"""
Integration test for lead enrichment using Hecla Mining Company as test case
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
import pytest
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
    'Vice President of Finance'
}

class TestLeadEnrichment:
    @pytest.fixture(scope="class")
    async def config(self):
        return ConfigManager().config

    @pytest.fixture(scope="class")
    async def browser_context(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # Set to True in production
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720}
            )
            yield context
            await context.close()
            await browser.close()

    @pytest.fixture(scope="class")
    async def services(self, browser_context, config):
        # Initialize services
        page = await browser_context.new_page()
        
        vision_service = VisionService()
        action_parser = ActionParser()
        state_machine = NavigationStateMachine()
        validation_service = ValidationService()
        screenshot_pipeline = ScreenshotPipeline()
        result_collector = ResultCollector()
        
        # Initialize agents with login
        apollo_agent = ApolloAutonomousAgent(
            page=page,
            vision_service=vision_service,
            action_parser=action_parser,
            state_machine=state_machine,
            validation_service=validation_service,
            screenshot_pipeline=screenshot_pipeline,
            result_collector=result_collector
        )
        
        # Login to Apollo
        await apollo_agent.login(
            config.apollo.email,
            config.apollo.password
        )
        
        # Initialize RocketReach agent
        rocket_page = await browser_context.new_page()
        rocket_agent = RocketReachAgent(
            page=rocket_page,
            vision_service=vision_service,
            action_parser=action_parser,
            state_machine=state_machine,
            validation_service=validation_service,
            screenshot_pipeline=screenshot_pipeline,
            result_collector=result_collector
        )
        
        # Login to RocketReach
        await rocket_agent.login(
            config.rocketreach.email,
            config.rocketreach.password
        )
        
        yield {
            'apollo_agent': apollo_agent,
            'rocket_agent': rocket_agent,
            'vision_service': vision_service,
            'action_parser': action_parser,
            'state_machine': state_machine,
            'validation_service': validation_service,
            'screenshot_pipeline': screenshot_pipeline,
            'result_collector': result_collector
        }
        
        # Cleanup
        await apollo_agent.cleanup()
        await rocket_agent.cleanup()

    @pytest.fixture(scope="class")
    async def orchestrator(self, services):
        orchestrator = LeadEnrichmentOrchestrator(
            apollo_agent=services['apollo_agent'],
            rocket_agent=services['rocket_agent'],
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
        logger.info(f"Enrichment completed in {(datetime.now() - start_time).total_seconds():.2f} seconds")
        logger.info(f"Found {len(result.contacts)} contacts")
        
        # Validate results
        assert result.company_name == TEST_COMPANY['name']
        assert len(result.contacts) > 0, "No contacts found"
        
        # Validate contact quality
        for contact in result.contacts:
            # Check required fields
            assert contact.get('name'), "Contact missing name"
            assert contact.get('title'), "Contact missing title"
            assert contact.get('email'), "Contact missing email"
            
            # Validate email format and collection
            email = contact['email']
            assert '@' in email, "Invalid email format"
            local_part, domain = email.split('@')
            
            # Basic email format validation
            assert len(local_part) > 0, "Empty local part in email"
            assert len(domain) > 0, "Empty domain in email"
            assert '.' in domain, "Invalid domain format"
            
            # Log discovered email pattern
            logger.info(f"Found email pattern: {local_part}@{domain}")
            
            # Validate email has associated confidence score
            assert 'confidence' in contact, "Missing confidence score for email"
            logger.info(f"Email confidence score: {contact['confidence']}")
            
            # Track found domains for pattern analysis
            if 'email_domains' not in self.__class__.__dict__:
                self.__class__.email_domains = set()
            self.__class__.email_domains.add(domain)
            
            # Validate source verification
            assert contact.get('sources'), "Missing source information for email"
            sources = contact['sources']
            logger.info(f"Email verified by sources: {', '.join(sources)}")
            
            # Validate title matches expected roles
            title_match = any(
                expected.lower() in contact['title'].lower()
                for expected in EXPECTED_TITLES
            )
            assert title_match, f"Unexpected title: {contact['title']}"
            
            # Check confidence scores
            assert contact.get('confidence', 0) >= 0.7, "Low confidence score"
            
            # Validate source information
            assert contact.get('sources'), "Missing source information"
            
            logger.info(f"Validated contact: {contact['name']} ({contact['title']})")
        
        # Export results
        export_path = await orchestrator.export_results(
            format='csv',
            include_metrics=True
        )
        assert export_path and Path(export_path).exists(), "Export failed"
        
        # Log performance metrics and discovered patterns
        metrics = orchestrator.get_orchestrator_metrics()
        logger.info("\nPerformance Metrics:")
        logger.info(f"Average processing time: {metrics['performance']['avg_processing_time']:.2f}s")
        logger.info(f"Cache hit rate: {metrics['performance']['cache_hit_rate']:.2%}")
        logger.info(f"Validation rate: {metrics['validation']['validation_rate']:.2%}")
        
        # Log email pattern analysis
        if hasattr(self.__class__, 'email_domains'):
            logger.info("\nDiscovered Email Domains:")
            for domain in sorted(self.__class__.email_domains):
                logger.info(f"- {domain}")
            
        # Log detailed result analysis
        logger.info("\nResult Analysis:")
        logger.info(f"Total contacts found: {len(result.contacts)}")
        source_breakdown = {}
        for contact in result.contacts:
            for source in contact.get('sources', []):
                source_breakdown[source] = source_breakdown.get(source, 0) + 1
        logger.info("Source breakdown:")
        for source, count in source_breakdown.items():
            logger.info(f"- {source}: {count} contacts")
        
        return result

    @pytest.mark.asyncio
    async def test_rate_limiting(self, orchestrator):
        """Test rate limiting behavior"""
        # Execute multiple searches in quick succession
        tasks = [
            orchestrator.enrich_company(TEST_COMPANY['name'], TEST_COMPANY['domain'])
            for _ in range(3)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify rate limiting worked
        metrics = orchestrator.get_orchestrator_metrics()
        assert metrics['detailed_metrics']['error_counts']['apollo'] == 0, "Rate limit exceeded"
        assert metrics['detailed_metrics']['error_counts']['rocketreach'] == 0, "Rate limit exceeded"

    @pytest.mark.asyncio
    async def test_error_recovery(self, orchestrator):
        """Test error recovery capabilities"""
        # Force an error by temporarily breaking the connection
        original_search = orchestrator.apollo_agent.search_company
        
        async def mock_error(*args, **kwargs):
            raise Exception("Simulated network error")
        
        orchestrator.apollo_agent.search_company = mock_error
        
        # Attempt enrichment
        result = await orchestrator.enrich_company(
            TEST_COMPANY['name'],
            TEST_COMPANY['domain']
        )
        
        # Verify recovery
        assert result.contacts, "Failed to recover from error"
        assert orchestrator.current_state.retry_counts['apollo'] > 0, "No retry attempts"
        
        # Restore original function
        orchestrator.apollo_agent.search_company = original_search