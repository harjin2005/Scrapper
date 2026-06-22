# **Travis County Foreclosure Scraper \- Task Instructions**

## **Project Overview**

Build an automated web scraping system that collects foreclosure data from Travis County, Texas Clerk of Courts online portal (searchable database) and compiles the information into a structured Google Sheets tracking spreadsheet.

**Loom Video:**  
[http://loom.com/share/e80906add3174ad7bbac5b711c255d36?focus\_title=1\&muted=1\&from\_recorder=1](http://loom.com/share/e80906add3174ad7bbac5b711c255d36?focus_title=1&muted=1&from_recorder=1) 

## **Objective**

Create a fully automated pipeline that:

1. Searches Travis County Clerk portal for Notice of Substitute Trustee Sale documents  
2. Downloads all foreclosure PDFs for the current month  
3. Extracts property and foreclosure data from each PDF  
4. Cross-references property data with Travis CAD for appraisal values  
5. Cross-references with Travis County Tax Office for delinquent taxes  
6. Updates a Google Sheets spreadsheet with enriched data  
7. Runs automatically daily without manual intervention

## **Part 1: Automated Search and PDF Download from Clerk Portal**

### **Target Website (Travis County Clerk of Courts)**

**Search Portal URL:** https://www.tccsearch.org/RealEstate/SearchEntry.aspx?e=newSession

### **Search Strategy**

**Document Type:**

* **NOTICE OF SUBSTITUTE TRUSTEE SALE**

**Date Range:**

* Search by current month and current year  
* Example: If today is May 13, 2026 → search May 2026  
* Run daily to capture new filings

### **Step 1A: Navigate to Search Portal**

8. Go to: https://www.tccsearch.org/RealEstate/SearchEntry.aspx?e=newSession  
9. This opens the Real Estate Index Search Entry page

### **Step 1B: Configure Search Parameters**

10. **Document Type Field:**  
* Select or enter: 'NOTICE OF SUBSTITUTE TRUSTEE SALE'  
* This may be a dropdown or text input field

11. **Date Range Fields:**  
* Filed Date From: First day of current month (e.g., 05/01/2026)  
* Filed Date To: Current date or last day of current month (e.g., 05/13/2026 or 05/31/2026)  
* Use MM/DD/YYYY format

12. Leave all other fields blank (no grantor, grantee, or address filters needed)

### **Step 1C: Execute Search and Retrieve Results**

13. Click 'Search' or 'Submit' button  
14. Review search results page showing all matching documents  
15. Results typically show: Instrument Number, Document Type, Filing Date, Grantor, Grantee, Property Address

### **Step 1D: Download PDFs**

For each result in the search:

16. Click on the document link or Instrument Number  
17. Download the PDF of the Notice of Substitute Trustee Sale  
18. Note the Instrument Number for file naming

### **Step 1E: Handle Pagination (if applicable)**

* If results span multiple pages, navigate through all pages  
* Download PDFs from each page  
* Track page numbers to ensure complete collection

### **Step 1F: PDF Storage**

**Google Drive Location:** My Drive \> Scrapping Task \> Task 4: Travis County \> PDFs \> \[YYYY-MM-DD\]

**Naming Convention:**

* \[InstrumentNumber\]\_NOTICE\_OF\_SUBSTITUTE\_TRUSTEE\_SALE.pdf  
* Example: 2026012345\_NOTICE\_OF\_SUBSTITUTE\_TRUSTEE\_SALE.pdf  
* Organize by date: Create dated folder for each day's downloads

## **Part 2: Automated Data Extraction from PDFs**

### **PDF Content Overview**

Each 'Notice of Substitute Trustee Sale' PDF contains:

* Property address and legal description  
* Sale date, time, and location  
* Grantor (property owner) name  
* Grantee (lender/beneficiary) name  
* Original loan amount  
* Deed of trust recording information  
* Substitute trustee information

### **Data to Extract from Each PDF**

| Field | Where to Find in PDF |
| :---- | :---- |
| Instrument No. | Document number from search results or PDF header |
| Property Address | Under 'Property' or 'Commonly known as' section |
| Legal Description | Lot, Block, Subdivision \- usually after property address |
| Sale Date | Date, time, and place of sale section (first Tuesday) |
| Sale Location | County courthouse or specific address in Austin |
| Grantor(s) | Property owner names \- under 'Grantor' or 'Trustor' |
| Grantee(s) | Lender/beneficiary names \- under 'Grantee' or 'Beneficiary' |
| Original Loan Amount | In 'Obligations Secured' or 'Note' section |
| Deed of Trust Date | Recording date of original deed of trust |
| Deed of Trust Recording \# | Document/Instrument number for deed of trust |
| Substitute Trustee | Trustee firm name and contact |
| Returnee/Attorney | Law firm or attorney handling foreclosure |
| Notary | Notary public information if listed |
| Date Received | Filing date from search results |

### **Extraction Method**

Use PDF parsing libraries to extract text:

* Python: PyPDF2, pdfplumber, or tabula-py  
* Node.js: pdf-parse or pdf2json  
* Use regex patterns to find specific fields  
* Handle variations in PDF formatting

## **Part 3: Automated Cross-Referencing with Travis CAD**

### **Travis Central Appraisal District (Travis CAD)**

**URL:** https://travis.prodigycad.com/property-search

**Primary Search Method: Property Address**

* Enter full property address from foreclosure PDF  
* Example: '1234 MAIN STREET, AUSTIN, TX 78701'  
* Click Search

**Fallback Search Methods (if address fails):**

19. Search by Owner Name (use grantor names from PDF)  
20. Search by Account Number (if found in previous lookups)  
21. Search by Legal Description (Lot/Block/Subdivision)

**Data to Extract from Travis CAD:**

* Property Status (Active, Inactive, etc.)  
* Appraised Value (Market Value)  
* Account Number  
* Property details (confirm legal description)

## **Part 4: Automated Cross-Referencing with Tax Office**

### **Travis County Tax Office \- Account Search**

**URL:** https://tax-office.traviscountytx.gov/properties/taxes/account-search

**Search Method:**

* Search by property address  
* Or search by account number (from Travis CAD)  
* Look for delinquent tax amounts

**Data to Extract:**

* Total taxes due (if delinquent)  
* Years of delinquency  
* If no delinquent taxes found, enter '0' or 'Current'

## **Part 5: Data Output & Organization**

### **Google Sheets Output**

**File:** travis\_county\_foreclosures (Google Sheets)  
**Location:** My Drive \> Scrapping Task \> Task 4: Travis County

### **Required Spreadsheet Columns (in order)**

| Column | Description |
| :---- | :---- |
| Index \# | Row number |
| Instrument No. | Document ID from clerk portal |
| Address | Full property address |
| County | Travis |
| Sale Type | Substitute Trustee Sale |
| Sale Date | Date of scheduled sale (first Tuesday) |
| Document Type | Notice of Substitute Trustee Sale |
| Grantor(s) | Property owner names from PDF |
| Grantee(s) | Lender/trustee names from PDF |
| Legal Description | Lot, block, subdivision from PDF |
| Related Document No. | Deed of Trust recording number |
| Related Doc Type | Deed of Trust |
| Substitute Trustee | Trustee firm name from PDF |
| Returnee/Attorney | Attorney/law firm from PDF |
| Notary | Notary information if listed in PDF |
| Date Received | Filing date from clerk portal |
| PDF Link | Google Drive link to downloaded PDF |
| Property Status | From Travis CAD (Active/Inactive) |
| Account Number | From Travis CAD |
| Created At | Timestamp when added to sheet |
| Updated At | Timestamp of last update |
| Taxes Due | Delinquent tax amount from Tax Office |
| Appraised Value | Property value from Travis CAD |

### **Important Rules**

* Only add NEW records (check Instrument No. for duplicates)  
* Append new rows to bottom of spreadsheet  
* Preserve all existing data  
* Update 'Updated At' timestamp on each run  
* Include clickable Google Drive links to PDFs

### **Google Drive Organization**

Folder Structure:  
My Drive/  
  └── Scrapping Task/  
      └── Task 4: Travis County/  
          ├── travis\_county\_foreclosures (Google Sheet)  
          └── PDFs/  
              ├── 2026-05-13/  
              │   ├── 2026012345\_NOTICE\_OF\_SUBSTITUTE\_TRUSTEE\_SALE.pdf  
              │   ├── 2026012346\_NOTICE\_OF\_SUBSTITUTE\_TRUSTEE\_SALE.pdf  
              │   └── ...  
              ├── 2026-05-14/  
              └── 2026-05-15/

## **Data Validation & Quality Assurance**

### **Required Field Validation**

The system must validate that these REQUIRED fields are extracted for every record:

* Instrument No. (100% required)  
* Address (100% required)  
* Grantor(s) (100% required)  
* Sale Date (100% required)  
* PDF Link (100% required)

### **Acceptance Criteria**

**✅ PASS Criteria:**

* ≥95% of all required fields successfully extracted  
* 100% of PDF downloads successful  
* 100% of Addresses extracted  
* ≥90% of Travis CAD lookups successful  
* ≥85% of Tax Office lookups successful

**⚠️ REVIEW Criteria:**

* 85-94% of required fields extracted  
* 80-89% of Travis CAD lookups successful  
* 75-84% of Tax Office lookups successful

**❌ FAIL Criteria:**

* \<85% of any required field extracted  
* \<95% of PDF downloads successful  
* Any duplicate Instrument Numbers

## **Automation Requirements**

### **Daily Schedule**

* **Frequency:** Once per day  
* **Recommended Time:** Early morning (6:00-8:00 AM) to capture previous day's filings  
* **Days:** Monday through Friday (business days only)

### **Travis County Specific Notes**

* Search portal requires form submission with date range  
* Always search current month (first day to current date)  
* May require handling CAPTCHA or session management  
* Volume: Unknown \- estimate similar to other major Texas counties

### **Automation Method**

Choose any scheduling method that works reliably:

* Cron job (Linux/Mac) \- run daily at specified time  
* Task Scheduler (Windows) \- run daily Monday-Friday  
* Cloud scheduler (AWS Lambda, Google Cloud Functions, Azure Functions)  
* Any other automated scheduling solution

### **Error Handling Requirements**

The system must handle:

* County website downtime or slow response  
* Search form submission failures  
* CAPTCHA challenges (may require manual intervention or CAPTCHA solving service)  
* Session timeout or authentication issues  
* PDF download failures (retry 3 times)  
* Pagination errors  
* Malformed or corrupt PDFs  
* Variations in PDF formatting  
* Missing fields in PDFs  
* Travis CAD lookup failures  
* Tax Office lookup failures  
* Google Drive upload failures  
* Google Sheets API rate limits  
* Authentication failures

### **Logging Requirements**

Create a log file that tracks:

* Date/time of each run  
* Date range searched (e.g., '05/01/2026 to 05/13/2026')  
* Number of search results found  
* Number of PDFs downloaded successfully  
* Field extraction success rates  
* Failed PDF downloads with instrument numbers  
* Failed Travis CAD lookups with addresses  
* Failed Tax Office lookups with addresses  
* Total runtime  
* Success/failure status with completion percentage

## **Technical Deliverables**

### **Required Outputs**

22. **Working scraper script** (any programming language)  
23. **Setup documentation** (README with installation instructions)  
24. **Configuration file** for Google APIs, search parameters, and schedule settings  
25. **Dependencies file** (requirements.txt, package.json, or equivalent)  
26. **Automation setup** (cron job, Task Scheduler, or equivalent configured for daily execution)  
27. **Test run results** (logs showing successful execution and data validation)

### **Technical Specifications**

* Must run headless (no manual browser interaction except for CAPTCHA if required)  
* Must authenticate with Google APIs securely  
* Must handle search form submission programmatically  
* Must handle PDF text extraction reliably  
* Must handle pagination if results span multiple pages  
* Must deduplicate records before adding to spreadsheet  
* Must validate extracted data  
* Must be maintainable (clean, commented code)  
* **Language choice:** Python, JavaScript/Node.js, C\#, Java, Ruby, etc. \- whatever delivers the functionality

### **Recommended Technologies (Optional)**

* **Web automation:** Selenium, Puppeteer, Playwright for form submission and navigation  
* **PDF parsing:** PyPDF2, pdfplumber, tabula-py (Python) or pdf-parse (Node.js)  
* **HTTP requests:** requests (Python) or axios (Node.js)  
* **Google APIs:** Official Google client libraries  
* **Scheduling:** OS-level schedulers or cloud-based solutions

## **Key Differences from Other Counties**

### **Travis County Characteristics**

28. **Data Source:** Searchable clerk portal (similar to Harris County)  
29. **Document Name:** 'Notice of Substitute Trustee Sale'  
30. **Search Method:** Form submission with document type and date range filters  
31. **Frequency:** Daily (Monday-Friday)  
32. **CAD:** Travis CAD available online  
33. **Tax Office:** ONLINE PORTAL AVAILABLE  
34. **Complexity:** Medium \- requires form automation, similar to Harris County

### **Comparison with Other Counties**

* **Harris County:** Similar portal-based search approach  
* **Bell County:** Direct PDF downloads (simpler)  
* **Williamson County:** Direct PDF portal with monthly organization

## **Success Criteria**

* ✅ Scraper runs automatically daily (Monday-Friday)  
* ✅ Search form submitted successfully with correct parameters  
* ✅ All search results retrieved (including pagination)  
* ✅ All PDFs downloaded successfully  
* ✅ All required data fields extracted accurately from PDFs  
* ✅ PDFs organized in Google Drive by date  
* ✅ Google Sheets updated with new records  
* ✅ Cross-referencing with Travis CAD automated  
* ✅ Cross-referencing with Tax Office automated  
* ✅ No duplicate records created  
* ✅ System handles errors gracefully  
* ✅ Data validation shows ≥95% field completion  
* ✅ Code is clean, documented, and maintainable  
* ✅ Complete documentation provided  
* ✅ Failed operations logged and reported

## **Submission Requirements**

35. Complete source code (zipped or GitHub repository)  
36. README.md with comprehensive setup instructions  
37. Dependencies file (requirements.txt, package.json, or equivalent)  
38. Configuration file template with clear instructions  
39. Sample output showing: Screenshot of populated Google Sheet, Screenshot of Google Drive folder with organized PDFs  
40. Log file from test run showing: Successful search form submission, Successful PDF downloads, Successful data extraction, Successful Travis CAD and Tax Office lookups, Data validation results, Any failed operations  
41. Brief demonstration (video or written) showing: Automated search working, PDF extraction working, Cross-referencing working, Data validation report

