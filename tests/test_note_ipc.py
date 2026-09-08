import json
import queue
import socket
import subprocess
import threading
from pathlib import Path
from unittest import mock

import pytest
import labels
import note_ipc


@pytest.mark.parametrize('parts', [[b'hello', b' world'], [b'\xf0', b'\x9f\x98', b'\x80'], [b'x' * 4096, b'y' * 6000]])
def test_fragmented_bytes_received_in_full(parts):
    connection = mock.Mock()
    connection.recv.side_effect = parts + [b'']
    assert note_ipc.receive_text(connection) == b''.join(parts).decode('utf-8')


def test_limit_and_invalid_utf8_reject_whole_message():
    connection = mock.Mock()
    connection.recv.return_value = b'12345'
    with pytest.raises(ValueError, match='limit'):
        note_ipc.receive_text(connection, max_bytes=4)
    connection.recv.side_effect = [b'\xff', b'']
    with pytest.raises(UnicodeDecodeError):
        note_ipc.receive_text(connection)


@pytest.mark.parametrize('test_timeout', [0.1, None])
def test_timed_out_client_does_not_stop_next_client(monkeypatch, test_timeout):
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen()
    port = server.getsockname()[1]
    stop = threading.Event()
    messages = queue.Queue()
    actual_receive = note_ipc.receive_text
    if test_timeout is not None:
        monkeypatch.setattr(note_ipc, 'receive_text', lambda c: actual_receive(c, timeout=test_timeout))
    worker = threading.Thread(target=note_ipc.listen, args=(server, stop, messages), daemon=True)
    worker.start()
    idle = socket.create_connection(('127.0.0.1', port))
    try:
        with socket.create_connection(('127.0.0.1', port)) as good:
            payload = ('\U0001F600' * 3000).encode('utf-8')
            assert len(payload) == 12000
            good.sendall(payload)
            good.shutdown(socket.SHUT_WR)
        assert messages.get(timeout=note_ipc.TIMEOUT + 2) == '\U0001F600' * 3000
        assert messages.empty()
    finally:
        idle.close()
        stop.set()
        server.close()
        worker.join(timeout=3)
    assert not worker.is_alive()


@pytest.mark.parametrize('message', [None, [], 2, {'type': 'bad'}, {'type': 'text', 'text': 4}, {'type': 'restore_minimized', 'name': []}])
def test_invalid_ipc_commands_are_ignored(message):
    manager = labels.LabelManager.__new__(labels.LabelManager)
    manager.spawn_label = mock.Mock()
    manager._restore_minimized_group = mock.Mock()
    manager._handle_ipc_message(message)
    manager.spawn_label.assert_not_called()
    manager._restore_minimized_group.assert_not_called()


@pytest.mark.parametrize('bad_primary', [None, '{broken', '', '   ', 'null', '[]', '{"socket_port":"bad"}', '{"socket_port":0}'])
def test_powershell_helper_reads_configured_port_without_clipboard(tmp_path, bad_primary):
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen()
    server.settimeout(10)
    port = server.getsockname()[1]
    config = tmp_path / Path(labels.CONFIG_PATH).name
    if bad_primary is not None:
        config.write_text(bad_primary)
        config = Path(str(config) + '.bak')
    config.write_text(json.dumps({'socket_port': port}))
    import os
    environment = dict(os.environ, SCROLLY_POLLY_NOTELY_DATA_DIR=str(tmp_path))
    helper = Path(labels.__file__).with_name('send_label.ps1')
    process = subprocess.Popen(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(helper), '-Text', 'synthetic helper text'], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        connection, _ = server.accept()
        with connection:
            assert note_ipc.receive_text(connection) == 'synthetic helper text'
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr.decode(errors='replace')
    finally:
        server.close()
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def test_malformed_framed_message_is_not_plain_text():
    assert labels._decode_ipc_message('SPN1\n{invalid') is None


@pytest.mark.parametrize('mode', ['roundtrip', 'occupied'])
def test_real_manager_in_isolated_tcl_process(mode):
    import os, sys
    environment = dict(os.environ, SCROLLY_POLLY_NOTELY_DATA_DIR=str(Path(labels.DATA_DIR) / mode))
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('manager_smoke.py')), mode], env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'PASS: ' + mode in result.stdout


@pytest.mark.parametrize('data,expected', [('plain text', 'plain text'), ('SPN1\n{"type":"text","text":"framed"}', 'framed')])
def test_positive_text_decode_dispatch(data, expected):
    manager = labels.LabelManager.__new__(labels.LabelManager)
    manager.spawn_label = mock.Mock()
    manager._handle_ipc_message(labels._decode_ipc_message(data))
    manager.spawn_label.assert_called_once_with(text=expected)


def test_positive_restore_decode_dispatch():
    manager = labels.LabelManager.__new__(labels.LabelManager)
    manager._restore_minimized_group = mock.Mock()
    manager._bring_to_front = mock.Mock()
    manager._handle_ipc_message(labels._decode_ipc_message(labels._encode_ipc_command({'type': 'restore_minimized', 'name': 'group'})))
    manager._restore_minimized_group.assert_called_once_with('group')
    manager._bring_to_front.assert_called_once()


def test_queue_drain_continues_after_handler_exception():
    manager = labels.LabelManager.__new__(labels.LabelManager)
    manager.root = mock.Mock()
    manager._ipc_messages = queue.Queue()
    manager._ipc_messages.put('first')
    manager._ipc_messages.put('second')
    manager._handle_ipc_message = mock.Mock(side_effect=[ValueError('bad handler'), None])
    manager._callback_error = mock.Mock()
    manager._drain_ipc()
    assert manager._handle_ipc_message.call_count == 2
    manager._callback_error.assert_called_once()
    manager.root.after.assert_called_once_with(100, manager._drain_ipc)


def test_full_queue_drops_message_and_accepts_next_client():
    server = mock.Mock()
    connections = []
    for payload in (b'one', b'two'):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        connection.recv.side_effect = [payload, b'']
        connections.append(connection)
    server.accept.side_effect = [(c, ('127.0.0.1', 1)) for c in connections] + [OSError('stop')]
    messages = mock.Mock()
    messages.put_nowait.side_effect = [queue.Full, None]
    note_ipc.listen(server, threading.Event(), messages)
    assert messages.put_nowait.call_args_list == [mock.call('one'), mock.call('two')]


def test_whole_message_deadline_is_bounded_even_with_progress():
    connection = mock.Mock()
    connection.recv.return_value = b'progress'
    with mock.patch.object(note_ipc, 'time', mock.Mock(monotonic=mock.Mock(side_effect=[0, 0, 3]))):
        with pytest.raises(TimeoutError):
            note_ipc.receive_text(connection, timeout=2)


@pytest.mark.parametrize('bad_content', ['', '   ', 'null', '{"socket_port":"bad"}'])
def test_helper_invalid_primary_and_backup_fail_with_port_guidance(tmp_path, bad_content):
    import os
    config = tmp_path / Path(labels.CONFIG_PATH).name
    config.write_text(bad_content)
    Path(str(config) + '.bak').write_text(bad_content)
    helper = Path(labels.__file__).with_name('send_label.ps1')
    result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(helper), '-Text', 'synthetic'], env=dict(os.environ, SCROLLY_POLLY_NOTELY_DATA_DIR=str(tmp_path)), capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert '-Port' in result.stderr


def test_helper_legacy_object_without_port_uses_app_default(tmp_path):
    config = tmp_path / 'legacy.json'
    config.write_text('{"theme":"dark"}')
    script = tmp_path / 'read-port.ps1'
    script.write_text("""param([string]$Helper, [string]$Config)
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Helper, [ref]$tokens, [ref]$parseErrors)
$function = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Read-ConfiguredPort' }, $true)
. ([scriptblock]::Create($function.Extent.Text))
Read-ConfiguredPort $Config
""", encoding='utf-8')
    helper = Path(labels.__file__).with_name('send_label.ps1')
    result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), str(helper), str(config)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '47210'
