# salesagent/salesagent/tests/manual_test.py

import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

from src.agents.apollo_agent import ApolloAgent
from src.agents.rocketreach_agent import RocketReachAgent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    logger.info(f"{service_name}: Searching for '{company_name}' using process_company...")
    try:
        result = await agent.process_company(company_name)
        if result:
            people = result.get("people", [])
            emails = result.get("emails", [])
            logger.info(f" => {service_name} Found {len(people)} person(s)")
            for i, p in enumerate(people, start=1):
                logger.info(f"    [{i}] {p['name']} - {p['title']} (email={p['email']})")
            logger.info(f" => Gathered {len(emails)} email(s): {emails}")
            return result
        else:
            logger.info(f" => {service_name} No result for '{company_name}'")
            return None
    except Exception as e:
        logger.error(f"{service_name} ERROR for {company_name}: {str(e)}")
        return None

async def try_company_name(name: str, apollo_agent: ApolloAgent, rocketreach_agent: RocketReachAgent):
    logger.info(f"\nTrying company name: {name} ...")

    # 1) Try Apollo
    apollo_result = await try_single_search(apollo_agent, name, "Apollo")
    if apollo_result and apollo_result.get("people"):
        return apollo_result

    # 2) RocketReach
    rocket_result = await try_single_search(rocketreach_agent, name, "RocketReach")
    if rocket_result and rocket_result.get("people"):
        return rocket_result

    return None

async def test_company(company_data: dict):
    name = company_data["name"]
    website = company_data["website"]
    alts = company_data.get("alternates", [])

    logger.info(f"\n{'='*50}")
    logger.info(f"Testing company: {name}")
    logger.info(f"Website: {website}")
    logger.info(f"Alternate names: {alts}")
    logger.info(f"{'='*50}\n")

    apollo_agent = ApolloAgent()
    apollo_agent.set_domain(website)  # e.g. "hecla.com"

    rocket_agent = RocketReachAgent()

    main_result = await try_company_name(name, apollo_agent, rocket_agent)
    if main_result:
        return main_result

    for alt in alts:
        logger.info(f"\nTrying alternate name: {alt} ...")
        alt_res = await try_company_name(alt, apollo_agent, rocket_agent)
        if alt_res:
            return alt_res

    logger.info(f"\nNo results found for any variation of {name}")
    return None

async def main():
    successes = []
    fails = []

    for comp in TEST_COMPANIES:
        out = await test_company(comp)
        if out:
            successes.append(comp["name"])
        else:
            fails.append(comp["name"])

    logger.info("\n" + "="*50)
    logger.info("SEARCH RESULTS SUMMARY")
    logger.info("="*50)
    
    logger.info(f"\nSuccessful: {len(successes)}/{len(TEST_COMPANIES)}")
    for s in successes:
        logger.info(f"  ✓ {s}")

    logger.info(f"\nFailed: {len(fails)}/{len(TEST_COMPANIES)}")
    for f in fails:
        logger.info(f"  ✗ {f}")

    sr = (len(successes)/len(TEST_COMPANIES))*100
    logger.info(f"\nOverall success rate: {sr:.1f}%")

if __name__ == "__main__":
    asyncio.run(main())
