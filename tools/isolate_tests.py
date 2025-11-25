"""Test isolation helper for bisecting/crashing pytest runs.

Usage (Windows):
  python tools\isolate_tests.py quarantine
  python tools\isolate_tests.py incremental  # moves files back one-by-one and runs pytest until failure
  python tools\isolate_tests.py restore      # move files back from tests_quarantine to tests
  python tools\isolate_tests.py status       # report counts

Notes:
 - This script keeps `tests/conftest.py` and `tests/__init__.py` in place so fixtures stay available.
 - For safety keep a separate shell/VM when running until you've confirmed the offending test.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"
QUARANTINE_DIR = REPO_ROOT / "tests_quarantine"


def list_test_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return sorted([p for p in folder.glob("test_*.py") if p.name not in ("conftest.py", "__init__.py")])


def ensure_quarantine():
    QUARANTINE_DIR.mkdir(exist_ok=True)


def quarantine():
    """Move all test_*.py (except conftest/__init__) into tests_quarantine."""
    ensure_quarantine()
    moved = []
    for p in list_test_files(TESTS_DIR):
        dest = QUARANTINE_DIR / p.name
        shutil.move(str(p), str(dest))
        moved.append(p.name)
    print(f"Moved {len(moved)} test files to {QUARANTINE_DIR}")
    if moved:
        print("Files:")
        for n in moved:
            print(" -", n)


def restore_all():
    moved = []
    for p in list_test_files(QUARANTINE_DIR):
        dest = TESTS_DIR / p.name
        shutil.move(str(p), str(dest))
        moved.append(p.name)
    print(f"Restored {len(moved)} files to {TESTS_DIR}")
    return moved


def run_pytest(args: List[str]) -> int:
    cmd = [sys.executable, "-m", "pytest"] + args
    print("Running:", " ".join(cmd))
    try:
        completed = subprocess.run(cmd, check=False)
        return completed.returncode
    except Exception as e:
        print("Exception while running pytest:", e)
        return 1


def incremental(timeout: int | None = None, single_file_test: bool = False):
    """Move tests back into tests/ one-by-one and run pytest after each move.

    This finds the first file whose addition causes pytest to fail or crash.
    - If `single_file_test` is True, pytest will be run only on the file being added; otherwise the full suite will be run each time.
    """
    files = list_test_files(QUARANTINE_DIR)
    if not files:
        print("No files found in quarantine. Run 'quarantine' first.")
        return

    print(f"Found {len(files)} files in quarantine. Restoring one-by-one...")

    for i, f in enumerate(files, start=1):
        src = QUARANTINE_DIR / f.name
        dest = TESTS_DIR / f.name
        print(f"\n[{i}/{len(files)}] Restoring {f.name}")
        shutil.move(str(src), str(dest))

        if single_file_test:
            args = [str(dest), "-q", "-x"]
        else:
            args = ["-q", "-x"]

        rc = run_pytest(args)
        if rc != 0:
            print("\nDetected pytest failure/crash after adding:", f.name)
            print("Stop here. The problematic test is likely this file or it interacts with earlier files.")
            return

    print("All files restored and tests ran cleanly (no failing/crashing runs detected).")


def status():
    a = len(list_test_files(TESTS_DIR))
    b = len(list_test_files(QUARANTINE_DIR))
    print(f"tests: {a} file(s) in {TESTS_DIR}")
    print(f"quarantine: {b} file(s) in {QUARANTINE_DIR}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Isolate flaky/crashing pytest tests via quarantine + incremental restore")
    p.add_argument("action", choices=["quarantine", "incremental", "restore", "status"], help="Action to take")
    p.add_argument("--single-file", action="store_true", help="When incremental: run pytest only on the restored file, not the whole suite")
    p.add_argument("--timeout", type=int, help="Not yet used — placeholder for future run timeouts (seconds)")
    return p.parse_args()


def main():
    args = parse_args()
    if args.action == "quarantine":
        quarantine()
    elif args.action == "restore":
        restore_all()
    elif args.action == "incremental":
        incremental(timeout=args.timeout, single_file_test=args.single_file)
    elif args.action == "status":
        status()


if __name__ == "__main__":
    main()
