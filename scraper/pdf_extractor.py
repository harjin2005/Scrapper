from __future__ import annotations
import io
import re
from datetime import date
from pathlib import Path
from typing import Optional
import pdfplumber
from scraper.models import ForeclosureRecord
from scraper.logger import get_logger

log = get_logger("pdf_extractor")

# Tesseract path on this machine (installed at D:\New folder by winget)
_TESSERACT_CMD = r"D:\New folder\tesseract.exe"


def _ocr_pdf(pdf_path: str) -> str:
    """Render each page with PyMuPDF and OCR with pytesseract."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
        doc = fitz.open(pdf_path)
        pages: list[str] = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            pages.append(pytesseract.image_to_string(img, lang="eng"))
        return "\n".join(pages)
    except Exception as exc:
        log.warning("ocr_failed", error=str(exc))
        return ""

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _clean_address(addr: str) -> str:
    addr = re.sub(r"\s+0{4,}\d+", "", addr)   # strip trailing OCR account numbers
    addr = re.sub(r"\s+\d{8,}$", "", addr)
    return addr.strip()


_ADDR_BOILERPLATE = re.compile(
    r"(NOTICE\s+OF|DEED\s+OF\s+TRUST|SUBSTITUTE\s+TRUSTEE|TRUSTEE'S|"
    r"recorded\s+on|Official\s+Public\s+Records|REAL\s+PROPERTY|"
    r"Earliest\s+Time|Ipm|Deed\s+of\s+Trust)",
    re.IGNORECASE,
)
_YEAR_PREFIX = re.compile(r"^20\d\d\b")
_VALID_STREET = re.compile(
    r"^\d{1,5}\s+\w",   # starts with 1-5 digit street number then word char
)


def _is_valid_address(addr: str) -> bool:
    if not addr or len(addr) < 6:
        return False
    if _YEAR_PREFIX.match(addr):
        return False
    if _ADDR_BOILERPLATE.search(addr):
        return False
    # Must start with a digit (street number) or look like a real address
    if not re.match(r"^\d", addr) and not re.search(r"\d{1,5}\s+\w", addr):
        return False
    return True


class PDFExtractor:
    def extract(self, pdf_path: str, pdf_link: str) -> ForeclosureRecord:
        filename = Path(pdf_path).stem
        text = self._read_pdf_text(pdf_path)
        log.info("pdf_text_extracted", pdf_path=pdf_path, char_count=len(text))

        instrument_no = self._extract_instrument_no(text, filename)
        record = ForeclosureRecord(
            instrument_no=instrument_no,
            address=self._extract_address(text) or "",
            grantor=self._extract_grantor(text) or "",
            grantee=self._extract_grantee(text),
            legal_description=self._extract_legal_description(text),
            sale_date=self._extract_sale_date(text),
            substitute_trustee=self._extract_substitute_trustee(text),
            returnee_attorney=self._extract_attorney(text),
            related_document_no=self._extract_dot_recording_no(text),
            pdf_link=pdf_link,
        )
        log.info("record_extracted", instrument_no=instrument_no)
        return record

    def _read_pdf_text(self, pdf_path: str) -> str:
        pages_text: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
        text = "\n".join(pages_text)
        if not text.strip():
            log.info("pdf_no_text_fallback_ocr", pdf_path=pdf_path)
            text = _ocr_pdf(pdf_path)
        return text

    def _extract_instrument_no(self, text: str, filename: str) -> str:
        patterns = [
            # "recorded in Document INSTRUMENT NO. 2024100942"
            r"INSTRUMENT\s+NO\.?\s*(\d{8,12})",
            r"[Ii]nstrument\s+No\.?\s*:?\s*(\d{8,12})",
            r"[Dd]ocument\s+No\.?\s*:?\s*(\d{8,12})",
            r"[Ii]nst\.?\s+No\.?\s*:?\s*(\d{8,12})",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        m = re.match(r"(\d{8,12})", filename)
        if m:
            return m.group(1)
        return filename.split("_")[0]

    def _extract_address(self, text: str) -> Optional[str]:
        # Priority 1: explicit label — "commonly known as" or "Property Address:"
        for pat in [
            r"[Cc]ommonly\s+known\s+as\s*:?\s*([^\n]+)",
            r"[Pp]roperty\s+[Aa]ddress\s*:?\s*([^\n]+)",
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                addr = _clean_address(m.group(1).strip().rstrip("."))
                # Strip leading date prefix e.g. "May 30, 2020 201 WOODLANDS CT"
                addr = re.sub(r"^(?:[A-Za-z]+ \d+,? )?20\d\d\s+", "", addr).strip()
                if _is_valid_address(addr):
                    return addr

        # Priority 2: address block at top — street line then city/state/zip
        top = text[:600]
        m = re.search(
            r"(\d+\s+[A-Z0-9][A-Z0-9 ]+(?:BLVD|DRIVE|DR|STREET|ST|AVE|AVENUE|LN|LANE|RD|ROAD|CT|COURT|WAY|CIR|PKWY|HWY|TRAIL|TRL|PASS|LOOP|CROSSING)[^\n]*)\n([^\n]*\bTX\b[^\n]*)",
            top, re.IGNORECASE
        )
        if m:
            street = re.sub(r"\s+\d{6,}", "", m.group(1)).strip()
            city_state = m.group(2).strip()
            addr = f"{street}, {city_state}"
            if _is_valid_address(addr):
                return addr

        # Priority 3: street number + known suffix anywhere in text
        # Exclude year-like numbers (2000-2099) as street numbers
        for m in re.finditer(
            r"(\d{1,5}\s+[A-Z][A-Z0-9 ]+(?:BLVD|DRIVE|DR|STREET|ST|AVE|AVENUE|LN|LANE|RD|ROAD|CT|COURT|WAY|CIR|PKWY|HWY|TRAIL|TRL|PASS|LOOP)[^\n,]*)",
            text, re.IGNORECASE
        ):
            addr = _clean_address(m.group(1).strip())
            if _is_valid_address(addr) and not _YEAR_PREFIX.match(addr):
                return addr

        return None

    def _extract_grantor(self, text: str) -> Optional[str]:
        # Travis County format: "with NAME, grantor(s) and LENDER, mortgagee"
        # Commercial format: "Borrower:\nNAME" or "Grantor:\nNAME"
        for pat in [
            r"with\s+([^,\n]+?),\s*grantor",
            r"executed\s+by\s+([^,\n]+?)(?:,|\s+securing)",
            # WHEREAS commercial: "WHEREAS, ENTITY NAME, a [State] [type]"
            r"WHEREAS,\s+([^,\n]+?),\s+a\s+",
            # WHEREAS-by format: "WHEREAS, by a deed..., ENTITY, to secure a debt"
            r"([A-Z][^.\n]+?)\s+to\s+secure\s+a\s+debt\s+to\s",
            # Mortgagor format: "ENTITY (hereinafter called the "Mortgagor")"
            r"([^\n.]+?),?\s*\(hereinafter\s+called\s+the\s+.{0,2}Mortgagor",
            # HOA/condo: "indebtedness of NAME resulting from" or "NAME default in"
            r"indebtedness\s+of\s+([^\n]+?)\s+(?:resulting\s+from|default\s+in\s+the)",
            # Two-column table PDF: 3 consecutive single-symbol lines (bullet or OCR artifact)
            # then notice date, then borrower/grantor name
            r"[^\w\s]\s*\n[^\w\s]\s*\n[^\w\s]\s*\n+[^\n]+\n+([^\n]+)",
            # Table format: label alone on line, value on next non-empty line
            r"^(?:Borrower|Grantor|Trustor)\s*:\s*\n+\s*([^\n]+)",
            r"[Gg]rantor\s*(?:\(s\))?\s*:?\s*([^\n]+)",
            r"[Bb]orrower\s*:?\s*([^\n]+)",
            r"[Tt]rustor\s*:?\s*([^\n]+)",
        ]:
            m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if m:
                val = m.group(1).strip().rstrip(",.")
                # Skip if the value looks like a boilerplate label (ends with : or known label)
                if (len(val) > 2
                        and not val.endswith(":")
                        and not re.match(r"^(Address|Holder|Servicer|Trustee|Date|Lender|Borrower)\s*:", val, re.IGNORECASE)):
                    return val
        return None

    def _extract_grantee(self, text: str) -> Optional[str]:
        # Travis County format: "grantor(s) and LENDER, mortgagee"
        for pat in [
            r"grantor\(s\)\s+and\s+([^,\n]+),\s*mortgagee",
            r"mortgagee[:\s]+([^\n]+)",
            r"[Gg]rantee\s*:?\s*([^\n]+)",
            r"[Bb]eneficiary\s*:?\s*([^\n]+)",
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().rstrip(",.")
                if len(val) > 2:
                    return val
        return None

    def _extract_legal_description(self, text: str) -> Optional[str]:
        patterns = [
            r"[Ll]egal\s+[Dd]escription\s*:?\s*([^\n]+(?:\n[^\n]+){0,2})",
            r"(LOT\s+\d+[,\s]+BLOCK\s+\d+[^\n]+)",
            r"(TRACT\s+\d+[^\n]+TRAVIS\s+COUNTY[^\n]*)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().replace("\n", " ")
                if len(val) > 5:
                    return val
        return None

    def _extract_sale_date(self, text: str) -> Optional[date]:
        # Priority 1a: Sale Date label then value on SAME line
        m = re.search(r"\bDate\s+of\s+Sale\s*:\s*([A-Za-z]+)\s+(\d{1,2})[.,]\s+(\d{4})", text, re.IGNORECASE)
        if m:
            mn = m.group(1).lower()
            if mn in MONTHS:
                try:
                    return date(int(m.group(3)), MONTHS[mn], int(m.group(2)))
                except ValueError:
                    pass

        # Priority 1b: "Date:" label alone, value on next non-empty line (commercial PDF table format)
        m = re.search(r"^Date\s*:\s*\n+\s*([A-Za-z]+)\s+(\d{1,2})[.,]\s+(\d{4})", text, re.MULTILINE)
        if m:
            mn = m.group(1).lower()
            if mn in MONTHS:
                try:
                    return date(int(m.group(3)), MONTHS[mn], int(m.group(2)))
                except ValueError:
                    pass

        # Priority 1c: "Date: June 02, 2026" inline (OCR may use period instead of comma)
        m = re.search(r"\bDate\s*:\s*([A-Za-z]+)\s+(\d{1,2})[.,]\s+(\d{4})", text)
        if m:
            mn = m.group(1).lower()
            if mn in MONTHS:
                try:
                    return date(int(m.group(3)), MONTHS[mn], int(m.group(2)))
                except ValueError:
                    pass

        # Priority 2: "being Month D, YYYY" near sale context
        sale_context = re.search(
            r"[Ss]ale\s+[Dd]ate.*?being\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})",
            text, re.IGNORECASE | re.DOTALL
        )
        if sale_context:
            mn = sale_context.group(1).lower()
            if mn in MONTHS:
                try:
                    return date(int(sale_context.group(3)), MONTHS[mn], int(sale_context.group(2)))
                except ValueError:
                    pass

        # Priority 3: "Tuesday, June 2, 2026" or "on Tuesday, June 2, 2026"
        for pat in [
            r"(?:on\s+)?Tuesday[,\s]+([A-Za-z]+)\s+(\d{1,2})[.,]\s+(\d{4})",
            r"(?:first|1st)\s+Tuesday[,\s]+([A-Za-z]+)\s+(\d{1,2})[.,]\s+(\d{4})",
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                mn = m.group(1).lower()
                if mn in MONTHS:
                    try:
                        return date(int(m.group(3)), MONTHS[mn], int(m.group(2)))
                    except ValueError:
                        pass

        m = re.search(r"(?:first|1st)\s+Tuesday.*?([A-Za-z]+)\s+(\d{4})", text, re.IGNORECASE)
        if m:
            mn = m.group(1).lower()
            if mn in MONTHS:
                return self._first_tuesday(int(m.group(2)), MONTHS[mn])

        # Priority 3b: "on Month D[junk], YYYY" — HOA notices and OCR ordinal artifacts
        # Placed after Tuesday patterns so "recorded on May 15, 2018" doesn't shadow sale date
        m = re.search(
            r"\bon\s+([A-Za-z]+)\s+(\d{1,2})[^,A-Za-z\n]{0,6},\s+(\d{4})",
            text, re.IGNORECASE
        )
        if m:
            mn = m.group(1).lower()
            if mn in MONTHS:
                try:
                    return date(int(m.group(3)), MONTHS[mn], int(m.group(2)))
                except ValueError:
                    pass

        # Priority 4: "Sale Date: Month D, YYYY"
        m = re.search(r"[Ss]ale\s+[Dd]ate\s*:?\s*.*?([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", text, re.IGNORECASE | re.DOTALL)
        if m:
            mn = m.group(1).lower()
            if mn in MONTHS:
                try:
                    return date(int(m.group(3)), MONTHS[mn], int(m.group(2)))
                except ValueError:
                    pass

        # Priority 4b: "Foreclosure Sale" / "Date of Sale" section — two-column table PDFs
        # where label and value are separated; lazy [\s\S] skips any intervening text
        m = re.search(
            r"(?:Foreclosure Sale|Date\s+of\s+Sale)[\s\S]{0,500}?([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})",
            text, re.IGNORECASE
        )
        if m:
            mn = m.group(1).lower()
            if mn in MONTHS:
                try:
                    return date(int(m.group(3)), MONTHS[mn], int(m.group(2)))
                except ValueError:
                    pass

        # Priority 5: any "being Month D, YYYY"
        for m in re.finditer(r"being\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", text, re.IGNORECASE):
            mn = m.group(1).lower()
            if mn in MONTHS:
                try:
                    return date(int(m.group(3)), MONTHS[mn], int(m.group(2)))
                except ValueError:
                    continue
        return None

    def _first_tuesday(self, year: int, month: int) -> date:
        d = date(year, month, 1)
        days_until_tuesday = (1 - d.weekday()) % 7
        return date(year, month, 1 + days_until_tuesday)

    def _extract_loan_amount(self, text: str) -> Optional[str]:
        patterns = [
            r"[Oo]riginal\s+[Nn]ote\s+[Aa]mount\s*:?\s*\$?([\d,]+(?:\.\d{2})?)",
            r"[Oo]bligations?\s+[Ss]ecured\s*:?\s*\$?([\d,]+(?:\.\d{2})?)",
            r"[Nn]ote\s+[Aa]mount\s*:?\s*\$?([\d,]+(?:\.\d{2})?)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    def _extract_dot_recording_no(self, text: str) -> Optional[str]:
        patterns = [
            r"[Dd]eed\s+of\s+[Tt]rust.*?[Ii]nstrument\s+[Nn]o\.?\s*(\d{8,12})",
            r"[Dd]eed\s+of\s+[Tt]rust.*?[Dd]ocument\s+[Nn]o\.?\s*(\d{8,12})",
            r"[Rr]ecorded.*?[Ii]nstrument\s+[Nn]o\.?\s*(\d{8,12})",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                return m.group(1).strip()
        return None

    def _extract_substitute_trustee(self, text: str) -> Optional[str]:
        patterns = [
            # "appoints in their steed BARRETT DAFFIN FRAPPIER TURNER & ENGEL, LLP"
            r"appoints?\s+in\s+their\s+stee[d]?\s+([^\n]+?)(?:\s+whose|\s+as\s+substitute|\s*\n)",
            r"[Ss]ubstitute\s+[Tt]rustee\s*[:(]?\s*([^\n]+)",
            r"[Tt]rustee\s*:\s*([^\n]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().rstrip(",.")
                if len(val) > 2:
                    return val
        return None

    def _extract_attorney(self, text: str) -> Optional[str]:
        patterns = [
            r"[Aa]ttorney\s*:?\s*([^\n]+)",
            r"[Rr]eturnee\s*:?\s*([^\n]+)",
            r"[Ll]aw\s+[Ff]irm\s*:?\s*([^\n]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().rstrip(",.")
                if len(val) > 2:
                    return val
        return None
