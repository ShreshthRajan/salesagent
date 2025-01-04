# src/services/vision_service.py
from typing import Dict, List, Optional, Any
import logging
import base64
import json
from pathlib import Path
import aiohttp
import asyncio
from functools import lru_cache
import hashlib
from datetime import datetime
from src.utils.config import ConfigManager
from src.utils.exceptions import VisionAPIError

logger = logging.getLogger(__name__)

class VisionService:
    """Enhanced GPT-4 Vision API integration service"""
    
    def __init__(self):
        self.config = ConfigManager().config
        self.api_key = self.config.openai.api_key
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self._load_prompt_templates()
        self.cache = {}
        self.retry_config = {
            'max_retries': 3,
            'base_delay': 1,
            'max_delay': 10
        }
        self.page_state_cache = {}
        self.state_confidence_threshold = 0.85

    def _load_prompt_templates(self):
        """Load and initialize prompt templates"""
        self.templates = {
            'default': self._get_default_template(),
            'search': self._get_search_template(),
            'profile': self._get_profile_template(),
            'extraction': self._get_extraction_template(),
            'validation': self._get_validation_template()
        }

    def _get_default_template(self) -> str:
        return """
        Analyze this screenshot of a web interface. Identify:
        1. Key interactive elements (buttons, inputs, links)
        2. Their exact locations (coordinates or selectors)
        3. Current page state and context
        4. Recommended next action with confidence score

        Format response as:
        {
            "page_state": "string",
            "confidence": float,
            "elements": [
                {
                    "type": "button|input|link",
                    "text": "string",
                    "location": {"x": int, "y": int} | "selector": "string",
                    "confidence": float
                }
            ],
            "next_action": {
                "type": "click|type|wait|scroll|hover",
                "target": {"x": int, "y": int} | "selector": "string",
                "value": "string",
                "confidence": float
            }
        }
        """

    def _get_search_template(self) -> str:
        return """
        Analyze this screenshot of a search interface. Focus on:
        1. Search input fields and their current values
        2. Submit/search buttons
        3. Any visible results or suggestions
        4. Error messages or captchas
        
        Additional Context: {context}
        """

    def _get_profile_template(self) -> str:
        return """
        Analyze this profile page screenshot. Focus on:
        1. Contact information sections
        2. Email reveal/show buttons
        3. Profile completeness indicators
        4. Navigation options
        
        Previous State: {previous_state}
        Target Information: {target_info}
        """

    def _get_extraction_template(self) -> str:
        return """
        Extract specific information from this screenshot:
        1. Email addresses (revealed or hidden)
        2. Contact buttons or forms
        3. Professional information
        4. Company details
        
        Format: {format_instructions}
        """

    def _get_validation_template(self) -> str:
        return """
        Validate this result page screenshot. Check for:
        1. Success/error messages
        2. Data quality indicators
        3. Verification badges/icons
        4. Alternative contact methods
        
        Expected Result: {expected_result}
        """

    def _get_dynamic_template(self, template_key: str, **kwargs) -> str:
        """Get and format dynamic prompt template"""
        base_template = self.dynamic_prompts.get(template_key, self.templates['default'])
        return base_template.format(**kwargs)

    @lru_cache(maxsize=100)
    async def _encode_image(self, image_path: str) -> str:
        """Encode image to base64 with caching"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    async def analyze_screenshot(
        self,
        screenshot_path: Path,
        template_key: str = 'default',
        custom_prompt: Optional[str] = None,
        retry_count: int = 0
    ) -> Dict:
        """Analyze screenshot with retries and caching"""
        cache_key = f"{str(screenshot_path)}_{template_key}_{custom_prompt}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            base64_image = await self._encode_image(str(screenshot_path))
            prompt = custom_prompt or self.templates.get(template_key, self.templates['default'])
            
            response = await self._make_api_request(base64_image, prompt)
            parsed_result = self._parse_vision_response(response)
            
            # Cache successful results
            self.cache[cache_key] = parsed_result
            return parsed_result

        except Exception as e:
            if retry_count < self.retry_config['max_retries']:
                delay = min(
                    self.retry_config['base_delay'] * (2 ** retry_count),
                    self.retry_config['max_delay']
                )
                await asyncio.sleep(delay)
                return await self.analyze_screenshot(
                    screenshot_path,
                    template_key,
                    custom_prompt,
                    retry_count + 1
                )
            raise VisionAPIError(f"Failed to analyze screenshot after retries: {str(e)}")

    async def analyze_with_context(
        self,
        screenshot_path: Path,
        context: Dict,
        previous_state: Optional[str] = None,
        template_key: str = 'default'
    ) -> Dict:
        """Analyze screenshot with additional context"""
        try:
            # Generate context-aware prompt
            prompt = self._get_dynamic_template(
                template_key,
                context=json.dumps(context),
                previous_state=previous_state,
                target_info=context.get('target_info', ''),
                expected_result=context.get('expected_result', '')
            )

            # Check cache with context hash
            cache_key = self._generate_context_cache_key(screenshot_path, context)
            if cache_key in self.page_state_cache:
                cached_result = self.page_state_cache[cache_key]
                if self._is_cache_valid(cached_result):
                    return cached_result['result']

            # Perform analysis with retries
            result = await self.analyze_screenshot(
                screenshot_path,
                custom_prompt=prompt
            )

            # Cache result with context
            self.page_state_cache[cache_key] = {
                'result': result,
                'timestamp': datetime.now(),
                'context': context
            }

            return result

        except Exception as e:
            logger.error(f"Context-aware analysis failed: {str(e)}")
            raise VisionAPIError(f"Failed to analyze with context: {str(e)}")

    async def _make_api_request(self, base64_image: str, prompt: str) -> Dict:
        """Make API request with timeout handling"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 500
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30
            ) as response:
                if response.status != 200:
                    raise VisionAPIError(f"API request failed: {await response.text()}")
                return await response.json()

    def _parse_vision_response(self, response: Dict) -> Dict:
        """Parse and validate Vision API response with confidence scoring"""
        try:
            content = json.loads(response['choices'][0]['message']['content'])
            
            # Validate required fields
            required_fields = {'page_state', 'elements', 'next_action'}
            if not all(field in content for field in required_fields):
                raise VisionAPIError("Invalid response format - missing required fields")
            
            # Ensure confidence scores exist
            if 'confidence' not in content:
                content['confidence'] = 0.0
                
            for element in content['elements']:
                if 'confidence' not in element:
                    element['confidence'] = 0.0
                    
            if 'confidence' not in content['next_action']:
                content['next_action']['confidence'] = 0.0
            
            return content
            
        except json.JSONDecodeError:
            raise VisionAPIError("Invalid JSON in response content")
        except KeyError as e:
            raise VisionAPIError(f"Missing key in response: {str(e)}")

    def _generate_context_cache_key(self, screenshot_path: Path, context: Dict) -> str:
        """Generate cache key including context"""
        context_str = json.dumps(context, sort_keys=True)
        return f"{str(screenshot_path)}_{hashlib.md5(context_str.encode()).hexdigest()}"

    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Check if cached result is still valid"""
        cache_age = (datetime.now() - cache_entry['timestamp']).total_seconds()
        return cache_age < 60  # Cache valid for 60 seconds

    async def validate_state_transition(
        self,
        before_screenshot: Path,
        after_screenshot: Path,
        expected_state: str
    ) -> bool:
        """Validate state transition with visual confirmation"""
        try:
            before_state = await self.analyze_screenshot(before_screenshot)
            after_state = await self.analyze_screenshot(after_screenshot)

            # Compare states
            state_changed = before_state['page_state'] != after_state['page_state']
            reached_expected = after_state['page_state'] == expected_state
            confidence_ok = after_state.get('confidence', 0) >= self.state_confidence_threshold

            return state_changed and reached_expected and confidence_ok

        except Exception as e:
            logger.error(f"State transition validation failed: {str(e)}")
            return False

    def get_state_analysis_metrics(self) -> Dict:
        """Get metrics about state analysis performance"""
        return {
            'cache_size': len(self.page_state_cache),
            'cache_hit_rate': self._calculate_cache_hit_rate(),
            'avg_confidence': self._calculate_avg_confidence(),
            'state_transition_success_rate': self._calculate_transition_rate()
        }

    def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total_requests = self.cache_hits + self.cache_misses
        return self.cache_hits / total_requests if total_requests > 0 else 0.0

    def _calculate_avg_confidence(self) -> float:
        """Calculate average confidence score"""
        if not self.page_state_cache:
            return 0.0
        confidences = [entry['result'].get('confidence', 0) 
                      for entry in self.page_state_cache.values()]
        return sum(confidences) / len(confidences)

    def _calculate_transition_rate(self) -> float:
        """Calculate successful state transition rate"""
        if not self.transition_attempts:
            return 0.0
        return self.successful_transitions / self.transition_attempts