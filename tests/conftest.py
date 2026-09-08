import os
from pathlib import Path
import shutil
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from _test_support import TEST_DATA_DIR, assert_test_storage
collect_ignore = ['stress_test.py']  # Run the flow script as a separate process.


@pytest.fixture(autouse=True)
def protect_live_data(monkeypatch):
    assert_test_storage()
    import labels
    # Legacy cases share the process root, but never inherit another case's
    # session/settings. New regression fixtures have per-case subdirectories.
    for filename in (labels.CONFIG_PATH, labels.CONFIG_PATH + '.bak'):
        Path(filename).unlink(missing_ok=True)
    original_rmtree = shutil.rmtree

    def owned_rmtree(path, *args, **kwargs):
        # Tests needing recursive cleanup must allocate beneath TEST_DATA_DIR.
        if not Path(path).resolve().is_relative_to(Path(TEST_DATA_DIR).resolve()):
            raise RuntimeError("Refusing recursive test cleanup outside owned storage")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", owned_rmtree)
    yield
    assert_test_storage()
    # One shared interpreter avoids cross-interpreter PhotoImages and repeated
    # Windows Tcl initialization. Remove every test-owned child and callback.
    import tkinter as tk
    root = tk._default_root
    if root is not None:
        for pending in root.tk.call('after', 'info'):
            root.after_cancel(pending)
        for child in root.winfo_children():
            child.destroy()


def pytest_sessionfinish(session, exitstatus):
    import tkinter as tk
    if tk._default_root is not None:
        tk._default_root.destroy()
