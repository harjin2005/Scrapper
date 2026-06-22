"""
Run once as Administrator to register the daily scraper job.

Usage (elevated PowerShell / CMD):
    python D:\\Scrapper\\scheduler_setup.py

What it registers:
    Task name : TravisCountyForeclosureScraper
    Action    : D:\\Scrapper\\run_scraper.bat
    Schedule  : Mon-Fri at 07:00 AM
    User      : SYSTEM  (runs even when no user is logged in)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TASK_NAME = "TravisCountyForeclosureScraper"
WORKING_DIR = r"D:\Scrapper"
BAT_FILE = r"D:\Scrapper\run_scraper.bat"

# Hardcoded — do NOT use sys.executable here: the admin Python may differ.
PYTHON_EXE = r"C:\Users\harji\AppData\Local\Programs\Python\Python310\python.exe"


def _build_task_xml() -> str:
    """Return a Windows Task Scheduler XML definition (UTF-16 encoding required)."""
    return f"""\
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Travis County Foreclosure Scraper — runs Mon-Fri at 07:00 AM</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-05-19T07:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek>
          <Monday/>
          <Tuesday/>
          <Wednesday/>
          <Thursday/>
          <Friday/>
        </DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Priority>7</Priority>
    <Hidden>false</Hidden>
    <Enabled>true</Enabled>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{BAT_FILE}</Command>
      <WorkingDirectory>{WORKING_DIR}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""


def _preflight_checks() -> bool:
    """Warn about common problems before attempting registration. Returns True if OK."""
    ok = True
    bat = Path(BAT_FILE)
    if not bat.exists():
        print(f"[ERROR] Bat file not found: {BAT_FILE}")
        print("        Create run_scraper.bat in D:\\Scrapper before registering the task.")
        ok = False

    python = Path(PYTHON_EXE)
    if not python.exists():
        print(f"[WARN]  Python not found at {PYTHON_EXE}")
        print("        The bat file references this path — update run_scraper.bat if needed.")
        # Not fatal — bat file may have already been customised.

    logs = Path(WORKING_DIR) / "logs"
    if not logs.exists():
        logs.mkdir(parents=True, exist_ok=True)
        print(f"[INFO]  Created logs directory: {logs}")

    return ok


def register_task() -> None:
    if not _preflight_checks():
        sys.exit(1)

    xml_text = _build_task_xml()
    xml_path = Path(WORKING_DIR) / "task_definition.xml"

    # schtasks /Create /XML requires UTF-16 LE with BOM
    xml_path.write_text(xml_text, encoding="utf-16")

    try:
        result = subprocess.run(
            [
                "schtasks",
                "/Create",
                "/TN", TASK_NAME,
                "/XML", str(xml_path),
                "/F",          # overwrite if already exists
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        xml_path.unlink(missing_ok=True)  # clean up temp XML regardless of outcome

    if result.returncode == 0:
        print(f"[OK]  Task registered: {TASK_NAME}")
        print(f"      Action    : {BAT_FILE}")
        print(f"      Schedule  : Mon-Fri at 07:00 AM")
        print(f"      Runs as   : SYSTEM (S-1-5-18)")
        print()
        print("To verify:")
        print(f'    schtasks /Query /TN "{TASK_NAME}" /FO LIST /V')
        print()
        print("To trigger a test run immediately:")
        print(f'    schtasks /Run /TN "{TASK_NAME}"')
    else:
        print(f"[FAIL] Registration failed (exit {result.returncode}):")
        print(result.stderr.strip() or result.stdout.strip())
        print()
        print("Common causes:")
        print("  1. Script not run as Administrator.")
        print("  2. Group Policy restricts Task Scheduler.")
        print()
        print("Manual alternative — paste this into an elevated CMD:")
        print(
            f'schtasks /Create /TN "{TASK_NAME}" /TR "{BAT_FILE}" '
            f'/SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:00 /F /RL HIGHEST'
        )
        sys.exit(1)


if __name__ == "__main__":
    register_task()
