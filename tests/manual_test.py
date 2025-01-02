# salesagent/salesagent/tests/manual_test.py
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from src.agents.apollo_agent import ApolloAgent
from src.agents.rocketreach_agent import RocketReachAgent

# Set up less-detailed logging by default
logging.basicConfig(
    level=logging.INFO,  # <--- changed to INFO from DEBUG
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

async def try_single_search(agent, company_name: str, service_name: str):
    """Try a single search with moderate logging."""
    logger.info(f"{service_name}: Searching for '{company_name}'...")
    try:
        result = await agent.process_company(company_name)
        
        if result:
            logger.info(f"  => {service_name} SUCCESS! Found:")
            logger.info(f"     Person Name: {result['name']}")
            logger.info(f"     Title: {result['title']}")
            logger.info(f"     Email: {result['email']}")
            return result
        else:
            logger.info(f"  => {service_name}: No final result for '{company_name}'")
            return None
    except Exception as e:
        logger.error(f"{service_name} ERROR for {company_name}: {e}")
        return None

async def try_company_name(name: str, apollo_agent: ApolloAgent, rocketreach_agent: RocketReachAgent):
    """Try both services for a single company name"""
    logger.info(f"\nTrying company name: {name} ...")

    # Try Apollo first
    result = await try_single_search(apollo_agent, name, "Apollo")
    if result:
        return result

    # Then try RocketReach
    result = await try_single_search(rocketreach_agent, name, "RocketReach")
    if result:
        return result

    return None

async def test_company(company_data: dict):
    """Test a single company with all its variations"""
    company_name = company_data["name"]
    company_website = company_data["website"]
    alternates = company_data.get("alternates", [])

    logger.info(f"\n{'='*50}")
    logger.info(f"Testing company: {company_name}")
    logger.info(f"Website: {company_website}")
    logger.info(f"Alternate names: {alternates}")
    logger.info(f"{'='*50}\n")

    # Initialize agents
    apollo_agent = ApolloAgent()
    rocketreach_agent = RocketReachAgent()

    # Main name
    result = await try_company_name(company_name, apollo_agent, rocketreach_agent)
    if result:
        return result

    # Try alternates
    for alt_name in alternates:
        logger.info(f"\nTrying alternate name: {alt_name}")
        result = await try_company_name(alt_name, apollo_agent, rocketreach_agent)
        if result:
            return result

    logger.info(f"\nNo results found for any variation of {company_name}")
    return None

async def main():
    results = {}
    successful_searches = []
    failed_searches = []

    # Test each company
    for company in TEST_COMPANIES:
        result = await test_company(company)
        results[company["name"]] = result
        
        if result:
            successful_searches.append((company["name"], result))
        else:
            failed_searches.append(company["name"])

    # Summary
    logger.info("\n" + "="*50)
    logger.info("SEARCH RESULTS SUMMARY")
    logger.info("="*50)
    
    logger.info(f"\nSuccessful searches ({len(successful_searches)}/{len(TEST_COMPANIES)}):")
    for (company_name, r) in successful_searches:
        logger.info(f" ✓ {company_name}")
        logger.info(f"    - Found: {r['name']}")
        logger.info(f"    - Title: {r['title']}")
        logger.info(f"    - Email: {r['email']}")

    logger.info(f"\nFailed searches ({len(failed_searches)}/{len(TEST_COMPANIES)}):")
    for company_name in failed_searches:
        logger.info(f" ✗ {company_name}")

    success_rate = (len(successful_searches) / len(TEST_COMPANIES)) * 100
    logger.info(f"\nOverall success rate: {success_rate:.1f}%")

if __name__ == "__main__":
    asyncio.run(main())
