"""
Run once as Administrator to register the daily scraper job.
Usage: python scheduler_setup.py
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path


def register_task() -> None:
    python_exe = sys.executable
    script_path = str(Path(__file__).parent / "main.py")
    working_dir = str(Path(__file__).parent)

    task_xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T07:00:00</StartBoundary>
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
  <Actions Context="Author">
    <Exec>
      <Command>{python_exe}</Command>
      <Arguments>"{script_path}"</Arguments>
      <WorkingDirectory>{working_dir}</WorkingDirectory>
    </Exec>
  </Actions>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Hidden>false</Hidden>
  </Settings>
</Task>"""

    xml_path = Path(working_dir) / "task_definition.xml"
    xml_path.write_text(task_xml, encoding="utf-16")

    result = subprocess.run(
        [
            "schtasks", "/Create", "/TN", "TravisCountyForeclosureScraper",
            "/XML", str(xml_path), "/F",
        ],
        capture_output=True,
        text=True,
    )
    xml_path.unlink(missing_ok=True)

    if result.returncode == 0:
        print("Task registered: TravisCountyForeclosureScraper")
        print("Runs: Mon-Fri at 07:00 AM")
    else:
        print(f"Registration failed: {result.stderr}")
        print("Run this script as Administrator.")
        sys.exit(1)


if __name__ == "__main__":
    register_task()
