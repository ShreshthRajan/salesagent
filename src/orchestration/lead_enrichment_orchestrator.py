"""
Enhanced orchestration layer for coordinating RocketReach and Apollo agents with comprehensive
state management, validation, and metrics tracking.
"""
import re
from typing import List, Dict, Optional, Set, Any
import asyncio
import logging
from datetime import datetime, timedelta
import pandas as pd
from dataclasses import dataclass, field
from pathlib import Path
import json
import aiofiles

from src.agents.apollo_autonomous_agent import ApolloAutonomousAgent
from src.agents.rocket_autonomous_agent import RocketReachAgent
from src.services.validation_service import ValidationService, ValidationResult
from src.services.result_collector import ResultCollector, SearchResult
from src.utils.exceptions import OrchestrationError, ValidationError
from src.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

@dataclass
class EnrichmentState:
    """Tracks the current state of an enrichment operation"""
    company: str
    stage: str
    start_time: datetime = field(default_factory=datetime.now)
    sources_completed: Set[str] = field(default_factory=set)
    results_found: int = 0
    errors: List[str] = field(default_factory=list)
    retry_counts: Dict[str, int] = field(default_factory=lambda: {'apollo': 0, 'rocketreach': 0})
    last_action: Optional[str] = None
    status: str = 'running'

@dataclass
class EnrichmentResult:
    """Represents combined enrichment results with detailed metrics"""
    company_name: str
    contacts: List[Dict]
    found_at: datetime = field(default_factory=datetime.now)
    source_metrics: Dict = field(default_factory=dict)
    validation_scores: Dict = field(default_factory=dict)
    performance_metrics: Dict = field(default_factory=dict)
    error_details: Optional[str] = None
    processing_time: float = 0.0

@dataclass
class ResultCache:
    """Cache for enrichment results"""
    result: EnrichmentResult
    timestamp: datetime
    ttl: timedelta = field(default=timedelta(hours=24))

    @property
    def is_valid(self) -> bool:
        return datetime.now() - self.timestamp < self.ttl

class LeadEnrichmentOrchestrator:
    """Orchestrates multi-source lead enrichment process with enhanced features"""
    
    def __init__(
        self,
        apollo_agent: ApolloAutonomousAgent,
        rocket_agent: RocketReachAgent,
        validation_service: ValidationService,
        result_collector: ResultCollector,
        cache_dir: Optional[str] = None
    ):
        self.apollo_agent = apollo_agent
        self.rocket_agent = rocket_agent
        self.validation_service = validation_service
        self.result_collector = result_collector
        
        # Configuration
        self.max_total_results = 5
        self.min_confidence_threshold = 0.7
        self.cross_validation_required = True
        self.cache_dir = Path(cache_dir or "cache/enrichment")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Source configuration
        self.source_weights = {
            'apollo': 0.6,
            'rocketreach': 0.4
        }
        self.source_priority = ['apollo', 'rocketreach']
        
        # Rate limiting
        self.rate_limiter = RateLimiter(
            max_requests=100,
            time_window=60,
            burst_limit=10
        )
        
        # State management
        self.current_state: Optional[EnrichmentState] = None
        self.current_tasks: Set[asyncio.Task] = set()
        self.result_cache: Dict[str, ResultCache] = {}
        
        # Metrics tracking
        self.metrics = {
            'total_searches': 0,
            'successful_searches': 0,
            'failed_searches': 0,
            'total_results': 0,
            'cross_validated_results': 0
        }
        
        self.detailed_metrics = {
            'search_times': [],
            'success_rates': {'apollo': [], 'rocketreach': []},
            'validation_rates': [],
            'error_counts': {'apollo': 0, 'rocketreach': 0},
            'cross_validations': {'successful': 0, 'failed': 0},
            'cache_hits': 0,
            'cache_misses': 0
        }

    async def enrich_company(
        self,
        company_name: str,
        domain: str,
        force_refresh: bool = False
    ) -> EnrichmentResult:
        """Enhanced company enrichment with caching and detailed tracking"""
        start_time = datetime.now()
        cache_key = f"{company_name}:{domain}"
        
        try:
            # Check cache first
            if not force_refresh:
                cached_result = await self._check_cache(cache_key)
                if cached_result:
                    self.detailed_metrics['cache_hits'] += 1
                    return cached_result
                    
            self.detailed_metrics['cache_misses'] += 1
            self.metrics['total_searches'] += 1
            
            # Initialize state
            self.current_state = EnrichmentState(
                company=company_name,
                stage='initializing'
            )
            
            # Start parallel agent searches with rate limiting
            apollo_task = asyncio.create_task(
                self._rate_limited_search(
                    self.apollo_agent.search_company,
                    company_name,
                    'apollo'
                )
            )
            rocket_task = asyncio.create_task(
                self._rate_limited_search(
                    self.rocket_agent.search_company,
                    domain,
                    'rocketreach'
                )
            )
            
            self.current_tasks.update({apollo_task, rocket_task})
            self.current_state.stage = 'searching'
            
            # Wait for both with timeout
            try:
                apollo_results, rocket_results = await asyncio.gather(
                    apollo_task, 
                    rocket_task,
                    return_exceptions=True
                )
            except Exception as e:
                logger.error(f"Agent search failed: {str(e)}")
                self.current_state.errors.append(str(e))
                apollo_results = []
                rocket_results = []
            
            # Update state
            self.current_state.stage = 'merging'
            
            # Process and merge results
            merged_results = await self._merge_results(
                apollo_results,
                rocket_results,
                domain
            )
            
            # Cross-validate if enabled
            self.current_state.stage = 'validating'
            if self.cross_validation_required:
                validated_results = await self._cross_validate_results(
                    merged_results,
                    domain
                )
            else:
                validated_results = merged_results
            
            # Store results
            self.current_state.stage = 'storing'
            for result in validated_results:
                await self.result_collector.add_result(
                    SearchResult(**result)
                )
            
            # Update metrics
            if validated_results:
                self.metrics['successful_searches'] += 1
            else:
                self.metrics['failed_searches'] += 1
            
            self.metrics['total_results'] += len(validated_results)
            processing_time = (datetime.now() - start_time).total_seconds()
            self.detailed_metrics['search_times'].append(processing_time)
            
            # Create enrichment result
            result = EnrichmentResult(
                company_name=company_name,
                contacts=validated_results,
                source_metrics=self._get_source_metrics(),
                validation_scores=self._get_validation_scores(validated_results),
                performance_metrics=self._get_performance_metrics(),
                processing_time=processing_time
            )
            
            # Cache result
            await self._cache_result(cache_key, result)
            
            self.current_state.stage = 'complete'
            self.current_state.status = 'success'
            return result
            
        except Exception as e:
            logger.error(f"Enrichment failed: {str(e)}")
            if self.current_state:
                self.current_state.status = 'failed'
                self.current_state.errors.append(str(e))
            return EnrichmentResult(
                company_name=company_name,
                contacts=[],
                error_details=str(e),
                processing_time=(datetime.now() - start_time).total_seconds()
            )
        finally:
            # Cleanup
            self.current_tasks = {
                task for task in self.current_tasks 
                if not task.done()
            }

    async def _rate_limited_search(
        self,
        search_func: Any,
        search_param: str,
        source: str
    ) -> List[Dict]:
        """Execute search with rate limiting and retries"""
        await self.rate_limiter.acquire()
        try:
            return await self._retry_failed_search(search_func, search_param, source)
        finally:
            self.rate_limiter.release()

    async def _retry_failed_search(
        self,
        search_func: Any,
        search_param: str,
        source: str,
        attempt: int = 0
    ) -> List[Dict]:
        """Retry failed searches with exponential backoff"""
        try:
            return await search_func(search_param)
        except Exception as e:
            if self.current_state:
                self.current_state.retry_counts[source] += 1
                
            self.detailed_metrics['error_counts'][source] += 1
            
            if attempt < 2:  # Max 3 attempts
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                return await self._retry_failed_search(
                    search_func,
                    search_param,
                    source,
                    attempt + 1
                )
            raise OrchestrationError(f"Search failed after retries: {str(e)}")

    async def _merge_results(
        self,
        apollo_results: List[Dict],
        rocket_results: List[Dict],
        domain: str
    ) -> List[Dict]:
        """Enhanced result merging with detailed validation"""
        try:
            merged = {}
            
            # Process Apollo results
            for result in apollo_results:
                if not await self._validate_contact_info(result, domain):
                    continue
                    
                key = self._generate_result_key(result)
                result['confidence'] = self._calculate_confidence(result, domain)
                
                if key not in merged:
                    merged[key] = result
                    merged[key]['sources'] = {'apollo'}
                else:
                    merged[key]['sources'].add('apollo')
                    merged[key]['confidence'] = max(
                        merged[key]['confidence'],
                        result['confidence']
                    )
                    
            # Process RocketReach results
            for result in rocket_results:
                if not await self._validate_contact_info(result, domain):
                    continue
                    
                key = self._generate_result_key(result)
                result['confidence'] = self._calculate_confidence(result, domain)
                
                if key not in merged:
                    merged[key] = result
                    merged[key]['sources'] = {'rocketreach'}
                else:
                    merged[key]['sources'].add('rocketreach')
                    merged[key]['confidence'] = max(
                        merged[key]['confidence'],
                        result['confidence']
                    )
            
            # Apply priority and confidence filtering
            prioritized = [
                result for result in merged.values()
                if result['confidence'] >= self.min_confidence_threshold
            ]
            
            # Sort by confidence and source priority
            prioritized.sort(
                key=lambda x: (
                    x['confidence'],
                    max(self.source_weights[s] for s in x['sources'])
                ),
                reverse=True
            )
            
            return prioritized[:self.max_total_results]
            
        except Exception as e:
            logger.error(f"Result merging failed: {str(e)}")
            if self.current_state:
                self.current_state.errors.append(f"Merge failure: {str(e)}")
            return []

    async def _validate_contact_info(self, result: Dict, domain: str) -> bool:
        """Comprehensive contact information validation"""
        try:
            # Title validation
            title_valid = any(
                title.lower() in result.get('title', '').lower()
                for title in self.apollo_agent.TARGET_TITLES
            )
            
            # Name format validation
            name_parts = result.get('name', '').split()
            name_valid = len(name_parts) >= 2
            
            # Email validation
            email = result.get('email')
            if not email:
                return False
                
            email_validation = await self.validation_service.validate_email(
                email,
                domain
            )
            
            # Pattern validation if available
            pattern_valid = True
            if domain in self.validation_service.pattern_cache:
                pattern = self.validation_service.pattern_cache[domain]
                local_part = email.split('@')[0]
                pattern_valid = bool(re.match(pattern, local_part))
            
            validation_result = all([
                title_valid,
                name_valid,
                email_validation.is_valid,
                pattern_valid
            ])
            
            # Update metrics
            self.detailed_metrics['validation_rates'].append(float(validation_result))
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Contact validation failed: {str(e)}")
            return False

    def _calculate_confidence(self, result: Dict, domain: str) -> float:
        """Enhanced confidence calculation with source weighting"""
        try:
            base_confidence = result.get('confidence', 0.5)
            
            # Apply source weights
            source_weight = sum(
                self.source_weights[source] 
                for source in result['sources']
            ) / len(result['sources'])
            
            weighted_confidence = base_confidence * source_weight
            
            # Adjust based on email domain match
            if result.get('email', '').endswith(domain):
                weighted_confidence *= 1.1
                
            # Adjust based on title match
            if any(title.lower() in result.get('title', '').lower() 
                   for title in self.apollo_agent.TARGET_TITLES):
                weighted_confidence *= 1.1
                
            # Adjust based on validation history
            if result.get('email') in self.validation_service.validation_cache:
                cached_validation = self.validation_service.validation_cache[result['email']]
                if cached_validation.is_valid:
                    weighted_confidence *= 1.05
                
            return min(weighted_confidence, 1.0)
            
        except Exception as e:
            logger.error(f"Confidence calculation failed: {str(e)}")
            return 0.5
        
    async def _cross_validate_results(
        self,
        results: List[Dict],
        domain: str
    ) -> List[Dict]:
        """Enhanced cross-validation with detailed tracking"""
        validated = []
        
        for result in results:
            try:
                # Skip if already validated
                if result.get('validated'):
                    validated.append(result)
                    continue
                
                # Email validation
                email_validation = await self.validation_service.validate_email(
                    result['email'],
                    domain
                )
                
                # Cross-validate sources
                if len(result['sources']) > 1:
                    result['confidence'] *= 1.2
                    result['cross_validated'] = True
                    self.metrics['cross_validated_results'] += 1
                    self.detailed_metrics['cross_validations']['successful'] += 1
                elif email_validation.is_valid:
                    result['confidence'] *= email_validation.confidence
                    result['cross_validated'] = False
                    self.detailed_metrics['cross_validations']['failed'] += 1
                
                # Additional validation checks
                validation_score = await self._compute_validation_score(result, domain)
                result['validation_score'] = validation_score
                
                if result['confidence'] >= self.min_confidence_threshold:
                    result['validated'] = True
                    validated.append(result)
                
            except Exception as e:
                logger.error(f"Result validation failed: {str(e)}")
                if self.current_state:
                    self.current_state.errors.append(f"Validation error: {str(e)}")
                
        return validated

    async def _compute_validation_score(self, result: Dict, domain: str) -> float:
        """Compute comprehensive validation score"""
        score = 0.0
        checks = 0
        
        # Email format
        if await self._check_email_format(result['email']):
            score += 1
        checks += 1
        
        # Domain match
        if result['email'].split('@')[1] == domain:
            score += 1
        checks += 1
        
        # Title validation
        if any(title.lower() in result['title'].lower() 
               for title in self.apollo_agent.TARGET_TITLES):
            score += 1
        checks += 1
        
        # Source agreement
        if len(result['sources']) > 1:
            score += 1
        checks += 1
        
        return score / checks if checks > 0 else 0.0

    async def process_batch(
        self,
        companies: List[Dict[str, str]],
        max_concurrent: int = 3
    ) -> Dict[str, EnrichmentResult]:
        """Process multiple companies with concurrency control"""
        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(company_info: Dict[str, str]) -> None:
            async with semaphore:
                result = await self.enrich_company(
                    company_info['name'],
                    company_info['domain']
                )
                results[company_info['name']] = result
        
        tasks = [
            process_with_semaphore(company)
            for company in companies
        ]
        
        await asyncio.gather(*tasks)
        return results

    async def _check_cache(self, cache_key: str) -> Optional[EnrichmentResult]:
        """Check cache for existing results"""
        try:
            if cache_key in self.result_cache:
                cached = self.result_cache[cache_key]
                if cached.is_valid:
                    return cached.result
                else:
                    del self.result_cache[cache_key]
            
            # Check persistent cache
            cache_file = self.cache_dir / f"{cache_key}.json"
            if cache_file.exists():
                async with aiofiles.open(cache_file, 'r') as f:
                    data = json.loads(await f.read())
                    if datetime.fromisoformat(data['timestamp']) + timedelta(hours=24) > datetime.now():
                        return EnrichmentResult(**data['result'])
            
            return None
            
        except Exception as e:
            logger.error(f"Cache check failed: {str(e)}")
            return None

    async def _cache_result(self, cache_key: str, result: EnrichmentResult) -> None:
        """Cache result in memory and on disk"""
        try:
            # Memory cache
            self.result_cache[cache_key] = ResultCache(
                result=result,
                timestamp=datetime.now()
            )
            
            # Disk cache
            cache_file = self.cache_dir / f"{cache_key}.json"
            cache_data = {
                'result': {
                    'company_name': result.company_name,
                    'contacts': result.contacts,
                    'source_metrics': result.source_metrics,
                    'validation_scores': result.validation_scores,
                    'performance_metrics': result.performance_metrics,
                    'processing_time': result.processing_time
                },
                'timestamp': datetime.now().isoformat()
            }
            
            async with aiofiles.open(cache_file, 'w') as f:
                await f.write(json.dumps(cache_data, indent=2))
                
        except Exception as e:
            logger.error(f"Cache update failed: {str(e)}")

    async def _check_email_format(self, email: str) -> bool:
        """Validate email format with common patterns"""
        try:
            if not email or '@' not in email:
                return False
                
            local, domain = email.split('@')
            
            # Basic format checks
            if not all(c.isalnum() or c in '.-_' for c in local):
                return False
                
            if local.startswith('.') or local.endswith('.'):
                return False
                
            if '..' in local or '..' in domain:
                return False
                
            return True
            
        except Exception:
            return False

    async def export_results(
        self,
        format: str = 'csv',
        filepath: Optional[str] = None,
        include_metrics: bool = True
    ) -> Optional[str]:
        """Enhanced export functionality with metrics"""
        try:
            results = await self.result_collector.get_all_results()
            
            if not results:
                logger.warning("No results to export")
                return None
            
            # Prepare export data
            export_data = []
            for r in results:
                result_dict = {
                    'company_name': r.company_name,
                    'person_name': r.person_name,
                    'title': r.title,
                    'email': r.email,
                    'confidence': r.confidence,
                    'sources': ','.join(r.metadata.get('sources', [])),
                    'validated': r.metadata.get('validated', False),
                    'cross_validated': r.metadata.get('cross_validated', False),
                    'validation_score': r.metadata.get('validation_score', 0.0),
                    'found_at': r.found_at.isoformat()
                }
                
                if include_metrics:
                    result_dict.update({
                        'processing_time': r.metadata.get('processing_time', 0.0),
                        'retry_count': r.metadata.get('retry_count', 0),
                        'error_count': len(r.metadata.get('errors', []))
                    })
                    
                export_data.append(result_dict)
            
            # Generate default filepath if not provided
            if not filepath:
                filepath = f"exports/enrichment_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Create directory if needed
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            
            # Export based on format
            df = pd.DataFrame(export_data)
            
            if format == 'csv':
                output_path = f"{filepath}.csv"
                df.to_csv(output_path, index=False)
                return output_path
            elif format == 'excel':
                output_path = f"{filepath}.xlsx"
                with pd.ExcelWriter(output_path) as writer:
                    df.to_excel(writer, sheet_name='Results', index=False)
                    
                    if include_metrics:
                        # Add metrics sheet
                        metrics_df = pd.DataFrame([{
                            **self.metrics,
                            **{f"detailed_{k}": v 
                               for k, v in self.detailed_metrics.items()}
                        }])
                        metrics_df.to_excel(writer, sheet_name='Metrics', index=False)
                        
                return output_path
            else:
                raise ValueError(f"Unsupported export format: {format}")
                
        except Exception as e:
            logger.error(f"Export failed: {str(e)}")
            return None

    async def cleanup(self):
        """Enhanced cleanup with cache management"""
        try:
            # Cancel pending tasks
            for task in self.current_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Cleanup agents
            await asyncio.gather(
                self.apollo_agent.cleanup(),
                self.rocket_agent.cleanup()
            )
            
            # Clear caches
            await self.result_collector.cleanup_cache()
            self.result_cache.clear()
            
            # Clean old cache files
            await self._cleanup_cache_files()
            
            # Reset state
            self.current_state = None
            self.current_tasks.clear()
            
            logger.info("Orchestrator cleanup completed")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")

    async def _cleanup_cache_files(self, max_age_hours: int = 24):
        """Clean up old cache files"""
        try:
            now = datetime.now()
            for cache_file in self.cache_dir.glob("*.json"):
                if cache_file.stat().st_mtime < (now - timedelta(hours=max_age_hours)).timestamp():
                    cache_file.unlink()
                    
        except Exception as e:
            logger.error(f"Cache file cleanup failed: {str(e)}")

    def get_orchestrator_metrics(self) -> Dict:
        """Get comprehensive orchestration metrics"""
        return {
            'basic_metrics': self.metrics,
            'detailed_metrics': self.detailed_metrics,
            'sources': self._get_source_metrics(),
            'validation': {
                'threshold': self.min_confidence_threshold,
                'cross_validation_enabled': self.cross_validation_required,
                'cross_validated_count': self.metrics['cross_validated_results'],
                'validation_rate': sum(self.detailed_metrics['validation_rates']) / 
                                 len(self.detailed_metrics['validation_rates'])
                                 if self.detailed_metrics['validation_rates'] else 0
            },
            'performance': {
                'avg_processing_time': sum(self.detailed_metrics['search_times']) /
                                     len(self.detailed_metrics['search_times'])
                                     if self.detailed_metrics['search_times'] else 0,
                'cache_hit_rate': self.detailed_metrics['cache_hits'] /
                                 (self.detailed_metrics['cache_hits'] + 
                                  self.detailed_metrics['cache_misses'])
                                 if (self.detailed_metrics['cache_hits'] + 
                                     self.detailed_metrics['cache_misses']) > 0 else 0,
                'active_tasks': len(self.current_tasks),
                'current_state': self.current_state.__dict__ if self.current_state else None
            }
        }