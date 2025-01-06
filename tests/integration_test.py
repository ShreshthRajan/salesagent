"""
Integration test for lead enrichment using Hecla Mining Company as test case
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

from src.agents.apollo_autonomous_agent import ApolloAutonomousAgent
from src.agents.rocket_autonomous_agent import RocketReachAgent
from src.services.vision_service import VisionService
from src.services.action_parser import ActionParser
from src.services.navigation_state import NavigationStateMachine
from src.services.validation_service import ValidationService
from src.services.screenshot_pipeline import ScreenshotPipeline
from src.services.result_collector import ResultCollector
from src.orchestration.lead_enrichment_orchestrator import LeadEnrichmentOrchestrator
from src.utils.config import ConfigManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
TEST_COMPANY = {
    'name': 'Hecla Mining Company',
    'domain': 'hecla.com'
}

# Expected titles for validation
EXPECTED_TITLES = {
    'CEO',
    'Chief Executive Officer',
    'CFO',
    'Chief Financial Officer',
    'VP Finance',
    'Vice President of Finance',
    'Director of Finance',
    'Director of FP&A'
}

@pytest.mark.asyncio
class TestLeadEnrichment:
    @pytest_asyncio.fixture(scope="class")
    async def config(self):
        return ConfigManager().config

    @pytest_asyncio.fixture(scope="class")
    async def browser_context(self, event_loop):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720}
            )
            yield context
            await context.close()
            await browser.close()

    @pytest_asyncio.fixture(scope="class")
    async def services(self, browser_context, config):
        # Initialize services
        vision_service = VisionService()
        action_parser = ActionParser()
        state_machine = NavigationStateMachine()
        validation_service = ValidationService()
        screenshot_pipeline = ScreenshotPipeline(browser_context.pages[0])
        result_collector = ResultCollector()
        
        yield {
            'vision_service': vision_service,
            'action_parser': action_parser,
            'state_machine': state_machine,
            'validation_service': validation_service,
            'screenshot_pipeline': screenshot_pipeline,
            'result_collector': result_collector,
            'browser_context': browser_context
        }
        
        # Cleanup
        await state_machine.cleanup()

    @pytest_asyncio.fixture(scope="class")
    async def orchestrator(self, services):
        page = await services['browser_context'].new_page()
        
        # Initialize Apollo agent
        apollo_agent = ApolloAutonomousAgent(
            page=page,
            vision_service=services['vision_service'],
            action_parser=services['action_parser'],
            state_machine=services['state_machine'],
            validation_service=services['validation_service'],
            screenshot_pipeline=services['screenshot_pipeline'],
            result_collector=services['result_collector']
        )

        # Initialize RocketReach agent
        rocket_page = await services['browser_context'].new_page()
        rocket_agent = RocketReachAgent(
            page=rocket_page,
            vision_service=services['vision_service'],
            action_parser=services['action_parser'],
            state_machine=services['state_machine'],
            validation_service=services['validation_service'],
            screenshot_pipeline=services['screenshot_pipeline'],
            result_collector=services['result_collector']
        )

        # Login to services
        await apollo_agent.login("vishesh@pillarhq.com", "MemberPrime316!!")
        await rocket_agent.login("vishesh@pillarhq.com", "MemberPrime316!!")

        orchestrator = LeadEnrichmentOrchestrator(
            apollo_agent=apollo_agent,
            rocket_agent=rocket_agent,
            validation_service=services['validation_service'],
            result_collector=services['result_collector']
        )

        yield orchestrator
        await orchestrator.cleanup()

    @pytest.mark.asyncio
    async def test_hecla_enrichment(self, orchestrator):
        """Test full enrichment flow for Hecla Mining Company"""
        logger.info(f"Starting enrichment test for {TEST_COMPANY['name']}")
        start_time = datetime.now()
        
        # Execute enrichment
        result = await orchestrator.enrich_company(
            company_name=TEST_COMPANY['name'],
            domain=TEST_COMPANY['domain']
        )
        
        # Log basic metrics
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Enrichment completed in {duration:.2f} seconds")
        logger.info(f"Found {len(result.contacts)} contacts")
        
        # Basic result validation
        assert result.company_name == TEST_COMPANY['name']
        assert len(result.contacts) > 0, "No contacts found"
        assert duration < 300, "Enrichment took too long"
        
        # Track email domains for pattern analysis
        email_domains = set()
        email_patterns = {}
        
        # Validate each contact
        for contact in result.contacts:
            # Required fields validation
            assert contact.get('name'), "Contact missing name"
            assert contact.get('title'), "Contact missing title"
            assert contact.get('email'), "Contact missing email"
            assert contact.get('confidence'), "Contact missing confidence score"
            assert contact.get('sources'), "Contact missing source information"
            
            # Name format validation
            name_parts = contact['name'].split()
            assert len(name_parts) >= 2, f"Invalid name format: {contact['name']}"
            
            # Title validation
            title_match = any(
                expected.lower() in contact['title'].lower()
                for expected in EXPECTED_TITLES
            )
            assert title_match, f"Unexpected title: {contact['title']}"
            
            # Email validation
            email = contact['email']
            assert '@' in email, "Invalid email format"
            local_part, domain = email.split('@')
            
            # Basic email format checks
            assert len(local_part) > 0, "Empty local part in email"
            assert len(domain) > 0, "Empty domain in email"
            assert '.' in domain, "Invalid domain format"
            assert not email.startswith('.'), "Email starts with dot"
            assert not email.endswith('.'), "Email ends with dot"
            assert '..' not in email, "Email contains consecutive dots"
            
            # Track email patterns
            email_domains.add(domain)
            pattern = self._extract_email_pattern(local_part)
            if pattern:
                if domain not in email_patterns:
                    email_patterns[domain] = set()
                email_patterns[domain].add(pattern)
            
            # Source validation
            assert len(contact['sources']) > 0, "No sources found"
            for source in contact['sources']:
                assert source in ['apollo', 'rocketreach'], f"Invalid source: {source}"
            
            # Confidence score validation
            assert 0 <= contact['confidence'] <= 1, "Invalid confidence score"
            if len(contact['sources']) > 1:
                assert contact['confidence'] >= 0.8, "Low confidence for multi-source"
            
            # Cross-validation check
            if 'cross_validated' in contact:
                assert isinstance(contact['cross_validated'], bool)
                if contact['cross_validated']:
                    assert len(contact['sources']) > 1, "Invalid cross-validation"
            
            logger.info(f"Validated contact: {contact['name']} ({contact['title']})")
            logger.info(f"Email pattern: {pattern} for domain: {domain}")
        
        # Export validation
        export_path = await orchestrator.export_results(format='csv')
        assert export_path and Path(export_path).exists(), "Export failed"
        
        # Performance metrics validation
        metrics = orchestrator.get_orchestrator_metrics()
        assert metrics['successful_searches'] > 0, "No successful searches"
        assert metrics['performance']['avg_processing_time'] < 60, "Slow processing"
        assert metrics['performance']['cache_hit_rate'] >= 0, "Invalid cache rate"
        
        # Log metrics
        logger.info("\nPerformance Metrics:")
        logger.info(f"Total searches: {metrics['total_searches']}")
        logger.info(f"Success rate: {metrics['successful_searches']/metrics['total_searches']:.2%}")
        logger.info(f"Average processing time: {metrics['performance']['avg_processing_time']:.2f}s")
        logger.info(f"Cache hit rate: {metrics['performance']['cache_hit_rate']:.2%}")
        
        # Log discovered patterns
        logger.info("\nDiscovered Email Patterns:")
        for domain, patterns in email_patterns.items():
            logger.info(f"\nDomain: {domain}")
            for pattern in patterns:
                logger.info(f"- {pattern}")
        
        # Source metrics
        logger.info("\nSource Metrics:")
        for source, stats in metrics['sources'].items():
            logger.info(f"\n{source.title()}:")
            logger.info(f"Success rate: {stats.get('success_rate', 0):.2%}")
            logger.info(f"Error rate: {stats.get('error_rate', 0):.2%}")
        
        return result

    @pytest.mark.asyncio
    async def test_rate_limiting(self, orchestrator):
        """Test rate limiting behavior"""
        tasks = [
            orchestrator.enrich_company(TEST_COMPANY['name'], TEST_COMPANY['domain'])
            for _ in range(3)
        ]
        
        start_time = datetime.now()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = (datetime.now() - start_time).total_seconds()
        
        # Validate results
        for result in results:
            assert not isinstance(result, Exception), "Rate limit task failed"
            assert result.contacts, "No contacts found"
            
        # Check rate limiting worked
        metrics = orchestrator.get_orchestrator_metrics()
        assert metrics['detailed_metrics']['error_counts']['apollo'] == 0
        assert metrics['detailed_metrics']['error_counts']['rocketreach'] == 0
        
        # Verify reasonable timing
        assert duration > 1.0, "Rate limiting not enforced"
        logger.info(f"Rate limited batch completed in {duration:.2f} seconds")
        
        # Log rate limiting metrics
        for source in ['apollo', 'rocketreach']:
            source_metrics = metrics['sources'][source]
            logger.info(f"\n{source.title()} Rate Limiting:")
            logger.info(f"Requests: {source_metrics['total_requests']}")
            logger.info(f"Rate limit hits: {source_metrics['rate_limit_hits']}")

    @pytest.mark.asyncio
    async def test_error_recovery(self, orchestrator):
        """Test error recovery capabilities"""
        original_search = orchestrator.apollo_agent.search_company
        recovery_tracked = {'attempts': 0}
        
        async def mock_error(*args, **kwargs):
            recovery_tracked['attempts'] += 1
            if recovery_tracked['attempts'] <= 2:
                raise Exception("Simulated network error")
            return await original_search(*args, **kwargs)
        
        orchestrator.apollo_agent.search_company = mock_error
        
        # Execute with error simulation
        result = await orchestrator.enrich_company(
            TEST_COMPANY['name'],
            TEST_COMPANY['domain']
        )
        
        # Validate recovery
        assert result.contacts, "Failed to recover and get results"
        assert recovery_tracked['attempts'] > 1, "No retry attempts made"
        assert orchestrator.current_state is not None, "State not maintained"
        
        # Validate error tracking
        metrics = orchestrator.get_orchestrator_metrics()
        assert metrics['detailed_metrics']['error_counts']['apollo'] > 0
        assert len(orchestrator.current_state.errors) > 0
        
        # Log recovery metrics
        logger.info("\nError Recovery Metrics:")
        logger.info(f"Recovery attempts: {recovery_tracked['attempts']}")
        logger.info(f"Final state: {orchestrator.current_state.status}")
        logger.info(f"Errors encountered: {len(orchestrator.current_state.errors)}")
        
        # Restore original function
        orchestrator.apollo_agent.search_company = original_search

    def _extract_email_pattern(self, local_part: str) -> Optional[str]:
        """Extract pattern from email local part"""
        pattern = ''
        for char in local_part:
            if char.isalpha():
                pattern += 'a'
            elif char.isdigit():
                pattern += 'd'
            else:
                pattern += char
        return pattern