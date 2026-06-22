"""Test multi-result CAD fix for known problem accounts."""
import asyncio, sys, yaml
sys.path.insert(0, '/home/ubuntu/scraper')
from montgomery.config import Config
from montgomery.tax_lookup import TaxLookup

def load_config():
    with open('/home/ubuntu/scraper/montgomery/config/config.yaml') as f:
        d = yaml.safe_load(f)
    return Config(**d)

async def main():
    cfg = load_config()
    tax = TaxLookup(cfg)

    # Account 0000020106500 cad_ref=R30113 — previously picked wrong account (0073250205101)
    print("=== Test 1: R30113 (4 results, was picking wrong one) ===")
    r1 = await tax.lookup('0000020106500', cad_ref='R30113')
    print(f"total_due={r1.total_due} initial_year={r1.initial_delinquency_year} years_behind={r1.years_behind} last_payment={r1.last_payment_date}")
    print(f"address={r1.property_address}")

    # Account 0000020108800 cad_ref=R30136 — 3 results
    print("\n=== Test 2: R30136 (3 results) ===")
    r2 = await tax.lookup('0000020108800', cad_ref='R30136')
    print(f"total_due={r2.total_due} initial_year={r2.initial_delinquency_year} years_behind={r2.years_behind} last_payment={r2.last_payment_date}")
    print(f"address={r2.property_address}")

asyncio.run(main())
