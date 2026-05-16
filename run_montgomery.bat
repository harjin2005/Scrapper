@echo off
cd /d D:\Scrapper
call venv\Scripts\activate.bat 2>nul || true
python -m montgomery.main >> montgomery\logs\run_montgomery.log 2>&1
