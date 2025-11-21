import os
import fnmatch


def test_no_use_container_width_exists():
    """
    Fail if any project files contain the deprecated Streamlit arg `use_container_width`.

    This prevents regressions where old code is reintroduced. The test searches
    the repository, excluding common binary and virtualenv directories.
    """
    repo_root = os.path.abspath(os.path.dirname(__file__))

    exclude_dirs = {'.git', '__pycache__', '.venv', 'venv', 'env', '.pytest_cache'}
    matches = []

    for base, dirs, files in os.walk(repo_root):
        # Skip excluded directories
        parts = set(base.split(os.sep))
        if parts & exclude_dirs:
            continue

        for filename in files:
            # Only check text files that are likely to contain Python/MD/streamlit calls
            if not fnmatch.fnmatch(filename, '*.py') and not fnmatch.fnmatch(filename, '*.md') and not fnmatch.fnmatch(filename, '*.txt') and not fnmatch.fnmatch(filename, '*.ipynb'):
                continue

            file_path = os.path.join(base, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    for i, line in enumerate(fh, start=1):
                        if 'use_container_width' in line:
                            matches.append((file_path, i, line.strip()))
            except (UnicodeDecodeError, PermissionError):
                # Skip files that can't be read as text
                continue

    if matches:
        lines = [f"{p}:{ln}: {code}" for p, ln, code in matches]
        found = '\n'.join(lines)
        raise AssertionError(
            "Deprecated Streamlit argument `use_container_width` found in repository.\n" +
            "Please replace with width='stretch' or width='content' as appropriate.\n\n" +
            found
        )
