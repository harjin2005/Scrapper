from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, computed_field


class ForeclosureRecord(BaseModel):
    index_no: Optional[int] = None
    instrument_no: str
    address: str
    county: str = "Travis"
    sale_type: str = "Substitute Trustee Sale"
    sale_date: Optional[date] = None
    document_type: str = "Notice of Substitute Trustee Sale"
    grantor: str
    grantee: Optional[str] = None
    legal_description: Optional[str] = None
    related_document_no: Optional[str] = None
    related_doc_type: Optional[str] = "Deed of Trust"
    substitute_trustee: Optional[str] = None
    returnee_attorney: Optional[str] = None
    notary: Optional[str] = None
    date_received: Optional[date] = None
    pdf_link: str
    property_status: Optional[str] = None
    account_number: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    taxes_due: str = "0"
    appraised_value: Optional[str] = None

    def to_sheet_row(self) -> list:
        return [
            self.index_no or "",
            self.instrument_no,
            self.address,
            self.county,
            self.sale_type,
            str(self.sale_date) if self.sale_date else "",
            self.document_type,
            self.grantor,
            self.grantee or "",
            self.legal_description or "",
            self.related_document_no or "",
            self.related_doc_type or "",
            self.substitute_trustee or "",
            self.returnee_attorney or "",
            self.notary or "",
            str(self.date_received) if self.date_received else "",
            self.pdf_link,
            self.property_status or "",
            self.account_number or "",
            self.created_at.isoformat(),
            self.updated_at.isoformat(),
            self.taxes_due,
            self.appraised_value or "",
        ]


class CADData(BaseModel):
    account_number: Optional[str] = None
    appraised_value: Optional[str] = None
    property_status: Optional[str] = None


class TaxData(BaseModel):
    taxes_due: str = "0"
    years_delinquent: int = 0


class RunReport(BaseModel):
    run_date: str
    date_range_searched: str
    total_results: int
    pdfs_downloaded: int
    records_processed: int
    required_field_extraction_rate: float
    cad_lookup_success_rate: float
    tax_lookup_success_rate: float
    failed_downloads: list[str]
    failed_cad_lookups: list[str]
    failed_tax_lookups: list[str]
    total_runtime_seconds: float

    @computed_field
    @property
    def overall_status(self) -> str:
        pdf_rate = self.pdfs_downloaded / max(self.total_results, 1)
        if (
            self.required_field_extraction_rate < 0.85
            or pdf_rate < 0.95
        ):
            return "FAIL"
        if (
            self.required_field_extraction_rate < 0.95
            or self.cad_lookup_success_rate < 0.90
            or self.tax_lookup_success_rate < 0.85
        ):
            return "REVIEW"
        return "PASS"
