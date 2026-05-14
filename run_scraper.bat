@echo off
REM Travis County Foreclosure Scraper — daily launcher
REM Runs main.py and appends all output to logs\last_run.log

cd /d "D:\Scrapper"

REM Ensure logs directory exists
if not exist "logs" mkdir logs

echo ============================= >> logs\last_run.log
echo Run started: %DATE% %TIME% >> logs\last_run.log
echo ============================= >> logs\last_run.log

"C:\Users\harji\AppData\Local\Programs\Python\Python310\python.exe" main.py >> logs\last_run.log 2>&1

echo Exit code: %ERRORLEVEL% >> logs\last_run.log
echo ============================= >> logs\last_run.log
