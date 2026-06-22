"""
Cross-verify a specific account: show every raw Excel column + computed output.
Usage: python diagnose_montgomery.py [ACCOUNT_NUMBER]
Default: uses account 000000130387
"""
from __future__ import annotations
import sys
import pandas as pd
import re

EXCEL_PATH = "montgomery/downloads/Montgomery_Tax_Del_Raw_032726.xlsx"
HEADER_ROW = 2

FINANCIAL_COLS = [
    "LEVY_BALANCE", "PENDUE", "INTDUE", "PANDI_ATTY",
    "ATTY_FEE", "COURT_COST", "ABSTRACT_FEE", "OTHER_FEE",
]

def _to_float(val) -> float:
    try:
        return float(re.sub(r"[^\d.]", "", str(val))) if str(val) not in ("nan", "") else 0.0
    except Exception:
        return 0.0

def _clean(val) -> str:
    if pd.isna(val) or str(val).strip() == "nan":
        return ""
    return str(val).strip()

def main():
    target_can = sys.argv[1] if len(sys.argv) > 1 else "000000130387"
    # Strip leading zeros for matching (Excel stores without leading zeros sometimes)
    target_stripped = target_can.lstrip("0") or "0"

    print(f"\n{'='*70}")
    print(f"DIAGNOSTIC — Account: {target_can}  (also trying {target_stripped})")
    print(f"Excel: {EXCEL_PATH}")
    print(f"{'='*70}")

    print("\nLoading Excel (this takes ~3 min for the full file)...")
    df = pd.read_excel(EXCEL_PATH, header=HEADER_ROW, dtype=str)
    df.dropna(how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    print(f"Total rows: {len(df)}")
    print(f"Columns: {list(df.columns)}\n")

    # Try both padded and stripped forms
    if "CAN" not in df.columns:
        print("ERROR: CAN column not found!")
        return

    mask = df["CAN"].isin([target_can, target_stripped])
    group = df[mask]

    if group.empty:
        # Try partial match
        mask2 = df["CAN"].str.strip().str.lstrip("0") == target_stripped
        group = df[mask2]

    if group.empty:
        print(f"Account {target_can} NOT FOUND in Excel.")
        print("Sample CAN values:", list(df["CAN"].head(5)))
        return

    print(f"Found {len(group)} row(s) for this account.\n")

    # ── Raw Excel rows ────────────────────────────────────────────────────────
    print("RAW ROWS (all columns with values):")
    print("-" * 70)
    for idx, row in group.iterrows():
        print(f"\n  Row index {idx}:")
        for col in df.columns:
            val = str(row.get(col, ""))
            if val and val != "nan":
                print(f"    {col:20s} = {val}")

    # ── Financial breakdown ───────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("FINANCIAL COLUMN BREAKDOWN:")
    print("-" * 70)
    grand_total = 0.0
    for col in FINANCIAL_COLS:
        if col in group.columns:
            col_sum = group[col].apply(_to_float).sum()
            grand_total += col_sum
            vals = [str(v) for v in group[col].tolist()]
            print(f"  {col:20s}: {vals}  → sum = {col_sum:.2f}")
        else:
            print(f"  {col:20s}: COLUMN MISSING")

    print(f"\n  COMPUTED total_tax_due = {grand_total:.2f}")

    # Also check TOT_PERCAN for comparison
    if "TOT_PERCAN" in group.columns:
        percan_vals = [_to_float(v) for v in group["TOT_PERCAN"].tolist()]
        print(f"  TOT_PERCAN (per-row, NOT used): {percan_vals}  (sum={sum(percan_vals):.2f})")

    # ── Key field extraction ──────────────────────────────────────────────────
    first = group.iloc[0]
    print(f"\n{'='*70}")
    print("FIELD EXTRACTION (what would go into the Sheet):")
    print("-" * 70)

    addrstring = _clean(first.get("ADDRSTRING", ""))
    print(f"  ADDRSTRING raw:     {addrstring!r}")
    m = re.search(r"\s+(\d+\s+\w)", addrstring)
    if m:
        split = m.start()
        owner = addrstring[:split].strip()
        mailing = addrstring[split:].strip()
    else:
        owner, mailing = addrstring, ""
    print(f"  → owner:            {owner!r}")
    print(f"  → mailing_address:  {mailing!r}")

    pnum = _clean(first.get("PNUMBER", ""))
    pstr = _clean(first.get("PSTRNAME", ""))
    prop_addr = f"{pnum} {pstr}".strip()
    print(f"\n  PNUMBER:            {pnum!r}")
    print(f"  PSTRNAME:           {pstr!r}")
    print(f"  → property_address: {prop_addr!r}")

    roll = _clean(first.get("ROLL", ""))
    mapping = {"R": "Residential","C": "Commercial","L": "Land","P": "Personal Property","M": "Mineral","U": "Utility"}
    prop_type = mapping.get(roll.upper(), roll)
    print(f"\n  ROLL:               {roll!r}  → {prop_type!r}")

    legacres = _clean(first.get("LEGACRES", ""))
    legal = _clean(first.get("LGLSTRING", ""))
    print(f"\n  LEGACRES:           {legacres!r}")
    print(f"  LGLSTRING:          {legal!r}")

    aprdistacc = _clean(first.get("APRDISTACC", ""))
    print(f"\n  APRDISTACC (MCAD key): {aprdistacc!r}")
    print(f"  CAN (Tax Office key):  {_clean(first.get('CAN', ''))!r}")

    cause = _clean(first.get("CAUSE_NO", ""))
    print(f"\n  CAUSE_NO:           {cause!r}")

    if "YEAR" in group.columns:
        years = []
        for y in group["YEAR"].dropna():
            try: years.append(int(float(str(y))))
            except: pass
        print(f"\n  YEAR values:        {years}")
        print(f"  → initial_year:     {str(min(years)) if years else 'None'}")
        print(f"  → years_behind:     {str(len(set(years))) if years else 'None'}")
    else:
        print("\n  YEAR column: MISSING")

    print(f"\n  Computed total_tax_due: ${grand_total:.2f}")
    print(f"\n{'='*70}")
    print("NOTE: Tax Office (actweb.acttax.com) is IP-blocked — live balance not available.")
    print("The $amount above is Excel-derived (March 2026 snapshot).")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
