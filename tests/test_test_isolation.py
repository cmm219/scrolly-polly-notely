from pathlib import Path
import shutil
import pytest
import labels
from _test_support import TEST_DATA_DIR, assert_test_storage


def test_storage_and_recursive_cleanup_are_confined(tmp_path):
    assert_test_storage()
    assert Path(labels.IMAGE_DIR).resolve().is_relative_to(Path(TEST_DATA_DIR).resolve())
    sentinel = tmp_path / 'untouched.txt'
    sentinel.write_text('keep')
    with pytest.raises(RuntimeError, match='outside owned storage'):
        shutil.rmtree(tmp_path)
    assert sentinel.read_text() == 'keep'


def test_bootstrap_rejects_outside_image_directory(tmp_path, monkeypatch):
    with monkeypatch.context() as scoped:
        scoped.setattr(labels, 'IMAGE_DIR', str(tmp_path / 'outside-owned-root'))
        with pytest.raises(RuntimeError, match='outside the owned temporary'):
            assert_test_storage()


def test_bootstrap_rejects_preimported_app_path(tmp_path):
    import os, subprocess, sys
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path),
                       SCROLLY_POLLY_NOTELY_DATA_DIR=str(tmp_path / 'synthetic-old-root'))
    code = 'import labels; import _test_support'
    result = subprocess.run([sys.executable, '-c', code], env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'Unsafe test storage' in result.stderr
