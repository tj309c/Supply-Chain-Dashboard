



<!-- Concise quick-start for AI coding agents working on this repo -->
# Copilot / AI assistant quick-start (Supply Chain Dashboard)

This project is a Streamlit-based supply-chain analytics dashboard. Keep guidance short — the source and tests are the best references.

What matters (big picture)
- Main UI: `dashboard_simple.py` (preferred). Pages live in `pages/` (small, testable modules).
- ETL layer: `data_loader.py` holds the canonical loaders. Big pattern: "unified" readers (load_orders_unified / load_deliveries_unified) -> light-weight processors (item/header loaders). Legacy wrappers exist for backward compatibility.
- IO: `file_loader.py` provides `safe_read_csv()` which checks `st.session_state.uploaded_files` first and falls back to disk. Tests instead monkeypatch `pd.read_csv` (see `tests/conftest.py`).

Key conventions for edits
- Loader signatures: most loader functions return logs + dataframe and often an error_df: (logs, df, error_df) — verify before changing call sites.
- Date handling: loaders consistently parse dates using explicit format '%m/%d/%y'; tests and logic expect that format.
- Performance: avoid duplicate pd.read_csv — use the unified-read pattern; prefer vectorized ops and limited groupby keys for speed.
- Caching/UI: use `@st.cache_data` for expensive loaders and `get_cached_report_data` for the "lazy filter" pattern used across pages.

Tests and fixtures (important)
- Tests are in `tests/`. `tests/conftest.py` uses an autouse fixture `mock_read_csv` that intercepts `pd.read_csv` and returns StringIO for filenames: master_data.csv, orders.csv, deliveries.csv, inventory.csv. Use/inspect these mocks when adding tests.
- When adding tests, follow existing fixtures or use a focused monkeypatch for pd.read_csv. Avoid reliance on streamlit session_state during tests.

Dev workflows (concrete commands, Windows CMD)
- Install deps: pip install -r requirements.txt
- Run app: streamlit run dashboard_simple.py (or use start_dashboard.bat/start_dashboard_dev.bat)
- Run tests: pytest -q  (or target files like pytest tests/test_data_loaders.py -q)

Where to look when editing
- For data loading patterns: `data_loader.py` (look for unified loaders + item/header split)
- For file I/O behavior: `file_loader.py` (safe_read_csv, get_file_source)
- For caching / UI patterns: `utils.py` and `dashboard_simple.py`.
- For examples & intended behavior: tests in `tests/` are authoritative; read `tests/conftest.py` first.

If anything is missing or unclear here, tell me which area you'd like expanded (more tests, onboarding, or example edits).  

If anything looks missing or unclear (for example README references to debug scripts), ask a human before deleting or refactoring — some scripts are intentionally omitted or environment-specific.

— end of file —

— end of file —
