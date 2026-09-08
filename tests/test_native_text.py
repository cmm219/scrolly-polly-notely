"""Native Tk event-loop and Tcl command-boundary regressions."""
import tkinter as tk
import pytest
import labels


def test_tcl_caught_index_error_stays_inside_interpreter():
    from test_image_paste import get_root
    root = get_root()
    outcomes = []
    for kind in (tk.Text, labels.ReadOnlyText):
        widget = kind(root)
        command = root.tk.call('list', widget._w, 'index', 'tk::anchor1')
        caught = root.tk.call('list', 'catch', command, '::qa_error', '::qa_options')
        script = root.tk.call('format', 'set ::qa_status [%s]', caught)
        root.tk.call('after', 0, script)
        ticks = []
        def next_tick():
            ticks.append(True)
            root.quit()
        root.after(10, next_tick)
        try:
            root.mainloop()
            assert ticks == [True]
            status = int(root.tk.getvar('::qa_status'))
            error = root.tk.getvar('::qa_error')
            options = root.tk.getvar('::qa_options')
            errorcode = root.tk.call('dict', 'get', options, '-errorcode')
            assert status == 1 and 'bad text index "tk::anchor1"' in error
            assert 'bad text index' in root.tk.call('dict', 'get', options, '-errorinfo')
            outcomes.append((status, error, errorcode))
            with pytest.raises(tk.TclError, match='bad text index'):
                widget.index('tk::anchor1')
        finally:
            widget.destroy()
            root.tk.call('unset', '-nocomplain', '::qa_status', '::qa_error', '::qa_options')
    assert outcomes[0] == outcomes[1]


def test_readonly_toggle_is_per_widget_and_missing_flag_fails_closed():
    from test_image_paste import get_root
    root = get_root()
    first = labels.ReadOnlyText(root)
    second = labels.ReadOnlyText(root)
    first.set_text('one')
    second.set_text('two')
    first.set_readonly(False)
    first.insert('end', ' writable')
    assert str(second.tk.call(second._w, 'insert', 'end', ' blocked')) == ''
    first.set_readonly(True)
    first.tk.call('unset', first._readonly_variable)
    assert str(first.tk.call(first._w, 'insert', 'end', ' blocked')) == ''
    assert first.get('1.0', 'end-1c') == 'one writable'
    assert second.get('1.0', 'end-1c') == 'two'
    first.set_text('internal update')
    assert first.get('1.0', 'end-1c') == 'internal update'
    # Images are created through the forwarded image subcommand, not text writes.
    photo = tk.PhotoImage(master=root, width=2, height=2)
    image_name = first.image_create('end-1c', image=photo)
    assert image_name in first.image_names()
    assert str(first.tk.call(first._w, 'delete', '1.0', 'end')) == ''
    assert first.get('1.0', 'end-1c') == 'internal update'


def test_proxy_cleanup_and_explicit_widget_name_are_safe():
    from test_image_paste import get_root
    root = get_root()
    before_commands = root.tk.call('info', 'commands', '*_original')
    before_flags = root.tk.call('info', 'vars', '::*_readonly')
    for index in range(5):
        frame = tk.Frame(root)
        widget = labels.ReadOnlyText(frame, name='text {qa};$[] spaces')
        widget.set_text('safe')
        assert widget.get('1.0', 'end-1c') == 'safe'
        proxy, original, flag = widget._w, widget._original_command, widget._readonly_variable
        frame.destroy()  # Parent destruction must also remove proc/variable.
        widget.destroy()  # Idempotent, even after parent destruction.
        for command in (proxy, original):
            # Exact command lookup through Tcl namespace avoids glob metacharacters.
            assert not root.tk.call('namespace', 'which', '-command', command)
        assert not int(root.tk.call('info', 'exists', flag))
        with pytest.raises(tk.TclError):
            widget.get('1.0', 'end')
    assert root.tk.call('info', 'commands', '*_original') == before_commands
    assert root.tk.call('info', 'vars', '::*_readonly') == before_flags


def test_destroy_tolerates_teardown_variable_error():
    from test_image_paste import get_root
    from unittest import mock
    root = get_root()
    widget = labels.ReadOnlyText(root)
    interpreter = widget.tk
    def during_teardown(*args):
        if args[0] == 'unset':
            raise tk.TclError('interpreter teardown')
        return interpreter.call(*args)
    widget.tk = mock.Mock(wraps=interpreter)
    widget.tk.call.side_effect = during_teardown
    try:
        widget.destroy()
        assert not interpreter.call('namespace', 'which', '-command', widget._w)
        assert not interpreter.call('namespace', 'which', '-command', widget._original_command)
    finally:
        widget.tk = interpreter
        interpreter.call('unset', '-nocomplain', widget._readonly_variable)
