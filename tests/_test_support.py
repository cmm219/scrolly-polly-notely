"""Safe bootstrap shared by pytest and direct test scripts; import before labels."""
import os
from pathlib import Path
import sys
import tempfile

_temporary = tempfile.TemporaryDirectory(prefix="spn-tests-")
TEST_DATA_DIR = _temporary.name
os.environ["SCROLLY_POLLY_NOTELY_DATA_DIR"] = TEST_DATA_DIR
os.environ["SCROLLY_POLLY_DISABLE_JUMPLIST"] = "1"


def assert_test_storage():
    import labels
    root = Path(TEST_DATA_DIR).resolve()
    for name in ("DATA_DIR", "CONFIG_PATH", "IMAGE_DIR"):
        path = Path(getattr(labels, name)).resolve()
        if not path.is_relative_to(root):
            raise RuntimeError(f"Unsafe test storage: {name} is outside the owned temporary directory")


if "labels" in sys.modules:
    assert_test_storage()
