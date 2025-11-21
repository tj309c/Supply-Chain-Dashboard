<!-- Auto-generated guidance for AI coding agents working on this repo. Keep it short and actionable. -->
# Copilot / AI assistant quick-start (Supply Chain Dashboard)

This file contains concise, repository-specific knowledge to help AI coding agents make high‑quality, context-aware edits.

Key components (big picture)
- Frontend: `dashboard.py` — a Streamlit single-file app that ties UI, caching and user workflows together.
- Data layer: `data_loader.py` — a set of focused loader functions (master, orders header/item, deliveries, backorders, inventory, lead-times). Loaders return (logs, dataframe, error_df) or similar tuples; check the function signature before changing.
- IO helper: `file_loader.py` — `safe_read_csv` chooses between disk path and Streamlit-uploaded file buffers (uses `st.session_state.uploaded_files`). Tests often monkeypatch `pd.read_csv` rather than using Streamlit state.
- Utilities: `utils.py` — Excel exports, enrichment helpers, caching helpers (lazy-loading pattern).

Developer workflows (concrete commands)
- Install deps: `pip install -r requirements.txt`
- Run app locally: `streamlit run dashboard.py` (default port 8501). It reads CSVs from `data/` unless environment variables are set.
- Set file overrides (example envs):
  - `ORDERS_FILE_PATH`, `DELIVERIES_FILE_PATH`, `MASTER_DATA_FILE_PATH`, `INVENTORY_FILE_PATH`
- Run quick validators/debuggers: `python inventory_validator.py` (exists). README mentions other debug scripts (e.g. `debug_service_level.py`) — those may be missing; prefer running unit tests if unsure.
- Run tests: `pytest test_data_loader.py` (tests mock `pd.read_csv` to validate loader logic).

Important repository-specific conventions & patterns
- Data loaders are defensive and performance-minded:
  - Prefer `usecols` on pd.read_csv and lightweight aggregation to improve speed.
  - Date parsing uses an explicit format (`%m/%d/%y`) for reliability — check/keep this when editing.
  - Loaders typically return diagnostic logs, a DataFrame, and an error DataFrame — preserve this API if possible.
- File I/O is Streamlit-aware: `safe_read_csv()` first checks `st.session_state.uploaded_files` then falls back to disk.
  - When editing loader tests, use monkeypatching of `pd.read_csv` (that's how existing tests inject in-memory CSVs).
- Caching and interactive UX are centered on Streamlit patterns:
  - Use `@st.cache_data` for expensive reads.
  - The app uses session state and a "lazy filter" pattern: filters are only applied when the user clicks `Apply Filters` (see `get_lazy_filtered_data` and `get_cached_report_data`). Respect this pattern when changing UI or data flows.
- Export / formatting helpers: `get_filtered_data_as_excel` and `get_filtered_data_as_excel_with_metadata` — they attempt to be memory efficient and handle datetime formatting.

Areas to be careful about
- Don't assume `st.session_state` exists when running code outside Streamlit (tests). Use `file_loader.get_file_source` logic or mock `pd.read_csv` in tests.
- Several README-listed debug scripts referenced in the README may not be present in the tree — double-check before linking or editing README.
- Many functions accept and return structured tuples (logs, df, error_df). Changing these signatures requires updating callers across `dashboard.py` and tests.

Quick examples to copy while editing
- Run dashboard locally with local data (Windows CMD):
  ```cmd
  pip install -r requirements.txt
  streamlit run dashboard.py
  ```
- Run the unit tests for data loaders:
  ```cmd
  pip install -r requirements.txt
  pytest test_data_loader.py -q
  ```

If anything looks missing or unclear (for example README references to missing debug scripts), ask a human before deleting or refactoring the corresponding references — they may be intentionally omitted from the repo you received.

— end of file —
