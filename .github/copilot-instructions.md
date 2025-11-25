



<!-- Concise quick-start for AI coding agents working on this repo -->
# Copilot / AI assistant quick-start (Supply Chain Dashboard)

This project is a Streamlit-based supply-chain analytics dashboard. Keep guidance short — the source and tests are the best references.

What matters (big picture)

Key conventions for edits

Tests and fixtures (important)

Dev workflows (concrete commands, Windows CMD)

Where to look when editing

If anything is missing or unclear here, tell me which area you'd like expanded (more tests, onboarding, or example edits).  

If anything looks missing or unclear (for example README references to debug scripts), ask a human before deleting or refactoring — some scripts are intentionally omitted or environment-specific.

## Big picture (what to know right away)
 - App: `dashboard_simple.py` drives a Streamlit UI. Modular pages live under `pages/` (small, focused modules — copy their patterns).
 - ETL: `data_loader.py` is the canonical data layer. It uses 'unified' readers (load_orders_unified / load_deliveries_unified) that read files once and feed small processors (item/header/service/backorder loaders). Legacy *_legacy functions remain for tests/compatibility.
 - IO: `file_loader.py` centralizes file access via `safe_read_csv()` + `get_file_source()` and supports Streamlit uploads (checks `st.session_state.uploaded_files` first).

## Project-specific conventions & patterns
 - Loader signatures: Many functions return (logs, dataframe[, error_df]). Check callers before you change them.
 - Date handling: Loaders intentionally parse dates with explicit format '%m/%d/%y' using pd.to_datetime(..., format='%m/%d/%y', errors='coerce'). Expect invalid or alternate formats to be dropped (tests assert this behavior).
 - Unified-loaders: Avoid multiple pd.read_csv calls for the same large file — prefer the unified loaders (e.g., load_orders_unified) and then call the lightweight processors (e.g., load_orders_item_lookup or load_orders_header_lookup) on the preloaded dataframe.
 - Performance patterns: Favor vectorized operations, early dropna of grouping keys, and reducing groupby keys (comment blocks in data_loader.py explain intent).
 - Caching in UI: Use utils.get_cached_report_data(report_view, loader, *args) or decorate long-running functions with @st.cache_data to keep interactive filters snappy.

## Tests & fixtures (how tests are designed)
 - Central fixture: `tests/conftest.py` has an autouse `mock_read_csv` that intercepts pd.read_csv and returns StringIO mocks for filenames: master_data.csv, orders.csv, deliveries.csv, inventory.csv. When adding tests, either rely on that fixture or monkeypatch pd.read_csv the same way.
 - Tests often use the legacy loader names (e.g., load_orders_item_lookup_legacy) — verify which variant tests expect before changing signatures.
 - Keep tests self-contained: use the shared fixtures (mock_master_data_csv, mock_orders_csv, etc.) and helper asserts in conftest (assert_log_contains, assert_columns_exist) for consistency.

## Where to look first (files that matter)
 - ETL & transformations: `data_loader.py` (start with unified readers and follow where they flow into lookup functions).
 - File I/O wrapper: `file_loader.py` (safe_read_csv, get_file_source).
 - Caching & export helpers: `utils.py` (get_cached_report_data, Excel export helpers).
 - UI: `dashboard_simple.py` and `pages/` (replicate the UI pattern when adding features).
 - Tests: `tests/` (read `tests/conftest.py` before tests in any area).

## Dev workflows / concrete commands (Windows CMD)
```cmd
pip install -r requirements.txt
streamlit run dashboard_simple.py
start_dashboard_dev.bat (or start_dashboard.bat)  # use for quick local run on Windows
pytest -q  # run tests
pytest tests/test_data_loaders.py -q  # run targeted tests
```

## Quick examples (copy these exact patterns)
 - Read a CSV that supports Streamlit uploads in code: df = safe_read_csv('orders', ORDERS_PATH, usecols=...)
 - Use unified loader then processors: logs, orders_df = load_orders_unified(ORDERS_PATH); logs, item_lookup, errors = load_orders_item_lookup(orders_df)
 - Cache data in UI: df = get_cached_report_data('Service Level', load_service_data, DELIVERIES_PATH, header_df, master_df)

## Small tips (do not assume / watch for)
 - Don't change loader return signatures without updating consuming callers and tests — they rely on (logs, df[, errors]).
 - Tests assume the strict date format; changing the parser has broad consequences for what rows get dropped.
 - When adding files referenced in tests, update `tests/conftest.py` mocks (or add new fixtures) so CI remains hermetic.

If you'd like, I can tighten this further to call out a handful of files to always check before editing (tests, data_loader.py functions touched, and file_loader.py). What would you prefer I expand? ✅
— end of file —

## Troubleshooting dangerous tests / kernel panics ⚠️

This project has a full pytest suite run locally and in CI. Occasionally a test may trigger low-level instability (kernel panic or OS crash) — use the following safe, minimal steps to isolate the problematic test without risking your machine.

- Isolate test files: move all tests out of the repository test folder into a temporary directory (e.g. `tests_quarantine/`), then move files back one-by-one and run pytest until the crash reappears. This quickly narrows down which file contains the problematic test.

- Run tests single-threaded and stop on first failure to reduce resource usage and speed up isolation:

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pytest -q -x
```

- Narrow tests with pattern matching instead of running the whole suite (use `-k` to select by substring):

```cmd
pytest -q -k "my_test_name_or_keyword"
```

- Run tests in a sandbox/VM or container to avoid system-level risk (recommended). On Windows, using WSL or a dedicated VM is a good option.

- Use resource monitoring (Task Manager / Resource Monitor) while running tests. Look for runaway CPU, memory or disk I/O spikes that coincide with the crash.

- Disable GPU / hardware-accelerated parts if tests exercise graphics or acceleration code.

- Check crash logs: OS-level crash dumps or Windows Event Viewer can point to the failing process and timestamp, helping map back to test output.

- Use `pytest-xdist` with caution: parallel workers can increase system load. For safer mitigation, run with a single worker (`-n 1`) or no parallelism.

- When you find the offending test file, run it with logging and `-s` to see stdout and traceback (helps find infinite loops / recursion):

```cmd
pytest <path/to/file>::<TestClass>::test_name -q -s
```

If you want me to add a short helper script to perform automated bisect-style isolation of files, I can add that for the repo.

## Automation: helper to isolate a crashing test 🛠️

I added a small helper script at `tools/isolate_tests.py` to automate the quarantine + incremental-restore approach described above. It's lightweight, Windows-friendly, and saves manual moving/copying of files.

Usage (run from repo root, Windows CMD):

```cmd
python tools\isolate_tests.py quarantine        # move all test_*.py into tests_quarantine/
python tools\isolate_tests.py status           # show counts in tests/ vs tests_quarantine/
python tools\isolate_tests.py incremental      # restore tests one-by-one and run pytest after each add (full-suite run)
python tools\isolate_tests.py incremental --single-file  # run pytest only on the restored file each step
python tools\isolate_tests.py restore          # move all quarantined files back into tests/
```

Notes:
- The script leaves `tests/conftest.py` and `tests/__init__.py` in place so fixtures and package layout remain available.
- Use `incremental` from a sandboxed environment (VM/WSL/container) when reproducing kernel panics.
- The script performs full pytest runs after each restore by default; use `--single-file` to make it faster and test files in isolation.
