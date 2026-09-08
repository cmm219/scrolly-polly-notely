"""QA regressions: live editing, reusable saved copies, and durable transfers."""
import copy
import json
from pathlib import Path
import tkinter as tk
from unittest import mock

import pytest
import labels
from PIL import Image


@pytest.fixture
def manager(tmp_path, monkeypatch):
    # conftest checks the module's data root remains owned; per-test config lives
    # under that same root so existing suite fixtures cannot consume this data.
    data = Path(labels.DATA_DIR) / tmp_path.name
    data.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(labels, 'CONFIG_PATH', str(data / 'notes.json'))
    monkeypatch.setattr(labels, 'IMAGE_DIR', str(data / 'images'))
    from test_image_paste import get_root
    root = get_root()
    manager = labels.LabelManager.__new__(labels.LabelManager)
    manager.root = root
    manager.labels = []
    manager.config = labels.load_config()
    manager._publish_jump_list = lambda: False
    yield manager
    manager._autosave_enabled = False
    for pending in root.tk.call('after', 'info'):
        root.after_cancel(pending)
    for child in root.winfo_children():
        child.destroy()


def edit(note, text):
    note._start_edit(None)
    note._entry.delete('1.0', 'end')
    note._entry.insert('1.0', text)


def paste(note, color):
    with mock.patch.object(labels.ImageGrab, 'grabclipboard', return_value=Image.new('RGB', (40, 25), color)):
        note._paste_image(None)


@pytest.mark.parametrize('text', ['', 'one line', 'a\nb', '  indented\n\n', '\nleading\n', 'emoji 😀\n'])
def test_commit_preserves_exact_text(manager, text):
    note = manager.spawn_label(text='old')
    edit(note, text)
    note._finish_edit()
    assert note.snapshot()['text'] == text
    note._start_edit(None)
    assert note._current_content()[0] == text
    note._finish_edit()
    assert note.snapshot()['text'] == text


def test_live_minimize_preserves_text_images_and_writes_once(manager):
    note = manager.spawn_label(text='old')
    edit(note, 'new\n')
    paste(note, 'red')
    paste(note, 'blue')
    expected = note.snapshot()
    real_save = labels.save_config
    calls = []
    def check_save(config):
        assert note.win.winfo_exists()
        assert config['last_session'] == []
        calls.append(copy.deepcopy(config))
        return real_save(config)
    with mock.patch.object(labels, 'save_config', side_effect=check_save):
        manager._auto_minimize_single_label(note)
    assert len(calls) == 1
    assert manager.labels == []
    saved = next(iter(labels.load_config()['minimized_groups'].values()))['labels'][0]
    assert saved == expected
    assert len({d['path'] for d in saved['images']}) == 2


def test_snapshot_does_not_modify_editor_or_undo(manager):
    note = manager.spawn_label(text='original')
    note._start_edit(None)
    entry = note._entry
    paste(note, 'red')
    entry.edit_separator()
    entry.insert('end-1c', 'a')
    entry.edit_separator()
    entry.insert('end-1c', 'b')
    entry.mark_set('insert', '1.2')
    entry.tag_remove('sel', '1.0', 'end')
    entry.tag_add('sel', '1.0', '1.2')
    before = (entry.dump('1.0', 'end', all=True), entry.index('insert'),
              entry.tag_ranges('sel'), entry.yview(), entry.edit_modified())
    note.snapshot()
    after = (entry.dump('1.0', 'end', all=True), entry.index('insert'),
             entry.tag_ranges('sel'), entry.yview(), entry.edit_modified())
    assert before == after
    entry.edit_undo()
    assert entry.get('1.0', 'end-1c').endswith('a')
    entry.edit_redo()
    assert entry.get('1.0', 'end-1c').endswith('ab')


@pytest.mark.parametrize('action', ['minimize', 'stash', 'close', 'duplicate', 'preset', 'restore_stash'])
def test_failed_transfer_keeps_disk_live_notes_and_windows(manager, action):
    note = manager.spawn_label(text='original')
    edit(note, 'dirty')
    manager.config['presets']['layout'] = [{'text': 'template'}]
    manager.config['stash'] = [{'text': 'stash'}]
    manager._persist_last_session()
    before = Path(labels.CONFIG_PATH).read_bytes()
    config_before = copy.deepcopy(manager.config)
    children = set(manager.root.winfo_children())
    manager._autosave_enabled = True
    manager._schedule_autosave()
    old_timer = manager._autosave_after_id
    actions = {
        'minimize': lambda: manager._auto_minimize_single_label(note),
        'stash': note._stash,
        'close': note._close,
        'duplicate': note._duplicate,
        'preset': lambda: manager._load_preset('layout'),
        'restore_stash': lambda: manager._restore_stash(0),
    }
    def fail(config):
        assert manager._mutation_depth > 0
        assert manager._autosave_after_id is None
        manager._autosave()  # Reentrant invocation cannot write partial state.
        raise OSError('injected disk failure')
    with mock.patch.object(labels, 'save_config', side_effect=fail) as save:
        with pytest.raises(OSError, match='injected'):
            actions[action]()
    save.assert_called_once()
    assert Path(labels.CONFIG_PATH).read_bytes() == before
    assert manager.config == config_before
    assert manager.labels == [note]
    assert set(manager.root.winfo_children()) == children
    assert note._entry is not None
    assert note.snapshot()['text'] == 'dirty'
    assert not note.is_clean_saved()
    assert old_timer not in manager.root.tk.call('after', 'info')


def test_preset_restore_is_additive_and_durable(manager):
    original = manager.spawn_label(text='draft')
    manager.config['presets']['layout'] = [{'text': 'template'}]
    manager._load_preset('layout')
    assert manager.labels[0] is original
    assert [d['text'] for d in labels.load_config()['last_session']] == ['draft', 'template']


def test_restored_stash_keeps_reusable_source_after_close(manager):
    note = manager.spawn_label(text='saved')
    edit(note, 'saved')
    paste(note, 'green')
    note._stash()
    data = copy.deepcopy(manager.config['stash'][0])
    manager._restore_stash(0)
    restored = manager.labels[-1]
    assert manager.config['stash'] == [data]
    with mock.patch.object(labels.messagebox, 'askyesnocancel') as prompt:
        restored._request_close()
    prompt.assert_not_called()
    assert labels.load_config()['stash'] == [data]
    assert manager.labels == []
    paths = [d['path'] for d in data['images']]
    manager._delete_stash_item(0)
    assert all(Path(path).exists() for path in paths)


def test_deleted_reusable_source_requires_close_prompt(manager):
    note = manager.spawn_label(text='saved')
    manager.config['stash'] = [note.snapshot()]
    note.mark_clean_saved()
    manager._delete_stash_item(0)
    with mock.patch.object(labels.messagebox, 'askyesnocancel', return_value=None) as prompt:
        note._request_close()
    prompt.assert_called_once()
    assert note in manager.labels


def test_session_only_restore_requires_close_prompt(manager):
    note = manager._spawn_from_data({'text': 'last remaining copy'})
    with mock.patch.object(labels.messagebox, 'askyesnocancel', return_value=None) as prompt:
        note._request_close()
    prompt.assert_called_once()
    assert note in manager.labels


def test_duplicate_preserves_all_properties_and_owns_images(manager):
    note = manager.spawn_label(text='copy', width=350, height=200, opacity=45,
                               ontop=False, show_window_controls=False)
    edit(note, 'copy')
    paste(note, 'red')
    paste(note, 'blue')
    note._finish_edit()
    expected = note.snapshot()
    duplicate = note._duplicate()[0]
    actual = duplicate.snapshot()
    assert {k: v for k, v in actual.items() if k not in ('x', 'y')} == {
        k: v for k, v in expected.items() if k not in ('x', 'y')}
    assert note._images[0] is not duplicate._images[0]
    assert note._photo_refs[0] is not duplicate._photo_refs[0]
    note._close()
    assert len(duplicate._image_frames) == 2
    assert all(int(duplicate.win.tk.call('image', 'width', str(p))) == 40 for p in duplicate._photo_refs)
    manager._persist_last_session()
    snapshot = labels.load_config()['last_session'][0]
    restored = manager._spawn_from_data(snapshot)
    assert len(restored._photo_refs) == 2


def test_readonly_tcl_mutations_and_real_keys_are_blocked(manager):
    note = manager.spawn_label(text='read only')
    widget = note.label
    note.win.update()
    widget.focus_force()
    widget.mark_set('insert', 'end-1c')
    widget.event_generate('<KeyPress>', keysym='z')
    widget.event_generate('<KeyPress>', keysym='BackSpace')
    for args in [('insert', 'end', 'X'), ('delete', '1.0', 'end'), ('replace', '1.0', 'end', 'X')]:
        widget.tk.call(widget._w, *args)
    manager.root.update()
    assert widget.get('1.0', 'end-1c') == 'read only'
    widget.tag_add('sel', '1.0', '1.4')
    assert widget.get('sel.first', 'sel.last') == 'read'
    widget.set_text('internal update')
    assert widget.get('1.0', 'end-1c') == 'internal update'
    command, original = widget._w, widget._original_command
    widget.destroy()
    assert not manager.root.tk.call('info', 'commands', command)
    assert not manager.root.tk.call('info', 'commands', original)


def test_search_recovers_and_finds_all_group_bodies(manager):
    manager.config['minimized_groups']['Alpha'] = {
        'labels': [{'text': 'first'}, {'text': 'second\nhidden body'}]}
    manager._show_saved_notes_window()
    popup = next(w for w in manager.root.winfo_children() if hasattr(w, '_saved_notes_search'))
    search, listing = popup._saved_notes_search, popup._saved_notes_list
    for query in ('absent-xyz', '', 'hidden body', 'absent-xyz', 'Alpha'):
        search.delete(0, 'end')
        search.insert(0, query)
        rows = listing.get(0, 'end')
        assert len(rows) == 1
        assert ('No matches' in rows[0]) == query.startswith('absent')
    assert 'Alpha' in listing.get(0)
    listing.selection_clear(0, 'end')
    listing.selection_set(0)
    # Invoke the real Open button after the no-match transition.
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    button = next(w for w in descendants(popup) if isinstance(w, tk.Button) and w.cget('text') == 'Open')
    button.invoke()
    assert [n.snapshot()['text'] for n in manager.labels] == ['first', 'second\nhidden body']


def test_autosave_live_edits_and_failure_retry(manager):
    note = manager.spawn_label(text='old')
    manager._persist_last_session()
    edit(note, 'new')
    manager._autosave()
    assert labels.load_config()['last_session'][0]['text'] == 'new'
    assert note._entry is not None
    note._entry.insert('end-1c', '!')
    with mock.patch.object(labels, 'save_config', side_effect=OSError('disk')) as save:
        manager._autosave()
        manager._autosave()
        save.assert_called_once()
    assert labels.load_config()['last_session'][0]['text'] == 'new'
    manager._persist_last_session()
    assert labels.load_config()['last_session'][0]['text'] == 'new!'


def test_quit_failure_keeps_active_editor_and_does_not_stop_workers(manager):
    note = manager.spawn_label(text='old')
    edit(note, 'unsaved edit')
    manager._stop_global_recovery_hotkey = mock.Mock()
    with mock.patch.object(labels, 'save_config', side_effect=OSError('disk')):
        with pytest.raises(OSError):
            manager._quit()
    manager._stop_global_recovery_hotkey.assert_not_called()
    assert note.win.winfo_exists()
    assert note._entry.get('1.0', 'end-1c') == 'unsaved edit'


@pytest.mark.parametrize('kind', ['stash', 'preset', 'group'])
def test_delete_failure_does_not_remove_reusable_source(manager, kind):
    manager.config['stash'] = [{'text': 'keep'}]
    manager.config['presets'] = {'p': [{'text': 'keep'}]}
    manager.config['minimized_groups'] = {'g': {'labels': [{'text': 'keep'}]}}
    before = copy.deepcopy(manager.config)
    action = {'stash': lambda: manager._delete_stash_item(0),
              'preset': lambda: manager._delete_preset('p'),
              'group': lambda: manager._delete_minimized_group('g')}[kind]
    with mock.patch.object(labels, 'save_config', side_effect=OSError('disk')), \
         mock.patch.object(labels.messagebox, 'askyesno', return_value=True):
        with pytest.raises(OSError):
            action()
    assert manager.config == before


def test_bulk_close_stops_at_cancel_and_preserves_remaining(manager):
    notes = [manager.spawn_label(text=text) for text in ('discard', 'cancel', 'keep')]
    with mock.patch.object(labels.messagebox, 'askyesnocancel', side_effect=[False, None]) as prompt:
        manager._close_all()
    assert prompt.call_count == 2
    assert manager.labels == notes[1:]
    assert [n['text'] for n in labels.load_config()['last_session']] == ['cancel', 'keep']


def test_bulk_close_empty_clears_stale_session(manager):
    manager.config['last_session'] = [{'text': 'stale'}]
    manager._close_all()
    assert labels.load_config()['last_session'] == []


def test_legacy_stash_date_remains_visible(manager):
    manager.config['stash'] = [{'text': 'legacy', 'stashed_on': '9/8'}]
    item = manager._saved_notes_items()[0]
    assert item['date'] == '9/8'
    assert '9/8' in item['label']
    assert item['sort_date'] == ''  # No year is invented for legacy dates.


def test_missing_image_during_edit_does_not_crash(manager):
    note = manager.spawn_label(text='text stays')
    note._start_edit(None)
    paste(note, 'red')
    image = note.snapshot()['images'][0]
    Path(image['path']).unlink()
    note._finish_edit()
    assert note.snapshot()['text'] == 'text stays'
    assert note.snapshot()['images'][0]['path'] == image['path']
    assert note._photo_refs == []
    manager._persist_last_session()
