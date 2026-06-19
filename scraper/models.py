from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, computed_field


class CADData(BaseModel):
    uid: Optional[str] = None                    # 13-digit, no leading zero (business key)
    uid_raw: Optional[str] = None                # 14-digit, with leading zero (for Tax URL)
    pid: Optional[str] = None                    # TrueProdigy internal property ID
    owner_name: Optional[str] = None             # name
    owner_secondary: Optional[str] = None        # nameSecondary
    property_street: Optional[str] = None        # streetPrimary e.g. "360 NUECES ST"
    property_city: Optional[str] = None          # city (from fullSitus parse)
    property_state: Optional[str] = None         # state
    property_zip: Optional[str] = None           # zip
    mailing_street: Optional[str] = None         # addrDeliveryLine
    mailing_city: Optional[str] = None           # addrCity
    mailing_state: Optional[str] = None          # addrState
    mailing_zip: Optional[str] = None            # addrZip
    appraised_value: Optional[str] = None        # appraisedValue (integer -> string)
    property_type_code: Optional[str] = None     # propType: "R", "C", "M", etc.
    acreage: Optional[str] = None                # legalAcreage
    legal_description: Optional[str] = None      # legalDescription
    date_bought_by_owner: Optional[str] = None   # deedDt from /deeds first result
    property_status: Optional[str] = None        # active: "Yes"/"No"


class TaxData(BaseModel):
    taxes_due: str = "0"
    years_delinquent: int = 0
    last_payment_date: Optional[str] = None      # from showPaymentReceipts.do table
    initial_delinquency_year: Optional[str] = None  # earliest year with balance > 0


class ListingEntry(BaseModel):
    """Data captured from the clerk search results listing grid (before PDF download)."""
    instrument_no: str
    local_path: str
    date_filed: Optional[str] = None
    grantor_listing: Optional[str] = None
    sale_date_listing: Optional[str] = None
    legal_desc_listing: Optional[str] = None


class ForeclosureRecord(BaseModel):
    # --- Core PDF fields (existing) ---
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
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # --- Tax fields (existing, kept for backward compat) ---
    taxes_due: str = "0"
    appraised_value: Optional[str] = None
    account_number: Optional[str] = None         # uid_raw (14-digit), for sheet column compat
    property_status: Optional[str] = None
    # --- New: UID (primary key for dedup) ---
    uid: Optional[str] = None                    # 13-digit, no leading zero
    # --- New: CAD enrichment ---
    owner_name_cad: Optional[str] = None
    owner_secondary: Optional[str] = None
    property_street: Optional[str] = None
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    mailing_street: Optional[str] = None
    mailing_city: Optional[str] = None
    mailing_state: Optional[str] = None
    mailing_zip: Optional[str] = None
    property_type_code: Optional[str] = None
    acreage: Optional[str] = None
    legal_description_cad: Optional[str] = None
    date_bought_by_owner: Optional[str] = None
    # --- New: Tax enrichment ---
    years_delinquent: int = 0
    last_payment_date: Optional[str] = None
    initial_delinquency_year: Optional[str] = None
    # --- New: MLS ---
    listed_on_mls: Optional[str] = None          # "Yes" or "No"
    # --- Internal quality flag (not written to sheet) ---
    extraction_quality: Optional[str] = None     # "OK" or "LOW"

    def to_sheet_row(self) -> list:
        return [
            # Existing columns A-W (23 cols, backward compatible)
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
            # New columns X-AP (19 cols)
            self.uid or "",
            self.owner_name_cad or "",
            self.owner_secondary or "",
            self.property_street or "",
            self.property_city or "",
            self.property_state or "",
            self.property_zip or "",
            self.mailing_street or "",
            self.mailing_city or "",
            self.mailing_state or "",
            self.mailing_zip or "",
            self.property_type_code or "",
            self.acreage or "",
            self.legal_description_cad or "",
            self.date_bought_by_owner or "",
            str(self.years_delinquent),
            self.last_payment_date or "",
            self.initial_delinquency_year or "",
            self.listed_on_mls or "",
        ]


class RunReport(BaseModel):
    run_date: str
    date_range_searched: str
    total_results: int
    pdfs_downloaded: int
    records_processed: int
    validation_failures: int = 0
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
