# tests/manual_test.py
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from src.agents.apollo_agent import ApolloAgent
from src.agents.rocketreach_agent import RocketReachAgent

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
current_dir = Path(__file__).parent.parent
env_path = current_dir / '.env'
load_dotenv(env_path)

TEST_COMPANIES = [
    {
        "name": "Hecla Mining Company",
        "website": "hecla.com",
        "alternates": ["Hecla Mining", "Hecla"]
    }
]

async def process_company(company_data: dict, apollo_agent: ApolloAgent, rocketreach_agent: RocketReachAgent):
    """Process a company through both agents following decision tree"""
    company_name = company_data["name"]
    logger.info(f"\nProcessing company: {company_name}")
    
    # Step 1: Try Apollo
    logger.info("Attempting Apollo search...")
    apollo_agent.set_domain(company_data["website"])
    apollo_result = await apollo_agent.process_company(company_name)
    
    found_people = []
    
    if apollo_result:
        # Add Apollo's found people
        logger.debug(f"Apollo returned: {apollo_result}")
        found_people.extend(apollo_result.get("found_people", []))
        
        # Try RocketReach for pending people
        pending_people = apollo_result.get("pending_people", [])
        if pending_people:
            logger.info(f"Attempting RocketReach for {len(pending_people)} pending Apollo people...")
            rr_result = await rocketreach_agent.process_company(company_name, pending_people)
            if rr_result:
                logger.debug(f"RocketReach returned for pending: {rr_result}")
                found_people.extend(rr_result.get("found_people", []))
    
    # If still no results, try RocketReach fresh search
    if not found_people:
        logger.info("Attempting fresh RocketReach search...")
        rr_result = await rocketreach_agent.process_company(company_name)
        if rr_result:
            logger.debug(f"RocketReach returned for fresh search: {rr_result}")
            found_people.extend(rr_result.get("found_people", []))
    
    if found_people:
        logger.info(f"Found {len(found_people)} total people with emails")
        return {
            "company": company_name,
            "website": company_data["website"],
            "people": found_people
        }
    
    logger.info("No results found")
    return None

async def test_company(company_data: dict):
    """Test a single company with all its variations"""
    logger.info(f"\n{'='*50}")
    logger.info(f"Testing company: {company_data['name']}")
    logger.info(f"Website: {company_data['website']}")
    logger.info(f"Alternate names: {company_data.get('alternates', [])}")
    logger.info(f"{'='*50}")

    # Initialize agents
    apollo_agent = ApolloAgent()
    rocketreach_agent = RocketReachAgent()

    # Try main name
    result = await process_company(company_data, apollo_agent, rocketreach_agent)
    if result:
        return result

    # Try alternates
    for alt_name in company_data.get("alternates", []):
        alt_data = company_data.copy()
        alt_data["name"] = alt_name
        logger.info(f"\nTrying alternate name: {alt_name}")
        result = await process_company(alt_data, apollo_agent, rocketreach_agent)
        if result:
            return result

    logger.info(f"\nNo results found for any variation of {company_data['name']}")
    return None

async def main():
    """Main test function"""
    try:
        results = []
        failed_companies = []

        # Test each company
        for company in TEST_COMPANIES:
            result = await test_company(company)
            if result:
                results.append(result)
            else:
                failed_companies.append(company["name"])

        # Print results summary
        logger.info("\n" + "="*50)
        logger.info("SEARCH RESULTS SUMMARY")
        logger.info("="*50)
        
        if results:
            logger.info(f"\nSuccessful searches ({len(results)}/{len(TEST_COMPANIES)}):")
            for result in results:
                logger.info(f"\n✓ {result['company']} ({result['website']})")
                for person in result["people"]:
                    logger.info(f"  - {person['name']}")
                    logger.info(f"    Title: {person['title']}")
                    logger.info(f"    Email: {person['email']}")
        
        if failed_companies:
            logger.info(f"\nFailed searches ({len(failed_companies)}/{len(TEST_COMPANIES)}):")
            for company in failed_companies:
                logger.info(f"✗ {company}")

        # Print success rate
        success_rate = (len(results) / len(TEST_COMPANIES)) * 100
        logger.info(f"\nOverall success rate: {success_rate:.1f}%")

    except Exception as e:
        logger.error(f"Error during test execution: {str(e)}")
        logger.info("\nEnvironment Check:")
        logger.info(f"Looking for .env file at: {env_path}")
        logger.info("Required environment variables:")
        logger.info("- APOLLO_API_KEY")
        logger.info("- ROCKETREACH_API_KEY")
        raise  # Re-raise the exception to see the full stack trace

if __name__ == "__main__":
    asyncio.run(main())