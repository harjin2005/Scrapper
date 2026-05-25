from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
import pandas as pd
from scraper.logger import get_logger
from montgomery.models import DelinquentRecord

log = get_logger("excel_processor")

# Montgomery County raw export: header on row index 2, one row per delinquent year.
# Group by CAN to get one DelinquentRecord per property.
_HEADER_ROW = 2


def _parse_owner_and_mailing(addrstring: str) -> tuple[str, str]:
    """
    ADDRSTRING = 'ESPARZA SANDRA 438 N. CUYLER STREET PAMPA, TX 79065'
    Split on first digit run that starts a street number (e.g. '438').
    Returns (owner_name, mailing_address).
    """
    if not addrstring or str(addrstring) == "nan":
        return "", ""
    s = str(addrstring).strip()
    m = re.search(r"\s+(\d+\s+\w)", s)
    if m:
        split = m.start()
        owner = s[:split].strip()
        mailing = s[split:].strip()
        return owner, mailing
    return s, ""


def _clean_amount(val) -> Optional[str]:
    if pd.isna(val) or str(val).strip() in ("", "nan"):
        return None
    s = re.sub(r"[$,\s]", "", str(val)).strip()
    return s if s else None


def _clean_str(val) -> str:
    if pd.isna(val) or str(val).strip() == "nan":
        return ""
    return str(val).strip()


def _roll_to_property_type(roll: str) -> str:
    mapping = {
        "R": "Residential",
        "C": "Commercial",
        "L": "Land",
        "P": "Personal Property",
        "M": "Mineral",
        "U": "Utility",
    }
    return mapping.get(str(roll).strip().upper(), roll)


def load_excel(path: str, excel_file_date: str) -> list[DelinquentRecord]:
    """Read real Montgomery County delinquent tax roll, return one record per property."""
    log.info("loading_excel", path=path)

    df = pd.read_excel(path, header=_HEADER_ROW, dtype=str)
    df.dropna(how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    log.info("excel_raw_rows", count=len(df), columns=len(df.columns))

    # Ensure required column exists
    if "CAN" not in df.columns:
        log.error("CAN_column_missing", available=list(df.columns[:10]))
        return []

    # Drop rows with no CAN
    df = df[df["CAN"].notna() & (df["CAN"].str.strip() != "")]
    df.reset_index(drop=True, inplace=True)

    records: list[DelinquentRecord] = []
    grouped = df.groupby("CAN", sort=False)

    for can, group in grouped:
        first = group.iloc[0]

        # Owner name + mailing address from ADDRSTRING
        owner, mailing = _parse_owner_and_mailing(first.get("ADDRSTRING", ""))

        # Property address = PNUMBER + PSTRNAME
        pnum = _clean_str(first.get("PNUMBER", ""))
        pstr = _clean_str(first.get("PSTRNAME", ""))
        prop_address = f"{pnum} {pstr}".strip() if (pnum or pstr) else ""

        # Legal description
        legal = _clean_str(first.get("LGLSTRING", ""))

        # Property type from ROLL code
        roll = _clean_str(first.get("ROLL", ""))
        prop_type = _roll_to_property_type(roll) if roll else None
        prop_type_code = roll if roll else None

        # Lot size from LEGACRES
        lot_size = _clean_str(first.get("LEGACRES", ""))

        # Total due — sum all financial columns for all rows under this CAN.
        # TOT_PERCAN is a per-row/per-unit amount (not a grand total).
        # Authoritative current balance comes from Tax Office website (overrides this in main.py).
        # Formula: LEVY_BALANCE + PENDUE + INTDUE + PANDI_ATTY + ATTY_FEE + COURT_COST + ABSTRACT_FEE + OTHER_FEE
        # Note: PANDI = PENDUE + INTDUE (same values), so we don't double-count.
        _FINANCIAL_COLS = ["LEVY_BALANCE", "PENDUE", "INTDUE", "PANDI_ATTY", "ATTY_FEE",
                           "COURT_COST", "ABSTRACT_FEE", "OTHER_FEE"]

        def _to_float(val: str) -> float:
            try:
                return float(re.sub(r"[^\d.]", "", str(val))) if str(val) not in ("nan", "") else 0.0
            except Exception:
                return 0.0

        try:
            grand_total = sum(
                group[col].apply(_to_float).sum()
                for col in _FINANCIAL_COLS
                if col in group.columns
            )
            total_due = str(round(grand_total, 2)) if grand_total > 0 else None
        except Exception:
            total_due = None

        # Delinquency years from YEAR column
        years: list[int] = []
        if "YEAR" in group.columns:
            for y in group["YEAR"].dropna():
                try:
                    years.append(int(float(str(y))))
                except (ValueError, TypeError):
                    pass

        initial_year = str(min(years)) if years else None
        years_behind = str(len(set(years))) if years else None

        # Cause number
        cause_no = _clean_str(first.get("CAUSE_NO", "")) or None

        # As-of date from file
        asof = _clean_str(first.get("ASOFDATE", ""))
        file_date = excel_file_date or asof

        # MCAD search key = APRDISTACC (no leading zeros)
        aprdistacc = _clean_str(first.get("APRDISTACC", ""))

        rec = DelinquentRecord(
            account_number=str(can).strip(),
            property_owner=owner,
            property_address=prop_address,
            property_mailing_address=mailing or None,
            property_type=prop_type,
            property_type_code=prop_type_code,
            lot_size=lot_size or None,
            legal_description=legal or None,
            initial_delinquency_year=initial_year,
            years_behind_taxes=years_behind,
            cause_or_lawsuit_no=cause_no,
            total_tax_due=total_due,
            county="Montgomery",
            excel_file_date=file_date,
            # Store APRDISTACC for MCAD search in extra field via model_extra
        )
        # Attach MCAD search key as non-schema attribute
        object.__setattr__(rec, "_aprdistacc", aprdistacc)

        records.append(rec)

    log.info(
        "excel_loaded",
        total_raw_rows=len(df),
        unique_properties=len(records),
    )
    return records
