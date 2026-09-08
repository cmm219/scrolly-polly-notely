import json
import os
from pathlib import Path
import subprocess
import sys
import queue
import threading
from unittest import mock

import pytest
import note_storage as storage

# Failure injection patches stdlib calls only within these synchronous tests;
# no background storage work is started while those patches are active.


def test_interrupted_primary_replace_preserves_previous_and_backup(tmp_path):
    path = str(tmp_path / 'notes.json')
    old = {'last_session': [{'text': 'old'}]}
    storage.save_document(path, old)
    replace = storage.os.replace
    def fail_primary(source, destination):
        if str(destination) == path:
            raise OSError('interrupted replace')
        replace(source, destination)
    with mock.patch.object(storage.os, 'replace', side_effect=fail_primary):
        with pytest.raises(OSError):
            storage.save_document(path, {'last_session': [{'text': 'new'}]})
    assert storage.load_document(path, {})[0] == old
    assert json.loads(Path(path + '.bak').read_text()) == old
    assert not list(tmp_path.glob('.spn-*.tmp'))


def test_partial_temp_write_or_fsync_failure_preserves_primary(tmp_path):
    path = str(tmp_path / 'notes.json')
    storage.save_document(path, {'last_session': [{'text': 'old'}]})
    before = Path(path).read_bytes()
    with mock.patch.object(storage.os, 'fsync', side_effect=OSError('disk full')):
        with pytest.raises(OSError):
            storage.save_document(path, {'last_session': [{'text': 'new'}]})
    assert Path(path).read_bytes() == before
    assert not list(tmp_path.glob('.spn-*.tmp'))


def test_serialize_failure_never_truncates_file(tmp_path):
    path = str(tmp_path / 'notes.json')
    storage.save_document(path, {'last_session': []})
    before = Path(path).read_bytes()
    with pytest.raises(TypeError):
        storage.save_document(path, {'last_session': [], 'bad': object()})
    assert Path(path).read_bytes() == before


def test_corrupt_primary_recovers_backup_without_rewriting_either(tmp_path):
    path = str(tmp_path / 'notes.json')
    old = {'last_session': [{'text': 'safe'}], 'custom': {'keep': True}}
    storage.save_document(path, old)
    storage.save_document(path, {'last_session': []})
    Path(path).write_text('{broken')
    backup = Path(path + '.bak').read_bytes()
    value, notice = storage.load_document(path, {'stash': []})
    assert value == dict(old, stash=[])
    assert 'Recovered' in notice
    assert Path(path).read_text() == '{broken'
    storage.save_document(path, value)
    assert Path(path + '.bak').read_bytes() == backup


def test_corrupt_both_fail_without_reset(tmp_path):
    path = str(tmp_path / 'notes.json')
    Path(path).write_text('{broken')
    Path(path + '.bak').write_text('[]')
    with pytest.raises(OSError, match='preserved'):
        storage.load_document(path, {'last_session': []})
    assert Path(path).read_text() == '{broken'


def test_backup_failure_warns_but_primary_saves(tmp_path):
    path = str(tmp_path / 'notes.json')
    storage.save_document(path, {'last_session': []})
    replace = storage.os.replace
    def fail_backup(source, destination):
        if str(destination).endswith('.bak'):
            raise OSError('backup locked')
        replace(source, destination)
    with mock.patch.object(storage.os, 'replace', side_effect=fail_backup):
        warning = storage.save_document(path, {'last_session': [{'text': 'new'}]})
    assert 'backup unavailable' in warning
    assert storage.load_document(path, {})[0]['last_session'][0]['text'] == 'new'


def test_lock_released_after_process_death(tmp_path):
    code = ('from note_storage import DataDirectoryLock; import sys,time; '
            'lock=DataDirectoryLock(sys.argv[1]); lock.__enter__(); '
            'print("locked",flush=True); time.sleep(30)')
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    child = subprocess.Popen([sys.executable, '-c', code, str(tmp_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
    handshake = queue.Queue()
    reader = threading.Thread(target=lambda: handshake.put(child.stdout.readline()), daemon=True)
    reader.start()
    try:
        try:
            line = handshake.get(timeout=5)
        except queue.Empty:
            child.kill()
            child.wait(timeout=5)
            reader.join(timeout=5)
            error = child.stderr.read()
            pytest.fail('Lock holder did not start: ' + error)
        reader.join(timeout=5)
        if line.strip() != 'locked':
            child.kill()
            child.wait(timeout=5)
            pytest.fail('Lock holder failed: ' + child.stderr.read())
        with pytest.raises(OSError, match='already'):
            with storage.DataDirectoryLock(str(tmp_path)):
                pass
        child.kill()
        child.wait(timeout=5)
        with storage.DataDirectoryLock(str(tmp_path)):
            pass
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def test_identical_save_preserves_older_backup(tmp_path):
    path = str(tmp_path / 'notes.json')
    storage.save_document(path, {'last_session': [{'text': 'old'}]})
    latest = {'last_session': [{'text': 'new'}]}
    storage.save_document(path, latest)
    backup = Path(path + '.bak')
    before = backup.read_bytes(), backup.stat().st_mtime_ns
    storage.save_document(path, latest)
    assert (backup.read_bytes(), backup.stat().st_mtime_ns) == before


def test_missing_load_and_backup_recovery_have_no_writes(tmp_path):
    path = str(tmp_path / 'notes.json')
    assert storage.load_document(path, {'last_session': []}) == ({'last_session': []}, None)
    assert list(tmp_path.iterdir()) == []
    value = {'last_session': [{'text': 'emoji \U0001F600\r\nlast\ud800'}], 'unknown': [1, 2]}
    backup = Path(path + '.bak')
    backup.write_bytes(b'\xef\xbb\xbf' + json.dumps(value).encode())
    before = backup.read_bytes()
    loaded, notice = storage.load_document(path, {})
    assert loaded == value and notice
    assert list(tmp_path.iterdir()) == [backup]
    assert backup.read_bytes() == before
    storage.save_document(path, value)
    assert storage.load_document(path, {})[0] == value


def test_validation_failure_does_not_open_or_change_destination(tmp_path):
    path = str(tmp_path / 'notes.json')
    storage.save_document(path, {'last_session': [{'text': 'old'}]})
    storage.save_document(path, {'last_session': [{'text': 'new'}]})
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError):
        storage.save_document(path, {'last_session': 'oops'})
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_unreadable_primary_is_not_overwritten(tmp_path):
    path = str(tmp_path / 'notes.json')
    storage.save_document(path, {'last_session': [{'text': 'preserve unreadable source'}]})
    before = Path(path).read_bytes()
    with mock.patch.object(storage, '_read', side_effect=PermissionError('source inaccessible')):
        with pytest.raises(PermissionError):
            storage.save_document(path, {'last_session': []})
    assert Path(path).read_bytes() == before


def test_identical_second_save_creates_first_recoverable_backup(tmp_path):
    path = str(tmp_path / 'notes.json')
    value = {'last_session': [{'text': 'only version'}]}
    storage.save_document(path, value)
    assert not Path(path + '.bak').exists()
    storage.save_document(path, value)
    assert json.loads(Path(path + '.bak').read_text()) == value
    Path(path).write_text('{broken')
    recovered, notice = storage.load_document(path, {})
    assert recovered == value and notice
