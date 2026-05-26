from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class DelinquentRecord(BaseModel):
    model_config = {"extra": "allow"}
    account_number: str
    property_owner: str = ""
    property_address: str = ""
    property_mailing_address: Optional[str] = None
    property_type: Optional[str] = None
    property_type_code: Optional[str] = None
    lot_size: Optional[str] = None
    legal_description: Optional[str] = None
    owner_contact_number: Optional[str] = None
    email: Optional[str] = None
    last_tax_payment_date: Optional[str] = None
    initial_delinquency_year: Optional[str] = None
    years_behind_taxes: Optional[str] = None
    cause_or_lawsuit_no: Optional[str] = None
    cause_date: Optional[str] = None
    appraised_value: Optional[str] = None
    total_tax_due: Optional[str] = None
    county: str = "Montgomery"
    excel_file_date: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_sheet_row(self) -> list:
        def _val(v, placeholder: str = "N/A") -> str:
            return str(v).strip() if v and str(v).strip() not in ("", "None") else placeholder

        return [
            self.account_number,
            _val(self.property_owner, "N/A"),
            _val(self.property_address, "N/A"),
            _val(self.property_mailing_address, "N/A"),
            _val(self.property_type, "N/A"),
            _val(self.property_type_code, "N/A"),
            _val(self.lot_size, "N/A"),
            _val(self.legal_description, "N/A"),
            _val(self.owner_contact_number, "N/A"),
            _val(self.email, "N/A"),
            _val(self.last_tax_payment_date, "N/A"),
            _val(self.initial_delinquency_year, "N/A"),
            _val(self.years_behind_taxes, "N/A"),
            _val(self.cause_or_lawsuit_no, "N/A"),
            _val(self.cause_date, "N/A"),
            _val(self.appraised_value, "N/A"),
            _val(self.total_tax_due, "N/A"),
            self.county,
            self.excel_file_date,
            str(self.created_at or ""),
            str(self.updated_at or ""),
        ]


class RunReport(BaseModel):
    run_date: str
    excel_file_date: str
    total_rows_in_excel: int
    rows_processed: int
    rows_added: int
    rows_updated: int
    required_field_extraction_rate: float
    mcad_lookup_success_rate: float
    tax_lookup_success_rate: float
    failed_account_numbers: list[str] = []
    failed_mcad: list[str] = []
    failed_tax: list[str] = []
    total_runtime_seconds: float
    overall_status: str = "PASS"

    def model_post_init(self, __context) -> None:
        if (
            self.required_field_extraction_rate < 0.85
            or self.rows_processed < self.total_rows_in_excel * 0.95
        ):
            self.overall_status = "FAIL"
        elif (
            self.required_field_extraction_rate < 0.95
            or self.mcad_lookup_success_rate < 0.90
            or self.tax_lookup_success_rate < 0.85
        ):
            self.overall_status = "REVIEW"
        else:
            self.overall_status = "PASS"


class CADData(BaseModel):
    property_type: Optional[str] = None
    property_type_code: Optional[str] = None
    appraised_value: Optional[str] = None
    lot_size: Optional[str] = None
    mailing_address: Optional[str] = None
    owner_contact: Optional[str] = None
    legal_description: Optional[str] = None


class TaxData(BaseModel):
    last_payment_date: Optional[str] = None
    initial_delinquency_year: Optional[str] = None
    years_behind: Optional[str] = None
    cause_number: Optional[str] = None
    cause_date: Optional[str] = None
    total_due: Optional[str] = None
    property_address: Optional[str] = None
    appraised_value: Optional[str] = None
