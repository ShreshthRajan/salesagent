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
            # result is { 'people': [...], 'emails': [...] } or None
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

    # 1) Apollo
    a_res = await try_single_search(apollo_agent, name, "Apollo")
    if a_res and a_res.get("people"):
        return a_res

    # 2) RocketReach
    r_res = await try_single_search(rocketreach_agent, name, "RocketReach")
    if r_res and r_res.get("people"):
        return r_res

    return None

async def test_company(company_data: dict):
    name = company_data["name"]
    website = company_data["website"]
    alts = company_data.get("alternates",[])

    logger.info(f"\n{'='*50}")
    logger.info(f"Testing company: {name}")
    logger.info(f"Website: {website}")
    logger.info(f"Alternate names: {alts}")
    logger.info(f"{'='*50}\n")

    a_agent = ApolloAgent()
    r_agent = RocketReachAgent()

    res = await try_company_name(name, a_agent, r_agent)
    if res:
        return res

    for alt in alts:
        logger.info(f"\nTrying alternate name: {alt} ...")
        alt_res = await try_company_name(alt, a_agent, r_agent)
        if alt_res:
            return alt_res

    logger.info(f"\nNo results found for any variation of {name}")
    return None

async def main():
    success = []
    fails = []
    for comp in TEST_COMPANIES:
        out = await test_company(comp)
        if out:
            success.append(comp["name"])
        else:
            fails.append(comp["name"])

    logger.info("\n" + "="*50)
    logger.info("SEARCH RESULTS SUMMARY")
    logger.info("="*50)
    
    logger.info(f"\nSuccessful: {len(success)}/{len(TEST_COMPANIES)}")
    for s in success:
        logger.info(f"  ✓ {s}")

    logger.info(f"\nFailed: {len(fails)}/{len(TEST_COMPANIES)}")
    for f in fails:
        logger.info(f"  ✗ {f}")

    sr = (len(success)/len(TEST_COMPANIES))*100
    logger.info(f"\nOverall success rate: {sr:.1f}%")

if __name__ == "__main__":
    asyncio.run(main())
