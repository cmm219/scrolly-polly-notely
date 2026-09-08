"""Run each real-manager smoke in its own Tcl process, using caller-owned data."""
import json
import os
from pathlib import Path
import socket
import sys
import time
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))
if not os.environ.get('SCROLLY_POLLY_NOTELY_DATA_DIR'):
    raise RuntimeError('Smoke requires an explicit isolated data folder')
os.environ['SCROLLY_POLLY_DISABLE_JUMPLIST'] = '1'
import labels


def main(mode):
    config = labels.load_config()
    config.update(last_session=[], socket_port=0, global_recovery_hotkey=False)
    if mode == 'occupied':
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            server.listen()
            config['socket_port'] = server.getsockname()[1]
            with mock.patch.object(labels, 'load_config', return_value=config), \
                 mock.patch.object(labels, 'save_config') as save, \
                 mock.patch.object(labels.LabelManager, '_spawn_from_data') as restore:
                try:
                    labels.LabelManager()
                except OSError as error:
                    assert 'already in use' in str(error)
                else:
                    raise AssertionError('Occupied port did not prevent startup')
                save.assert_not_called()
                restore.assert_not_called()
        return
    with mock.patch.object(labels, 'load_config', return_value=config):
        manager = labels.LabelManager()
    try:
        port = manager._server_socket.getsockname()[1]
        with socket.create_connection(('127.0.0.1', port)) as client:
            client.sendall('received 😀'.encode())
            client.shutdown(socket.SHUT_WR)
        deadline = time.monotonic() + 3
        while not manager.labels and time.monotonic() < deadline:
            manager.root.update()
            time.sleep(0.01)
        assert manager.labels, 'No note spawned within 3 seconds'
        assert manager.labels[0].snapshot()['text'] == 'received 😀'
        note = manager.labels[0]
        note._start_edit(None)
        note._entry.delete('1.0', 'end')
        note._entry.insert('1.0', 'saved during quit')
        manager._quit()
        assert json.loads(Path(labels.CONFIG_PATH).read_text())['last_session'][0]['text'] == 'saved during quit'
        assert manager._socket_stop.is_set()
        assert manager._ipc_after_id is None
        assert manager._autosave_after_id is None
    finally:
        try:
            if manager.root.winfo_exists():
                manager._quit()
        except labels.tk.TclError:
            pass


if __name__ == '__main__':
    main(sys.argv[1])
    print('PASS: ' + sys.argv[1])
