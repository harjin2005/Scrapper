from __future__ import annotations
import re
from datetime import date
from pathlib import Path
from typing import Optional
import pdfplumber
from scraper.models import ForeclosureRecord
from scraper.logger import get_logger

log = get_logger("pdf_extractor")

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


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
        return "\n".join(pages_text)

    def _extract_instrument_no(self, text: str, filename: str) -> str:
        patterns = [
            r"Instrument\s+No\.?\s*:?\s*(\d{8,12})",
            r"Document\s+No\.?\s*:?\s*(\d{8,12})",
            r"Inst\.?\s+No\.?\s*:?\s*(\d{8,12})",
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
        patterns = [
            r"[Cc]ommonly\s+known\s+as\s+([^\n]+)",
            r"[Pp]roperty\s+[Aa]ddress\s*:?\s*([^\n]+)",
            r"[Pp]roperty\s*:.*?([0-9]+\s+\w+[^\n,]+(?:,\s*\w+\s*,?\s*TX[^\n]*)?)",
            r"([0-9]+\s+[A-Z][A-Z\s]+(?:STREET|DRIVE|LANE|AVE|ROAD|BLVD|WAY|COURT|CIR|DR|ST|LN|RD|CT)[^\n,]*(?:,\s*AUSTIN[^\n]*)?)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                addr = m.group(1).strip().rstrip(".")
                if len(addr) > 5:
                    return addr
        return None

    def _extract_grantor(self, text: str) -> Optional[str]:
        patterns = [
            r"[Gg]rantor\s*:?\s*([^\n]+)",
            r"[Tt]rustor\s*:?\s*([^\n]+)",
            r"[Oo]wner\s*:?\s*([^\n]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().rstrip(",.")
                if len(val) > 2:
                    return val
        return None

    def _extract_grantee(self, text: str) -> Optional[str]:
        patterns = [
            r"[Gg]rantee\s*:?\s*([^\n]+)",
            r"[Bb]eneficiary\s*:?\s*([^\n]+)",
            r"[Ll]ender\s*:?\s*([^\n]+)",
        ]
        for pat in patterns:
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
        # Priority 1: explicit "being Month D, YYYY" near sale context
        sale_context = re.search(
            r"[Ss]ale\s+[Dd]ate.*?being\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})",
            text, re.IGNORECASE | re.DOTALL
        )
        if sale_context:
            month_name = sale_context.group(1).lower()
            if month_name in MONTHS:
                try:
                    return date(int(sale_context.group(3)), MONTHS[month_name], int(sale_context.group(2)))
                except ValueError:
                    pass

        # Priority 2: "first Tuesday of Month YYYY"
        pat2 = r"(?:first|1st)\s+Tuesday.*?([A-Za-z]+)\s+(\d{4})"
        m = re.search(pat2, text, re.IGNORECASE)
        if m:
            month_name = m.group(1).lower()
            if month_name in MONTHS:
                return self._first_tuesday(int(m.group(2)), MONTHS[month_name])

        # Priority 3: "Sale Date: Month D, YYYY"
        sale_date_pat = r"[Ss]ale\s+[Dd]ate\s*:?\s*.*?([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})"
        m = re.search(sale_date_pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            month_name = m.group(1).lower()
            if month_name in MONTHS:
                try:
                    return date(int(m.group(3)), MONTHS[month_name], int(m.group(2)))
                except ValueError:
                    pass

        # Priority 4: any "being Month D, YYYY"
        pat = r"being\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})"
        for m in re.finditer(pat, text, re.IGNORECASE):
            month_name = m.group(1).lower()
            if month_name in MONTHS:
                try:
                    return date(int(m.group(3)), MONTHS[month_name], int(m.group(2)))
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
            r"[Ss]ubstitute\s+[Tt]rustee\s*:\s*([^\n]+)",
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
