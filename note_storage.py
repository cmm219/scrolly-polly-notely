"""Atomic local note storage. No recovery path rewrites the source on load."""
import contextlib
import json
import os
import tempfile
import threading

_write_lock = threading.RLock()


def validate_document(value):
    if not isinstance(value, dict):
        raise ValueError("Settings must be a JSON object")

    def notes(items):
        if not isinstance(items, list) or any(not isinstance(n, dict) for n in items):
            raise ValueError("Note collections must be lists of objects")

    for key in ("last_session", "stash"):
        notes(value.get(key, []))
    for key in ("presets", "minimized_groups"):
        groups = value.get(key, {})
        if not isinstance(groups, dict):
            raise ValueError(f"{key} must be an object")
        for group in groups.values():
            if key == "minimized_groups":
                if not isinstance(group, dict):
                    raise ValueError("Saved groups must be objects")
                group = group.get("labels", [])
            notes(group)
    return value


def _read(path):
    with open(path, "rb") as stream:
        payload = stream.read()
    value = validate_document(json.loads(payload.decode("utf-8-sig")))
    return value, payload


def load_document(path, defaults):
    if not os.path.exists(path) and not os.path.exists(path + ".bak"):
        return dict(defaults), None
    try:
        value, _ = _read(path)
        notice = None
    except (OSError, ValueError, UnicodeError) as primary_error:
        try:
            value, _ = _read(path + ".bak")
        except (OSError, ValueError, UnicodeError) as backup_error:
            raise OSError(
                f"Cannot read your notes at {path}. Your files were preserved. "
                f"Restore a valid copy of this file or its .bak backup. "
                f"Details: {primary_error}; backup: {backup_error}"
            ) from primary_error
        notice = f"Recovered notes from {path}.bak. The original file was preserved."
    return dict(defaults, **value), notice


def _atomic_write(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".spn-", suffix=".tmp", dir=directory)
    try:
        try:
            stream = os.fdopen(fd, "wb")
        except Exception:
            os.close(fd)
            raise
        with stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    # Windows does not support opening/fsyncing a directory this way. A
    # post-replace durability hint must never turn success into a false failure.
    if os.name != "nt":
        with contextlib.suppress(OSError):
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)


def save_document(path, value):
    # No destination is opened until serialization and validation succeed.
    validate_document(value)
    payload = (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    warning = None
    with _write_lock:
        try:
            _, previous = _read(path)
        except FileNotFoundError:
            previous = None
        except (ValueError, UnicodeError):
            previous = None  # Keep the last good backup when recovering.
        if previous == payload and os.path.exists(path + ".bak"):
            return None  # Do not rotate away a useful backup on an identical save.
        if previous is not None:
            try:
                _atomic_write(path + ".bak", previous)
            except OSError:
                warning = "Saved; backup unavailable. Check folder permissions."
        _atomic_write(path, payload)
    return warning


class DataDirectoryLock:
    """Kernel-released advisory lock; a leftover file never means a stale lock."""
    def __init__(self, directory):
        self.path = os.path.join(directory, ".instance.lock")
        self.stream = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        stream = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(stream.fileno()).st_size == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            stream.close()
            raise OSError("Scrolly Polly Notely is already using this data folder. Close the existing app first.") from error
        self.stream = stream
        return self

    def __exit__(self, *args):
        if self.stream:
            self.stream.close()
            self.stream = None
