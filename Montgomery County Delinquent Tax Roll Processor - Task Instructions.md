# **Montgomery County Delinquent Tax Roll Processor \- Task Instructions**

## **Project Overview**

Build an automated data processing system that downloads Montgomery County's delinquent tax roll Excel file, enriches the data with property details from Montgomery CAD and tax information from the Tax Office, and compiles everything into a structured Google Sheets tracking spreadsheet.

## **Objective**

Create a fully automated pipeline that:

1. Downloads the latest Delinquent Tax Roll Excel file from Montgomery County Tax Office  
2. Processes and extracts property data from the Excel file  
3. Cross-references each property with Montgomery CAD for property details  
4. Cross-references with Montgomery County Tax Office for current tax status  
5. Updates a Google Sheets spreadsheet with enriched data  
6. Runs automatically when new tax rolls are published

## **Important: Montgomery County's Different Focus**

**Important Note:** Montgomery County DOES have foreclosure notices like other counties. However, for this task, we are NOT tracking foreclosure notices. Instead, we are tracking properties with delinquent taxes from the county's comprehensive 'Delinquent Tax Roll' Excel file. This gives us earlier-stage opportunities before properties reach foreclosure.

**What We're Tracking:**

* **Delinquent Tax Properties** \- properties with unpaid property taxes  
* **Earlier Stage Opportunities** \- these may become foreclosures later  
* **Tax Lien Opportunities** \- different investment strategy than foreclosures

**Approach for This Task:**

* **NO foreclosure PDFs to download**  
* **START with a bulk Excel file** containing all delinquent tax properties  
* Process is data enrichment rather than document scraping  
* Focus on tax delinquency, not foreclosure status

**Release Schedule:**

* Montgomery County typically updates the delinquent tax roll periodically throughout the year  
* Check the county website regularly for new releases (monitor weekly or monthly)  
* File is published with date stamp (e.g., 'Delinquent Tax Roll \- Detail as of May 11, 2026')

## **Part 1: Download Delinquent Tax Roll Excel File**

### **Target Website**

**Forms & Downloads Page:** https://www.mctotx.org/property/property\_tax\_forms.php\#undefined

### **Step 1A: Navigate to Download Page**

7. Go to: https://www.mctotx.org/property/property\_tax\_forms.php\#undefined  
8. Scroll to the section labeled 'Property Tax Forms & Downloads'  
9. Locate the link for 'Delinquent Tax Roll \- Detail'

### **Step 1B: Identify Latest Tax Roll**

The file will have a name pattern like:

* 'Delinquent Tax Roll \- Detail as of \[Date\] (XLSX, \[Size\])'  
* Example: 'Delinquent Tax Roll \- Detail as of May 11, 2026 (XLSX, 75400 KB)'

**Important:**

* Note the 'as of' date \- this tells you when the data was current  
* Track this date to detect when new files are published  
* Only download if the date is newer than your last processed file

### **Step 1C: Download the Excel File**

10. Click the download link  
11. The file URL pattern is typically: https://www.mctotx.org/Document%20Center/...  
12. Save the file with a date-stamped name for tracking  
13. Example filename: Montgomery\_Delinquent\_Tax\_Roll\_2026-05-11.xlsx

### **Step 1D: Storage Location**

**Local Storage:** Save to working directory for processing  
**Google Drive Backup:** My Drive \> Scrapping Task \> Task 5: Montgomery County \> Source Files \> \[YYYY-MM-DD\]

## **Part 2: Process Excel Data**

### **Excel File Structure**

The delinquent tax roll Excel file typically contains columns such as:



* Account Number  
* Owner Name  
* Property Address  
* Legal Description  
* Tax Year(s)  
* Amount Due  
* Penalties and Interest  
* Attorney Fees (if applicable)  
* Total Amount Due

**Note:** The exact column names and structure may vary. Inspect the actual file on first download to map columns correctly.

### **Step 2A: Load and Validate Excel File**

14. Open the Excel file using appropriate library (pandas, openpyxl, xlsx, etc.)  
15. Identify the data sheet (may have multiple sheets \- typically first sheet contains data)  
16. Verify expected columns are present  
17. Check row count (typical file contains thousands to tens of thousands of properties)

### **Step 2B: Extract Required Data**

For each row in the Excel file, extract:

| Field | Source |
| :---- | :---- |
| Account Number | Excel file \- Account Number column |
| Owner Name | Excel file \- Owner Name column |
| Property Address | Excel file \- Property Address column |
| Legal Description | Excel file \- Legal Description column |
| Tax Year(s) | Excel file \- Tax Year column |
| Amount Due | Excel file \- Amount Due or Total Due column |
| Penalties/Interest | Excel file \- separate columns or included in total |
| Attorney Fees | Excel file \- if applicable |

### **Step 2C: Data Cleaning and Standardization**

* Standardize address format (remove extra spaces, fix abbreviations)  
* Clean owner names (handle multiple owners, estates, trusts)  
* Parse amounts as numbers (remove $, commas)  
* Handle missing or null values appropriately

## **Part 3: Cross-Reference with Montgomery CAD**

### **Montgomery Central Appraisal District (MCAD)**

**URL:** https://mcad-tx.org/

### **Search Strategy**

**Primary Search Method: Account Number**

* Use account number from Excel file  
* This is the most reliable search method

**Fallback Search Methods (if account number fails):**

18. Search by Property Address  
19. Search by Owner Name  
20. Search by Legal Description

### **Data to Extract from MCAD**

* **Account Number** (verify matches DTR Excel)  
* **Property Owner Name** (verify matches DTR Excel)  
* **Property Address** (verify matches DTR Excel)  
* **Property Mailing Address** (if different from property address)  
* **Property Type** (Residential, Commercial, Land, Agricultural, etc.)  
* **Property Type Code** (classification code)  
* **Appraised Value** (Market Value or Assessed Value)  
* **Lot Size** (square feet or acres)  
* **Legal Description** (Lot, Block, Subdivision)  
* **Owner Contact Number** (if available publicly)  
* **Owner Email** (if available publicly \- may not be)

## **Part 4: Cross-Reference with Tax Office**

### **Montgomery County Tax Office \- Property Search**

**URL:** https://actweb.acttax.com/act\_webdev/montgomery/index.jsp

### **Search Strategy**

**Primary Search Method: Account Number**

* Use account number from Excel file  
* Most direct and reliable method

**Fallback Search Methods:**

21. Search by Property Address  
22. Search by Owner Name


### **Data to Extract from Tax Office**

* **Account Number** (verify matches DTR Excel and MCAD)  
* **Last Tax Payment Date** (most recent payment received)  
* **Initial Delinquency Year** (first year taxes went unpaid)  
* **Number of Years Behind Taxes** (Sequence \# \- count of delinquent years)  
* **Cause or Tax Lawsuit \#** (if property in litigation)  
* **Cause Date** (date tax lawsuit was filed)  
* **Total Tax Due** (Total Due, Total Tax, or Total Delinquency Due \- use most current)

**Important Note:**  
The Tax Office portal may show more current information than the Excel file. The Excel file is a snapshot as of a specific date, while the portal shows real-time data. Always use the Tax Office data as the most current source.

## **Part 5: Data Output & Organization**

### **Google Sheets Output**

**File:** montgomery\_county\_delinquent\_properties (Google Sheets)  
**Location:** My Drive \> Scrapping Task \> Task 5: Montgomery County

### **Required Spreadsheet Columns (in order)**

**Note:** Data may come from Delinquent Tax Roll Excel (DTR), Montgomery CAD (MCAD), or Tax Office (TAX). Use the most complete/accurate source available.

| Column | Data Source & Description |
| :---- | :---- |
| Account Number | Primary from DTR Excel, verify with MCAD/TAX |
| Property Owner | From DTR Excel, verify with MCAD |
| Property Address | From DTR Excel, verify with MCAD |
| Property Mailing Address | From MCAD or TAX (if different from property address) |
| Property Type | From MCAD (Residential, Commercial, Land, Agricultural, etc.) |
| Property Type Code | From MCAD (classification code) |
| Lot Size | From MCAD (square feet or acres) |
| Legal Description | From DTR Excel or MCAD (Lot, Block, Subdivision) |
| Owner Contact Number | From MCAD if available |
| Email | From MCAD if available (may not be public) |
| Last Tax Payment Date | From TAX Office |
| Initial Delinquency Year | From DTR Excel or TAX Office (first year taxes went unpaid) |
| Number of Years Behind Taxes | From DTR Excel or TAX (Sequence \# \- count of delinquent years) |
| Cause or Tax Lawsuit \# | From DTR Excel or TAX Office (if property in litigation) |
| Cause Date | From TAX Office (date lawsuit filed) |
| Property Appraised Value | From MCAD (Market Value, Assessed Value, or Appraised Value) |
| Total Tax Due | From DTR Excel or TAX Office (Total Due, Total Tax, Total Delinquency Due \- use most current) |
| Property County | Montgomery |
| Excel File Date | Date from DTR Excel filename (e.g., 'as of May 11, 2026') |
| Created At | Timestamp when first added to sheet |
| Updated At | Timestamp of last update |

### **Important Rules**

* **New vs. Update Logic:**  
*   • If Account Number exists: UPDATE the row with new data  
*   • If Account Number is new: ADD new row  
* Track Excel File Date to know which tax roll version the data came from  
* Preserve historical data (don't delete old records)  
* Update 'Updated At' timestamp on each run

### **Google Drive Organization**

Folder Structure:  
My Drive/  
  └── Scrapping Task/  
      └── Task 5: Montgomery County/  
          ├── montgomery\_county\_delinquent\_properties (Google Sheet)  
          └── Source Files/  
              ├── 2026-05-11/  
              │   └── Montgomery\_Delinquent\_Tax\_Roll\_2026-05-11.xlsx  
              ├── 2026-06-15/  
              └── 2026-07-20/

## **Data Validation & Quality Assurance**

### **Required Field Validation**

The system must validate that these REQUIRED fields are extracted for every record:

* Account Number (100% required)  
* Address (100% required)  
* Owner Name (100% required)  
* Amount Due (100% required)

### **Acceptance Criteria**

**✅ PASS Criteria:**

* 100% of Excel rows processed  
* ≥95% of all required fields successfully extracted  
* 100% of Account Numbers extracted  
* ≥90% of MCAD lookups successful  
* ≥85% of Tax Office lookups successful

**⚠️ REVIEW Criteria:**

* 85-94% of required fields extracted  
* 80-89% of MCAD lookups successful  
* 75-84% of Tax Office lookups successful

**❌ FAIL Criteria:**

* \<85% of any required field extracted  
* \<95% of Excel rows processed  
* Any duplicate Account Numbers (should update, not duplicate)

## **Automation Requirements**

### **Monitoring Schedule**

* **Frequency:** Weekly monitoring to detect new Excel file releases  
* **Recommended:** Every Monday morning check for new file  
* **Processing:** Only process when a NEW file is detected (check 'as of' date)

### **Montgomery County Specific Notes**

* **No daily updates** \- delinquent tax roll is published periodically  
* Excel file may contain thousands to tens of thousands of rows  
* Processing time may be hours depending on file size and lookup speed  
* Implement rate limiting for MCAD and Tax Office lookups to avoid blocking  
* Consider batch processing with progress tracking

### **Two-Phase Automation Strategy**

**Phase 1: File Detection (Weekly)**

* Check county website for new Excel file  
* Compare 'as of' date with last processed date  
* If new file detected, download it  
* Trigger Phase 2 processing

**Phase 2: Data Processing (On-Demand)**

* Load Excel file  
* Process all rows with cross-referencing  
* Update Google Sheets  
* Generate completion report

### **Automation Method**

Choose any scheduling method that works reliably:

* Cron job (Linux/Mac) \- run weekly file check  
* Task Scheduler (Windows) \- run every Monday  
* Cloud scheduler (AWS Lambda, Google Cloud Functions, Azure Functions)  
* Any other automated scheduling solution

### **Error Handling Requirements**

The system must handle:

* County website downtime  
* Excel file download failures  
* Corrupted or malformed Excel files  
* Changed Excel column structure (must detect and adapt)  
* Missing required columns in Excel  
* MCAD lookup failures (retry 3 times)  
* Tax Office lookup failures (retry 3 times)  
* Rate limiting / IP blocking (implement delays)  
* Google Drive upload failures  
* Google Sheets API rate limits  
* Authentication failures

### **Progress Tracking & Resumability**

**Important for Large Files:**

* Track progress (e.g., 'Processed 1,500 / 10,000 properties')  
* Save checkpoint after every N records (e.g., every 100\)  
* If process crashes, resume from last checkpoint  
* Log which account numbers have been processed

### **Logging Requirements**

Create a log file that tracks:

* Date/time of each run  
* Excel file date processed (e.g., 'May 11, 2026')  
* Total rows in Excel file  
* Number of rows successfully processed  
* Field extraction success rates  
* Number of MCAD lookups successful/failed  
* Number of Tax Office lookups successful/failed  
* Failed account numbers with error reasons  
* Total runtime  
* Success/failure status with completion percentage

## **Network Access Requirements**

### **Important: VPN May Be Required**

County government websites may restrict access from certain IP addresses or geographic locations. You may need to use a VPN to access Montgomery County systems.

**Potential Access Issues:**

* International IP addresses may be blocked or limited  
* Some county portals may require US-based IP addresses  
* Corporate/shared IPs may be rate-limited or blocked  
* VPN detection may block certain commercial VPN services

**Recommended Solutions:**

* Use a US-based VPN service (e.g., NordVPN, ExpressVPN, ProtonVPN with US server)  
* Deploy on US-based cloud infrastructure (AWS US regions, Google Cloud US, Azure US)  
* Use residential proxy services if commercial VPNs are blocked  
* Have backup VPN options in case primary is blocked

### **Testing Access Before Development**

**CRITICAL:** Test access to all county websites BEFORE starting development to avoid wasted effort.

**Access Testing Checklist:**

23. Test from your current IP address/location  
24. Try accessing:  
*   • Tax forms page: https://www.mctotx.org/property/property\_tax\_forms.php  
*   • MCAD: https://mcad-tx.org/  


*   • Tax Office: https://actweb.acttax.com/act\_webdev/montgomery/index.jsp  
25. If blocked, enable VPN with US server location (preferably Texas)  
26. Test again with VPN enabled  
27. Verify you can:  
*   • Load all pages successfully  
*   • Download the Excel file  
*   • Search MCAD for a test property  
*   • Search Tax Office for a test account  
28. Document which VPN/server location works for consistent use

### **Implementation Considerations**

* **Automated VPN Connection:** Configure your script to automatically connect to VPN before starting  
* **VPN Reliability:** Build in VPN connection checks and auto-reconnect if connection drops  
* **Cloud Deployment:** If deploying to cloud, choose US-based regions to avoid VPN need  
* **Credentials:** Store VPN credentials securely if automation requires VPN

## **Technical Deliverables**

### **Required Outputs**

29. **Working processor script** (any programming language)  
30. **Setup documentation** (README with installation instructions)  
31. **Configuration file** for Google APIs, URLs, and schedule settings  
32. **Dependencies file** (requirements.txt, package.json, or equivalent)  
33. **Automation setup** (cron job or scheduler configured for weekly file check)  
34. **Test run results** (logs showing successful execution and data validation)

### **Technical Specifications**

* Must handle Excel files programmatically (XLSX format)  
* Must authenticate with Google APIs securely  
* Must implement rate limiting for web lookups  
* Must track processing progress with checkpoints  
* Must detect duplicate account numbers and update (not create new rows)  
* Must validate extracted data  
* Must handle large datasets efficiently (10,000+ rows)  
* Must be maintainable (clean, commented code)  
* **Language choice:** Python, JavaScript/Node.js, C\#, Java, Ruby, etc. \- whatever delivers the functionality

### **Recommended Technologies (Optional)**

* **Excel processing:** pandas, openpyxl (Python) or xlsx, exceljs (Node.js)  
* **Web scraping:** BeautifulSoup, Selenium (Python) or Puppeteer, Cheerio (Node.js)  
* **HTTP requests:** requests (Python) or axios (Node.js)  
* **Google APIs:** Official Google client libraries  
* **Scheduling:** OS-level schedulers or cloud-based solutions

## **Key Differences from Other County Tasks**

### **Montgomery County Task Characteristics**

35. **Focus:** Delinquent tax properties (NOT foreclosure notices)  
36. **Data Source:** Bulk Excel file (NOT individual notices)  
37. **Stage:** Earlier-stage opportunities (tax delinquency before foreclosure)  
38. **Approach:** Data enrichment (not document scraping)  
39. **Frequency:** Periodic (check weekly, process when new file detected)  
40. **CAD:** MCAD available online  
41. **Tax Office:** ONLINE PORTAL AVAILABLE  
42. **Volume:** Large batches (thousands to tens of thousands per file)  
43. **Complexity:** High \- bulk processing with extensive cross-referencing

### **Comparison with Other County Tasks**

* **Harris/Travis:** Track foreclosure notices \- portal-based search with daily updates  
* **Bell/Williamson:** Track foreclosure notices \- direct PDF downloads  
* **Montgomery:** Track delinquent tax properties \- bulk Excel file processing (different investment opportunity)

## **Success Criteria**

* ✅ System checks for new Excel files weekly  
* ✅ New Excel files detected and downloaded automatically  
* ✅ 100% of Excel rows processed  
* ✅ All required data fields extracted accurately  
* ✅ Cross-referencing with MCAD automated  
* ✅ Cross-referencing with Tax Office automated  
* ✅ Google Sheets updated (new rows added, existing rows updated)  
* ✅ No duplicate Account Numbers created  
* ✅ Progress tracking and checkpoint system working  
* ✅ System handles errors gracefully  
* ✅ Data validation shows ≥95% field completion  
* ✅ Rate limiting prevents IP blocking  
* ✅ Code is clean, documented, and maintainable  
* ✅ Complete documentation provided  
* ✅ Failed operations logged and reported

## **Submission Requirements**

44. Complete source code (zipped or GitHub repository)  
45. README.md with comprehensive setup instructions  
46. Dependencies file (requirements.txt, package.json, or equivalent)  
47. Configuration file template with clear instructions  
48. Sample output showing: Screenshot of populated Google Sheet, Screenshot of source Excel file  
49. Log file from test run showing: Successful Excel download, Successful Excel processing, Successful MCAD lookups, Successful Tax Office lookups, Data validation results, Progress tracking, Any failed operations  
50. Brief demonstration (video or written) showing: Automated file detection working, Excel processing working, Cross-referencing working, Progress tracking, Data validation report

