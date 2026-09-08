"""Bounded localhost clipboard transport, independent of Tk."""
import socket
import time
import queue

MAX_BYTES = 1024 * 1024
TIMEOUT = 2.0


def receive_text(connection, max_bytes=MAX_BYTES, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    chunks = []
    size = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Clipboard sender timed out")
        connection.settimeout(remaining)
        chunk = connection.recv(min(65536, max_bytes + 1 - size))
        if not chunk:
            return b"".join(chunks).decode("utf-8-sig")
        size += len(chunk)
        if size > max_bytes:
            raise ValueError("Clipboard text exceeds the 1 MiB limit")
        chunks.append(chunk)


def listen(server, stop, messages):
    server.settimeout(0.2)
    while not stop.is_set():
        try:
            connection, peer = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        with connection:
            if peer[0] != "127.0.0.1":
                continue
            try:
                text = receive_text(connection)
                if text and not stop.is_set():
                    messages.put_nowait(text)
            except (OSError, ValueError, UnicodeError):
                # A malformed or stalled sender must not kill the listener or
                # execute a truncated payload. Try the next client.
                continue
            except queue.Full:
                # Bounded queues drop excess clients without growing memory.
                continue
