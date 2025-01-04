# src/services/validation_service.py
from typing import Dict, Optional, List
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
import json
import aiofiles
from pathlib import Path
from src.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    is_valid: bool
    confidence: float
    errors: List[str]
    timestamp: datetime = field(default_factory=datetime.now)

class ValidationService:
    """Validates actions, results, and maintains validation history"""
    
    def __init__(self):
        self.email_pattern = re.compile(r'^[\w\.-]+@[\w\.-]+\.\w+$')
        self.validation_history: List[Dict] = []
        self.pattern_cache = {}
        self.confidence_threshold = 0.8
        self.history_file = Path("data/validation_history.json")
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.validation_metrics = {
            'total_validations': 0,
            'successful_validations': 0,
            'failed_validations': 0
        }

    async def validate_action(self, action: Dict) -> ValidationResult:
        """Validate proposed action with confidence scoring"""
        errors = []
        confidence = 1.0
        
        try:
            # Check required fields
            required_fields = {'type', 'target'}
            if not all(field in action for field in required_fields):
                errors.append("Missing required fields")
                confidence *= 0.5

            # Validate action type
            valid_actions = {'click', 'type', 'wait', 'scroll', 'hover'}
            if action['type'] not in valid_actions:
                errors.append(f"Invalid action type: {action['type']}")
                confidence *= 0.3

            # Validate target format
            if isinstance(action['target'], dict):
                if not ('x' in action['target'] and 'y' in action['target']):
                    if not ('selector' in action['target']):
                        errors.append("Invalid target format")
                        confidence *= 0.7

            # Type-specific validation
            if action['type'] == 'type' and 'value' not in action:
                errors.append("Missing value for type action")
                confidence *= 0.6

            result = ValidationResult(
                is_valid=len(errors) == 0,
                confidence=confidence,
                errors=errors
            )

            await self._update_metrics(result)
            await self._save_validation_result(action, result)
            return result

        except Exception as e:
            logger.error(f"Action validation error: {str(e)}")
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                errors=[str(e)]
            )

    async def validate_email(self, email: str, domain: Optional[str] = None) -> ValidationResult:
        """Validate email with pattern learning and confidence scoring"""
        errors = []
        confidence = 1.0
        
        try:
            # Basic format validation
            if not self.email_pattern.match(email):
                errors.append("Invalid email format")
                confidence *= 0.3
            
            # Domain validation if provided
            if domain:
                email_domain = email.split('@')[1]
                if email_domain != domain:
                    errors.append("Email domain mismatch")
                    confidence *= 0.5
            
            # Pattern matching from learned patterns
            if email.split('@')[1] in self.pattern_cache:
                pattern = self.pattern_cache[email.split('@')[1]]
                if not re.match(pattern, email.split('@')[0]):
                    errors.append("Email doesn't match company pattern")
                    confidence *= 0.7
            
            result = ValidationResult(
                is_valid=len(errors) == 0,
                confidence=confidence,
                errors=errors
            )
            
            await self._update_pattern_learning(email)
            await self._update_metrics(result)
            return result
            
        except Exception as e:
            logger.error(f"Email validation error: {str(e)}")
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                errors=[str(e)]
            )

    async def validate_result(self, result: Dict) -> Optional[Dict]:
        """Validate search result with comprehensive checks"""
        try:
            errors = []
            confidence = 1.0

            # Required fields check
            required_fields = {'name', 'title', 'company'}
            for field in required_fields:
                if field not in result:
                    errors.append(f"Missing required field: {field}")
                    confidence *= 0.5

            # Name validation
            if 'name' in result:
                if not self.validate_person_name(result['name']):
                    errors.append("Invalid person name format")
                    confidence *= 0.7

            # Email validation if present
            if 'email' in result:
                email_validation = await self.validate_email(
                    result['email'],
                    result.get('company_domain')
                )
                if not email_validation.is_valid:
                    errors.extend(email_validation.errors)
                    confidence *= email_validation.confidence

            # Company validation
            if 'company' in result and len(result['company'].strip()) < 2:
                errors.append("Invalid company name")
                confidence *= 0.8

            validation_result = ValidationResult(
                is_valid=len(errors) == 0,
                confidence=confidence,
                errors=errors
            )

            await self._update_metrics(validation_result)

            if validation_result.is_valid and validation_result.confidence >= self.confidence_threshold:
                result['validation_score'] = validation_result.confidence
                return result
            return None

        except Exception as e:
            logger.error(f"Result validation error: {str(e)}")
            return None

    def validate_person_name(self, name: str) -> bool:
        """Validate person name format"""
        if not name or not isinstance(name, str):
            return False
        
        # Basic name validation (at least two parts, reasonable length)
        parts = name.split()
        if len(parts) < 2:
            return False
        
        # Check each part is reasonable
        for part in parts:
            if len(part) < 2 or not part[0].isupper():
                return False
                
        return True

    async def _update_pattern_learning(self, email: str):
        """Update pattern learning from valid email"""
        try:
            domain = email.split('@')[1]
            local_part = email.split('@')[0]
            
            if domain not in self.pattern_cache:
                self.pattern_cache[domain] = self._generate_pattern(local_part)
            else:
                # Update existing pattern
                current_pattern = self.pattern_cache[domain]
                new_pattern = self._merge_patterns(current_pattern, local_part)
                self.pattern_cache[domain] = new_pattern

            await self._save_patterns()

        except Exception as e:
            logger.error(f"Pattern learning update failed: {str(e)}")

    def _generate_pattern(self, local_part: str) -> str:
        """Generate regex pattern from email local part"""
        pattern = ""
        for char in local_part:
            if char.isalpha():
                pattern += r"[a-zA-Z]"
            elif char.isdigit():
                pattern += r"\d"
            else:
                pattern += re.escape(char)
        return pattern

    def _merge_patterns(self, current: str, new_local: str) -> str:
        """Merge existing pattern with new email format"""
        try:
            current_parts = current.split(r'\.')
            new_parts = new_local.split('.')
            
            merged = []
            for i in range(max(len(current_parts), len(new_parts))):
                if i < len(current_parts) and i < len(new_parts):
                    # Merge corresponding parts
                    merged.append(self._merge_pattern_parts(
                        current_parts[i],
                        self._generate_pattern(new_parts[i])
                    ))
                else:
                    # Add remaining parts as optional
                    part = (current_parts[i] if i < len(current_parts)
                           else self._generate_pattern(new_parts[i]))
                    merged.append(f"(?:{part})?")
            
            return r'\.'.join(merged)
        
        except Exception as e:
            logger.error(f"Pattern merge failed: {str(e)}")
            return current

    def _merge_pattern_parts(self, pattern1: str, pattern2: str) -> str:
        """Merge two pattern parts"""
        if pattern1 == pattern2:
            return pattern1
        return f"(?:{pattern1}|{pattern2})"

    async def _save_patterns(self):
        """Save learned patterns to disk"""
        try:
            patterns_file = self.history_file.parent / "email_patterns.json"
            async with aiofiles.open(patterns_file, 'w') as f:
                await f.write(json.dumps(self.pattern_cache))
        except Exception as e:
            logger.error(f"Failed to save patterns: {str(e)}")

    async def _update_metrics(self, result: ValidationResult):
        """Update validation metrics"""
        self.validation_metrics['total_validations'] += 1
        if result.is_valid:
            self.validation_metrics['successful_validations'] += 1
        else:
            self.validation_metrics['failed_validations'] += 1

    async def _save_validation_result(self, item: Dict, result: ValidationResult):
        """Save validation result to history"""
        history_entry = {
            'item': item,
            'result': {
                'is_valid': result.is_valid,
                'confidence': result.confidence,
                'errors': result.errors,
                'timestamp': result.timestamp.isoformat()
            }
        }
        
        self.validation_history.append(history_entry)
        
        # Persist to disk
        async with aiofiles.open(self.history_file, 'a') as f:
            await f.write(json.dumps(history_entry) + '\n')

    async def cross_validate(self, email: str, sources: List[Dict]) -> ValidationResult:
        """Cross-validate result across multiple sources"""
        confidences = []
        errors = []
        
        for source in sources:
            if email == source.get('email'):
                confidences.append(1.0)
            elif source.get('email_pattern') and re.match(source['email_pattern'], email):
                confidences.append(0.8)
            else:
                confidences.append(0.0)
                errors.append(f"Mismatch with source: {source.get('source_name')}")
        
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        result = ValidationResult(
            is_valid=avg_confidence >= self.confidence_threshold,
            confidence=avg_confidence,
            errors=errors
        )
        
        await self._update_metrics(result)
        return result

    def get_validation_metrics(self) -> Dict:
        """Get current validation metrics"""
        success_rate = (
            self.validation_metrics['successful_validations'] /
            self.validation_metrics['total_validations']
            if self.validation_metrics['total_validations'] > 0 else 0
        )
        
        return {
            **self.validation_metrics,
            'success_rate': success_rate,
            'pattern_cache_size': len(self.pattern_cache),
            'history_size': len(self.validation_history)
        }