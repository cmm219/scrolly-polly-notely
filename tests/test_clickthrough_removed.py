"""Click-through is no longer offered: notes keep Always on top and never restore stuck."""
from types import SimpleNamespace
import tkinter as tk
from unittest import mock

from test_note_safety import manager  # noqa: F401  shared temporary-storage fixture


def menu_labels(menu):
    labels = []
    for index in range(menu.index('end') + 1):
        if menu.type(index) == 'separator':
            continue
        labels.append(menu.entrycget(index, 'label'))
        if menu.type(index) == 'cascade':
            labels += menu_labels(menu.nametowidget(menu.entrycget(index, 'menu')))
    return labels


def test_note_menu_offers_always_on_top_not_clickthrough(manager):
    note = manager.spawn_label(text='pinned note')
    menus = []
    with mock.patch.object(tk.Menu, 'tk_popup', lambda menu, *args: menus.append(menu)):
        note._show_menu(SimpleNamespace(widget=note.frame, x=1, y=1, x_root=10, y_root=10))
    labels = menu_labels(menus[0])
    assert not any('Click-through' in label for label in labels)
    assert '✓ Always on top' in labels


def test_saved_clickthrough_is_not_restored(manager):
    # A saved flag would leave a note nobody can click (not even its close button).
    saved = manager.spawn_label(text='stuck note').snapshot()
    saved['clickthrough'] = True
    restored = manager._spawn_from_data(saved)
    assert restored.clickthrough is False
