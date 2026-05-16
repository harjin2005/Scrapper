from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
import pandas as pd
from scraper.logger import get_logger
from montgomery.models import DelinquentRecord

log = get_logger("excel_processor")

# Flexible column name mapping — keys are lowercase stripped variants
_COL_MAP = {
    # account number
    "account number": "account_number",
    "account no": "account_number",
    "acct no": "account_number",
    "acct number": "account_number",
    "account#": "account_number",
    # owner
    "owner name": "property_owner",
    "owner": "property_owner",
    "property owner": "property_owner",
    "taxpayer name": "property_owner",
    "taxpayer": "property_owner",
    # property address
    "situs address": "property_address",
    "property address": "property_address",
    "situs": "property_address",
    "address": "property_address",
    "property location": "property_address",
    # legal description
    "legal description": "legal_description",
    "legal desc": "legal_description",
    "legal": "legal_description",
    # total tax due
    "total amount due": "total_tax_due",
    "total due": "total_tax_due",
    "amount due": "total_tax_due",
    "total tax due": "total_tax_due",
    "balance due": "total_tax_due",
}


def _normalize_col(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).lower().strip())


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Return {df_column: field_name} for recognized columns."""
    mapping: dict[str, str] = {}
    for col in df.columns:
        norm = _normalize_col(col)
        if norm in _COL_MAP:
            mapping[col] = _COL_MAP[norm]
    return mapping


def _clean_amount(val) -> Optional[str]:
    if pd.isna(val) or val == "":
        return None
    s = re.sub(r"[$,\s]", "", str(val)).strip()
    return s if s else None


def _clean_str(val) -> str:
    if pd.isna(val):
        return ""
    return str(val).strip()


def load_excel(path: str, excel_file_date: str) -> list[DelinquentRecord]:
    """Read XLSX, map columns, return list of DelinquentRecord."""
    log.info("loading_excel", path=path)
    df = pd.read_excel(path, dtype=str)

    # Drop fully empty rows
    df.dropna(how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    col_map = _map_columns(df)
    log.info("column_mapping", mapped=col_map, total_columns=len(df.columns))

    if "account_number" not in col_map.values():
        # Last-chance: look for any column whose values look like account numbers
        for col in df.columns:
            sample = df[col].dropna().head(5).tolist()
            if all(re.match(r"\d{5,}", str(v)) for v in sample if v):
                col_map[col] = "account_number"
                log.warning("account_column_guessed", column=col)
                break

    records: list[DelinquentRecord] = []
    skipped = 0

    for idx, row in df.iterrows():
        fields: dict = {"excel_file_date": excel_file_date}

        for df_col, field_name in col_map.items():
            raw = row.get(df_col, "")
            if field_name == "total_tax_due":
                fields[field_name] = _clean_amount(raw)
            else:
                fields[field_name] = _clean_str(raw)

        account = fields.get("account_number", "")
        if not account or not re.match(r"\d", account):
            skipped += 1
            continue

        records.append(DelinquentRecord(**fields))

    log.info(
        "excel_loaded",
        total_rows=len(df),
        records=len(records),
        skipped=skipped,
    )
    return records
