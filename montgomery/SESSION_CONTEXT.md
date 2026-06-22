# Montgomery Session Context — 2026-05-26

## Current Position
EC2 run IN PROGRESS: 10 records targeting "Final  Try " sheet. Excel still loading (~3 min total).
- EC2 IP: 3.239.168.243 (us-east-1, t3.small, i-057319ccb3421a3a7)
- PID: 37777
- Log: `/home/ubuntu/run_10.log`
- Key: d:/Scrapper/montgomery-scraper.pem

## Monitor EC2
```bash
python monitor_run.py     # check status + tail log
python refresh_token.py   # re-auth Google if invalid_grant recurs
```

## Google Sheet
- ID: 1PE534MXnwlRqQoiukX8fCvtwamiKnT4JaiRsbBOb3DM
- OLD tab: "Montgomery" (100 records, wrong totals — formula was wrong)
- NEW tab: "Final  Try " (gid=695418404) — 10 fresh records target
- Link: https://docs.google.com/spreadsheets/d/1PE534MXnwlRqQoiukT8fCvtwamiKnT4JaiRsbBOb3DM/edit?gid=695418404

## Run Command (EC2 via redeploy_and_run.py or SSH)
```
python -m montgomery.main --file montgomery/downloads/Montgomery_Tax_Del_Raw_032726.xlsx --limit 10 --sheet "Final  Try "
```

## Fixes Applied This Session
1. **total_tax_due formula** → sum(TOT_PERCAN) not LEVY+PENDUE+INTDUE+PANDI_ATTY
   - PANDI_ATTY is attorney internal tracking field, NOT an additive fee
   - Verified: acct 130387 = $1,041.20 (Excel Mar 2026) vs $1,061.50 (live, 2mo interest delta)
2. **8 code review bugs** → float crash, YEAR KeyError, dead-page retry, None address, sheets O(n) cache fix, rstrip→removesuffix, PII log, OAuth hang guard
3. **EC2 deployment** → Tax Office unblocked from US East IP (actweb.acttax.com confirmed reachable)
4. **Tax nav fixed** → direct showdetail.jsp?can=ACCOUNT URL tried first; no-results detection; removed overbroad table a[href] selector
5. **--sheet CLI arg** → main.py now accepts --sheet "Tab Name"
6. **Google token** → full re-auth done, uploaded to EC2

## Key Blockers (remaining)
- Accounts like 0000080000xxx may not exist on ACTweb (personal property category?)
- Account 000000130387 (first normal account) should work fine on ACTweb
- last_payment_date will populate once navigation hits detail page correctly

## EC2 Cost
~$15/month always-on. To stop: `python -m awscli ec2 stop-instances --instance-ids i-057319ccb3421a3a7 --region us-east-1`

## Next Steps
1. Wait for 10-record run to complete (~15-20 min)
2. Verify "Final  Try " sheet — check last_payment_date + total_due accuracy
3. If good → run 100 records
4. Set up EC2 cron: Monday 6am weekly

## Recent Commits
```
9028f87 perf: try direct showdetail.jsp URL first, fall back to search form
1f21346 feat: add --sheet CLI arg, fix Tax detail nav selector, detect no-results
f81e9c9 fix: correct total_tax_due formula — use TOT_PERCAN not inflated sum
cd931fe fix: resolve 8 bugs from code review — crash guards, retry safety, PII, caching
db7e23f fix: address client feedback - MCAD validation, tax data accuracy, field fallbacks
```
