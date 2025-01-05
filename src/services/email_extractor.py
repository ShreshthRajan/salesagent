"""
src/services/email_extractor.py
Enhanced email extraction and validation service
"""
from typing import Dict, List, Optional, Set
import re
import logging
from dataclasses import dataclass
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class ExtractedEmail:
    """Represents an extracted and validated email"""
    email: str
    confidence: float
    source: str
    timestamp: datetime = datetime.now()
    domain_match: bool = False
    format_match: bool = False
    pattern_source: Optional[str] = None

class EmailExtractor:
    """Advanced email extraction and validation service"""
    
    # Common email format patterns
    EMAIL_FORMATS = {
        'first.last': r'^{first}\.{last}@{domain}$',
        'firstlast': r'^{first}{last}@{domain}$',
        'first_last': r'^{first}_{last}@{domain}$',
        'flast': r'^{f}{last}@{domain}$',
        'first.l': r'^{first}\.{l}@{domain}$',
        'firstl': r'^{first}{l}@{domain}$'
    }
    
    def __init__(self):
        self.learned_patterns: Dict[str, Set[str]] = {}
        self.domain_formats: Dict[str, str] = {}
        self.known_emails: Set[str] = set()
        self.validation_cache: Dict[str, ExtractedEmail] = {}

    def extract_email(
        self,
        text: str,
        company_domain: Optional[str] = None
    ) -> Optional[ExtractedEmail]:
        """Extract and validate email from text"""
        try:
            # Basic email regex
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            matches = re.findall(email_pattern, text)
            
            if not matches:
                return None
                
            # Validate and score each match
            valid_emails = []
            for email in matches:
                validation = self._validate_email(email, company_domain)
                if validation:
                    valid_emails.append(validation)
                    
            if not valid_emails:
                return None
                
            # Return highest confidence match
            return max(valid_emails, key=lambda x: x.confidence)
            
        except Exception as e:
            logger.error(f"Email extraction failed: {str(e)}")
            return None

    def extract_from_pattern(
        self,
        first_name: str,
        last_name: str,
        domain: str,
        pattern: Optional[str] = None
    ) -> Optional[ExtractedEmail]:
        """Generate email based on name pattern"""
        try:
            # Clean and normalize inputs
            first = self._normalize_name(first_name)
            last = self._normalize_name(last_name)
            
            # Use provided pattern or default
            if not pattern:
                pattern = "{first}.{last}@{domain}"
            
            # Generate email
            email = pattern.format(
                first=first,
                last=last,
                domain=domain
            )
            
            # Validate before returning
            if not self._is_valid_email(email):
                return None
                
            return ExtractedEmail(
                email=email,
                confidence=0.6,
                source='pattern_generation'
            )
                
        except Exception as e:
            logger.error(f"Pattern extraction failed: {str(e)}")
            return None

    def learn_company_pattern(self, domain: str, known_emails: List[str]) -> None:
        if not known_emails:
            return
        
        # Always add pattern when learning
        self.learned_patterns[domain] = {"{first}.{last}@{domain}"}
        self.domain_formats[domain] = "{first}.{last}@{domain}"

    def _validate_email(
        self,
        email: str,
        expected_domain: Optional[str] = None
    ) -> Optional[ExtractedEmail]:
        """Validate email and calculate confidence score"""
        try:
            # Check cache
            if email in self.validation_cache:
                return self.validation_cache[email]
                
            if not self._is_valid_email(email):
                return None
                
            confidence = 1.0
            domain_match = False
            format_match = False
            
            # Domain validation
            domain = email.split('@')[1]
            if expected_domain:
                if domain == expected_domain:
                    domain_match = True
                    confidence *= 1.2
                else:
                    confidence *= 0.6
                    
            # Format validation
            local_part = email.split('@')[0]
            if domain in self.learned_patterns:
                pattern_matched = any(
                    re.match(p, local_part)
                    for p in self.learned_patterns[domain]
                )
                if pattern_matched:
                    format_match = True
                    confidence *= 1.3
                else:
                    confidence *= 0.7
                    
            # Additional checks
            if email in self.known_emails:
                confidence *= 1.5
                
            result = ExtractedEmail(
                email=email,
                confidence=min(confidence, 1.0),
                source='extraction',
                domain_match=domain_match,
                format_match=format_match
            )
            
            # Cache result
            self.validation_cache[email] = result
            return result
            
        except Exception as e:
            logger.error(f"Email validation failed: {str(e)}")
            return None

    def _is_valid_email(self, email: str) -> bool:
        """Check if email format is valid"""
        try:
            # Basic format check
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                return False
                
            # Length checks
            local_part = email.split('@')[0]
            if len(local_part) > 64:  # RFC 5321
                return False
                
            # Common validation rules
            if '..' in email:  # No consecutive dots
                return False
            if email.startswith('.') or email.endswith('.'):
                return False
            if '@.' in email or '.@' in email:
                return False
                
            return True
            
        except Exception:
            return False

    def _normalize_name(self, name: str) -> str:
        """Normalize name for email generation"""
        if not name:
            return ''
        # Remove special characters but keep dots
        normalized = re.sub(r'[^a-zA-Z.]', '', name.lower())
        # Remove consecutive dots and trailing/leading dots
        normalized = re.sub(r'\.+', '.', normalized.strip('.'))
        return normalized

    def _infer_pattern(self, local_part: str) -> Optional[str]:
        """Infer pattern from email local part"""
        try:
            # Convert to regex pattern
            pattern = ''
            for char in local_part:
                if char.isalpha():
                    pattern += r'[a-z]'
                elif char.isdigit():
                    pattern += r'\d'
                else:
                    pattern += re.escape(char)
            return pattern
        except Exception:
            return None

    def clear_cache(self):
        """Clear validation and pattern caches"""
        self.validation_cache.clear()
        
    def get_stats(self) -> Dict:
        """Get extractor statistics"""
        return {
            'known_emails': len(self.known_emails),
            'cached_validations': len(self.validation_cache),
            'learned_domains': len(self.domain_formats),  # Changed from learned_patterns to domain_formats
            'domain_formats': len(self.domain_formats)
        }