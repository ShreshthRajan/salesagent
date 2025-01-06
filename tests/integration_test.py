"""
Integration tests for lead enrichment functionality with Apollo and RocketReach agents
"""
import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
import pytest
import pytest_asyncio
from playwright.async_api import async_playwright, Page, BrowserContext
from dotenv import load_dotenv
import json

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
from src.utils.exceptions import AutomationError, ValidationError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
    'President',
    'CFO',
    'Chief Financial Officer',
    'VP Finance',
    'Vice President of Finance',
    'Director of Finance',
    'Director of FP&A'
}

# Test credentials
CREDENTIALS = {
    'apollo': {
        'email': os.getenv('APOLLO_EMAIL', 'vishesh@pillarhq.com'),
        'password': os.getenv('APOLLO_PASSWORD', 'MemberPrime316!!')
    },
    'rocketreach': {
        'email': os.getenv('ROCKETREACH_EMAIL', 'vishesh@pillarhq.com'),
        'password': os.getenv('ROCKETREACH_PASSWORD', 'MemberPrime316!!')
    }
}

@pytest.mark.asyncio
class TestLeadEnrichment:
    """Test suite for lead enrichment functionality"""

    @pytest_asyncio.fixture(scope="class")
    async def event_loop(self, request):
        """Create event loop"""
        loop = asyncio.get_event_loop()
        yield loop

    @pytest_asyncio.fixture(scope="class")
    async def browser_context(self, event_loop) -> BrowserContext:
        """Create and configure browser context for testing"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=['--start-maximized']
            )

            # Create context with specific viewport
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080}
            )

            # Create initial page
            await context.new_page()

            yield context
            
            await context.close()
            await browser.close()

    @pytest_asyncio.fixture(scope="class")
    async def mock_config(self):
        """Load test configuration"""
        config = ConfigManager().config
        # Ensure API keys are set
        assert os.getenv('APOLLO_API_KEY'), "APOLLO_API_KEY not set"
        assert os.getenv('ROCKETREACH_API_KEY'), "ROCKETREACH_API_KEY not set"
        assert os.getenv('OPENAI_API_KEY'), "OPENAI_API_KEY not set"
        return config

    @pytest_asyncio.fixture(scope="class")
    async def services(self, browser_context, mock_config):
        """Initialize services with proper pages"""
        # Create pages for each service
        service_page = await browser_context.new_page()
        apollo_page = await browser_context.new_page()
        rocket_page = await browser_context.new_page()

        # Initialize services
        vision_service = VisionService()
        action_parser = ActionParser()
        state_machine = NavigationStateMachine()
        await state_machine.initialize_search('init', 'setup')
        validation_service = ValidationService()
        screenshot_pipeline = ScreenshotPipeline(service_page)
        result_collector = ResultCollector()

        services_dict = {
            'vision_service': vision_service,
            'action_parser': action_parser,
            'state_machine': state_machine,
            'validation_service': validation_service,
            'screenshot_pipeline': screenshot_pipeline,
            'result_collector': result_collector,
            'browser_context': browser_context,
            'apollo_page': apollo_page,
            'rocket_page': rocket_page,
            'config': mock_config
        }

        yield services_dict

        # Cleanup pages and services
        await asyncio.gather(
            service_page.close(),
            apollo_page.close(),
            rocket_page.close()
        )
        await state_machine.cleanup()

    @pytest_asyncio.fixture(scope="class")
    async def orchestrator(self, services):
        """Create and configure the orchestrator"""
        try:
            # Create agent-specific pages
            apollo_page = await services['browser_context'].new_page()
            rocket_page = await services['browser_context'].new_page()
            
            # Initialize agents
            apollo_agent = ApolloAutonomousAgent(
                page=apollo_page,
                vision_service=services['vision_service'],
                action_parser=services['action_parser'],
                state_machine=services['state_machine'],
                validation_service=services['validation_service'],
                screenshot_pipeline=services['screenshot_pipeline'],
                result_collector=services['result_collector']
            )
            
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
            logger.info("Logging into Apollo...")
            await apollo_agent.login(
                CREDENTIALS['apollo']['email'],
                CREDENTIALS['apollo']['password']
            )
            
            logger.info("Logging into RocketReach...")
            await rocket_agent.login(
                CREDENTIALS['rocketreach']['email'],
                CREDENTIALS['rocketreach']['password']
            )
            
            # Create orchestrator
            orchestrator = LeadEnrichmentOrchestrator(
                apollo_agent=apollo_agent,
                rocket_agent=rocket_agent,
                validation_service=services['validation_service'],
                result_collector=services['result_collector']
            )
            
            yield orchestrator
            
            # Cleanup
            logger.info("Cleaning up orchestrator...")
            await orchestrator.cleanup()
            await apollo_page.close()
            await rocket_page.close()
            
        except Exception as e:
            logger.error(f"Failed to initialize orchestrator: {str(e)}")
            raise

    @pytest.mark.asyncio
    async def test_hecla_enrichment(self, orchestrator):
        """Test full enrichment flow for Hecla Mining Company"""
        try:
            logger.info(f"Starting enrichment test for {TEST_COMPANY['name']}")
            start_time = datetime.now()
            
            # Execute enrichment
            result = await orchestrator.enrich_company(
                company_name=TEST_COMPANY['name'],
                domain=TEST_COMPANY['domain']
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Enrichment completed in {duration:.2f} seconds")
            
            # Basic validation
            assert result is not None, "No result returned"
            assert result.contacts is not None, "No contacts returned"
            assert len(result.contacts) > 0, "No contacts found"
            assert duration < 300, "Enrichment took too long"
            
            # Validate each contact
            logger.info(f"\nFound {len(result.contacts)} contacts:")
            for contact in result.contacts:
                self._validate_contact(contact)
            
            # Export results
            export_path = await orchestrator.export_results(
                format='csv',
                filepath="test_results/hecla_mining"
            )
            assert export_path and Path(export_path).exists(), "Export failed"
            
            # Log metrics
            metrics = orchestrator.get_orchestrator_metrics()
            logger.info("\nPerformance Metrics:")
            logger.info(json.dumps(metrics, indent=2))
            
            return result
            
        except Exception as e:
            logger.error(f"Enrichment test failed: {str(e)}")
            raise

    @pytest.mark.asyncio
    async def test_rate_limiting(self, orchestrator):
        """Test rate limiting behavior"""
        try:
            logger.info("Starting rate limiting test")
            tasks = [
                orchestrator.enrich_company(
                    TEST_COMPANY['name'],
                    TEST_COMPANY['domain']
                )
                for _ in range(3)
            ]
            
            start_time = datetime.now()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            duration = (datetime.now() - start_time).total_seconds()
            
            # Validate results
            for i, result in enumerate(results):
                assert not isinstance(result, Exception), \
                    f"Task {i} failed: {result}"
                assert result.contacts, f"Task {i} returned no contacts"
            
            # Check rate limiting metrics
            metrics = orchestrator.get_orchestrator_metrics()
            assert metrics['detailed_metrics']['error_counts']['apollo'] == 0, \
                "Apollo rate limit exceeded"
            assert metrics['detailed_metrics']['error_counts']['rocketreach'] == 0, \
                "RocketReach rate limit exceeded"
            
            logger.info(f"Rate limiting test completed in {duration:.2f} seconds")
            logger.info("All rate limited requests completed successfully")
            
        except Exception as e:
            logger.error(f"Rate limiting test failed: {str(e)}")
            raise
    
    def _validate_contact(self, contact: dict):
        """Helper method to validate contact information"""
        # Required fields
        assert contact.get('name'), "Contact missing name"
        assert contact.get('title'), "Contact missing title"
        assert contact.get('email'), "Contact missing email"
        
        # Title validation
        assert any(
            title.lower() in contact['title'].lower()
            for title in EXPECTED_TITLES
        ), f"Invalid title: {contact['title']}"
        
        # Email validation
        email = contact['email']
        assert '@' in email, f"Invalid email format: {email}"
        assert email.endswith(TEST_COMPANY['domain']), \
            f"Email domain mismatch: {email}"
        
        # Source and confidence validation
        assert contact.get('sources'), "Missing source information"
        assert contact.get('confidence', 0) >= 0.7, \
            f"Low confidence: {contact.get('confidence')}"
        
        logger.info(
            f"- {contact['name']} ({contact['title']})"
            f"\n  Email: {contact['email']}"
            f"\n  Confidence: {contact.get('confidence'):.2f}"
            f"\n  Sources: {', '.join(contact['sources'])}"
        )

    @pytest.mark.asyncio
    async def test_error_recovery(self, orchestrator):
        """Test error recovery capabilities"""
        try:
            logger.info("Starting error recovery test")
            original_search = orchestrator.apollo_agent.search_company
            recovery_attempts = 0
            
            async def mock_error(*args, **kwargs):
                nonlocal recovery_attempts
                recovery_attempts += 1
                if recovery_attempts <= 2:
                    raise AutomationError("Simulated network error")
                return await original_search(*args, **kwargs)
            
            # Replace with mock function
            orchestrator.apollo_agent.search_company = mock_error
            
            # Execute with error simulation
            result = await orchestrator.enrich_company(
                TEST_COMPANY['name'],
                TEST_COMPANY['domain']
            )
            
            # Validate recovery
            assert result.contacts, "Failed to recover and get results"
            assert recovery_attempts > 1, "No retry attempts made"
            
            # Validate orchestrator metrics
            metrics = orchestrator.get_orchestrator_metrics()
            assert metrics['basic_metrics']['failed_searches'] > 0, \
                "Failed searches not tracked"
            assert metrics['detailed_metrics']['error_counts']['apollo'] > 0, \
                "Errors not tracked"
            assert result.error_details is None, \
                "Final result should not have errors"
            
            logger.info(f"Error recovery succeeded after {recovery_attempts} attempts")
            logger.info(f"Found {len(result.contacts)} contacts after recovery")
            
        except Exception as e:
            logger.error(f"Error recovery test failed: {str(e)}")
            raise
            
        finally:
            # Restore original function
            orchestrator.apollo_agent.search_company = original_search
    
