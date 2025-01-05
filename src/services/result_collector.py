"""
src/services/result_collector.py
Service for collecting, deduplicating, and managing search results
"""
from typing import Dict, List, Optional, Set
import logging
from dataclasses import dataclass, field
from datetime import datetime
import json
import aiofiles
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """Represents a single search result with metadata"""
    company_name: str
    person_name: str
    title: str
    email: Optional[str]
    confidence: float
    source: str
    found_at: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)
    validation_status: str = "pending"

class ResultCollector:
    """Manages search results with deduplication and persistence"""
    
    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = Path(storage_dir or "data/results")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.results: Dict[str, SearchResult] = {}
        self.company_cache: Dict[str, Set[str]] = {}
        self.email_patterns: Dict[str, str] = {}
        
        self._load_cached_results()

    async def add_result(self, result: SearchResult) -> bool:
        """Add new search result with deduplication"""
        try:
            # Generate unique key
            key = self._generate_result_key(result)
            
            # Check for duplicate
            if key in self.results:
                existing = self.results[key]
                if self._should_update(existing, result):
                    self.results[key] = result
                    await self._save_result(result)
                    return True
                return False
            
            # Add new result
            self.results[key] = result
            
            # Update caches
            company = result.company_name.lower()
            if company not in self.company_cache:
                self.company_cache[company] = set()
            self.company_cache[company].add(key)
            
            # Save result
            await self._save_result(result)
            return True
            
        except Exception as e:
            logger.error(f"Failed to add result: {str(e)}")
            return False

    async def add_batch_results(self, results: List[SearchResult]) -> Dict[str, bool]:
        """Add multiple results with status tracking"""
        status = {}
        for result in results:
            try:
                status[self._generate_result_key(result)] = await self.add_result(result)
            except Exception as e:
                logger.error(f"Batch add failed for result: {str(e)}")
                status[self._generate_result_key(result)] = False
        return status

    def get_company_results(self, company_name: str) -> List[SearchResult]:
        """Get all results for a company"""
        company = company_name.lower()
        if company not in self.company_cache:
            return []
            
        return [
            self.results[key]
            for key in self.company_cache[company]
            if key in self.results
        ]

    def get_result(self, key: str) -> Optional[SearchResult]:
        """Get specific result by key"""
        return self.results.get(key)

    async def update_result(self, key: str, updates: Dict) -> bool:
        """Update existing result"""
        try:
            if key not in self.results:
                return False
                
            result = self.results[key]
            
            # Update fields
            for field, value in updates.items():
                if hasattr(result, field):
                    setattr(result, field, value)
                elif field in result.metadata:
                    result.metadata[field] = value
                    
            # Save updated result
            await self._save_result(result)
            return True
            
        except Exception as e:
            logger.error(f"Failed to update result: {str(e)}")
            return False

    async def remove_result(self, key: str) -> bool:
        """Remove result and clean up caches"""
        try:
            if key not in self.results:
                return False
                
            result = self.results[key]
            company = result.company_name.lower()
            
            # Remove from caches
            if company in self.company_cache:
                self.company_cache[company].discard(key)
                if not self.company_cache[company]:
                    del self.company_cache[company]
                    
            # Remove result file
            result_file = self.storage_dir / f"{key}.json"
            if result_file.exists():
                result_file.unlink()
                
            # Remove from memory
            del self.results[key]
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove result: {str(e)}")
            return False

    def _generate_result_key(self, result: SearchResult) -> str:
        """Generate unique key for result"""
        return f"{result.company_name.lower()}_{result.person_name.lower()}".replace(" ", "_")

    def _should_update(self, existing: SearchResult, new: SearchResult) -> bool:
        """Determine if existing result should be updated"""
        # Update if new result has higher confidence
        if new.confidence > existing.confidence:
            return True
            
        # Update if new result has email and existing doesn't
        if new.email and not existing.email:
            return True
            
        # Update if new result is more recent and has same confidence
        if new.confidence == existing.confidence and new.found_at > existing.found_at:
            return True
            
        return False

    async def _save_result(self, result: SearchResult):
        """Save result to disk"""
        try:
            key = self._generate_result_key(result)
            result_file = self.storage_dir / f"{key}.json"
            
            # Convert to dict for serialization
            result_dict = {
                "company_name": result.company_name,
                "person_name": result.person_name,
                "title": result.title,
                "email": result.email,
                "confidence": result.confidence,
                "source": result.source,
                "found_at": result.found_at.isoformat(),
                "metadata": result.metadata,
                "validation_status": result.validation_status
            }
            
            async with aiofiles.open(result_file, 'w') as f:
                await f.write(json.dumps(result_dict, indent=2))
                
        except Exception as e:
            logger.error(f"Failed to save result: {str(e)}")

    def _load_cached_results(self):
        """Load existing results from disk"""
        try:
            for result_file in self.storage_dir.glob("*.json"):
                try:
                    with open(result_file) as f:
                        data = json.load(f)
                        result = SearchResult(
                            company_name=data["company_name"],
                            person_name=data["person_name"],
                            title=data["title"],
                            email=data["email"],
                            confidence=data["confidence"],
                            source=data["source"],
                            found_at=datetime.fromisoformat(data["found_at"]),
                            metadata=data["metadata"],
                            validation_status=data["validation_status"]
                        )
                        
                        # Add to memory
                        key = self._generate_result_key(result)
                        self.results[key] = result
                        
                        # Update company cache
                        company = result.company_name.lower()
                        if company not in self.company_cache:
                            self.company_cache[company] = set()
                        self.company_cache[company].add(key)
                        
                except Exception as e:
                    logger.error(f"Failed to load result file {result_file}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Failed to load cached results: {str(e)}")

    def get_stats(self) -> Dict:
        """Get collector statistics"""
        total_results = len(self.results)
        total_companies = len(self.company_cache)
        results_with_email = sum(1 for r in self.results.values() if r.email)
        
        confidence_sum = sum(r.confidence for r in self.results.values())
        avg_confidence = confidence_sum / total_results if total_results > 0 else 0
        
        return {
            "total_results": total_results,
            "total_companies": total_companies,
            "results_with_email": results_with_email,
            "average_confidence": avg_confidence,
            "storage_size_mb": self._get_storage_size() / (1024 * 1024)
        }

    def _get_storage_size(self) -> int:
        """Get total size of stored results in bytes"""
        try:
            return sum(f.stat().st_size for f in self.storage_dir.glob("*.json"))
        except Exception:
            return 0