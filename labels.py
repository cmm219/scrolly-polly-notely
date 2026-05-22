"""
Scrolly Polly Notely — floating notes with text and image support.
Usage: python labels.py
"""

import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog
import tkinter.font as tkfont
import json
import os
import queue
import re
import socket
import sys
import threading
import uuid
import datetime
import argparse

try:
    from PIL import ImageGrab, ImageTk
except ImportError:
    ImageGrab = None
    ImageTk = None

APP_NAME = "ScrollyPollyNotely"
IPC_PREFIX = "SPN1\n"

try:
    import windows_jumplist
except Exception:
    windows_jumplist = None


def _get_data_dir():
    override = os.environ.get("SCROLLY_POLLY_NOTELY_DATA_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))

    if os.name == "nt":
        base_dir = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base_dir, APP_NAME)

    base_dir = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base_dir, APP_NAME)


DATA_DIR = _get_data_dir()
IMAGE_DIR = os.path.join(DATA_DIR, "pasted-images")

def _ensure_image_dir():
    os.makedirs(IMAGE_DIR, exist_ok=True)


def _jump_list_icon_path():
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "black-paper.ico"),
        os.path.join(getattr(sys, "_MEIPASS", ""), "assets", "black-paper.ico"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _decode_ipc_message(data):
    if data.startswith(IPC_PREFIX):
        try:
            return json.loads(data[len(IPC_PREFIX):])
        except json.JSONDecodeError:
            return {"type": "text", "text": data}
    return {"type": "text", "text": data}


def _encode_ipc_command(command):
    return IPC_PREFIX + json.dumps(command)


def _send_ipc_command(command, port=None, timeout=1.0):
    cfg = load_config()
    port = port or cfg.get("socket_port", 47210)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as conn:
            conn.sendall(_encode_ipc_command(command).encode("utf-8"))
        return True
    except OSError:
        return False


def _embed_images_into_widget(widget, images, photo_refs_out):
    """Embed image dicts into a tk.Text widget. Appends PhotoImage refs to photo_refs_out.
    Images on the same line are inserted in column order with per-line offset accounting.
    widget must already contain the plain text content before this is called.
    """
    try:
        from PIL import ImageTk
    except ImportError:
        return

    per_line_count = {}
    for img_dict in images:
        path = img_dict.get("path", "")
        if not os.path.exists(path):
            import sys
            print(f"[ScrollyPollyNotely] image not found, skipping: {path}", file=sys.stderr)
            continue
        try:
            photo = ImageTk.PhotoImage(file=path)
        except Exception as e:
            import sys
            print(f"[ScrollyPollyNotely] failed to load image {path}: {e}", file=sys.stderr)
            continue

        plain_pos = img_dict.get("position", "end")
        if plain_pos == "end" or plain_pos is None:
            insert_idx = "end"
        else:
            try:
                line, col = plain_pos.split(".")
                count = per_line_count.get(line, 0)
                insert_idx = f"{line}.{int(col) + count}"
                per_line_count[line] = count + 1
            except (ValueError, AttributeError):
                insert_idx = "end"

        photo_refs_out.append(photo)

        if hasattr(widget, '_sticky_label_ref'):
            sl = widget._sticky_label_ref
            frame = sl._make_image_frame(photo, img_dict)
            widget.window_create(insert_idx, window=frame)
        else:
            widget.image_create(insert_idx, image=photo)


def _extract_image_records(widget):
    """Walk a tk.Text widget dump and return (text_segments, image_records).
    image_records: list of {"tcl_name": str, "plain_pos": "line.col"} in dump order.
    plain_pos uses plain-text coordinate space (images count as 0 width).
    """
    text_segments = []
    image_records = []
    img_count_per_line = {}

    for item_type, value, index in widget.dump("1.0", "end", all=True):
        if item_type == "text":
            text_segments.append(value)
        elif item_type == "image":
            line, col = index.split(".")
            preceding = img_count_per_line.get(line, 0)
            plain_col = int(col) - preceding
            img_count_per_line[line] = preceding + 1
            image_records.append({
                "tcl_name": value,
                "plain_pos": f"{line}.{plain_col}",
            })
        elif item_type == "window":
            try:
                child = widget.nametowidget(value)
                if getattr(child, "_sticky_control", False):
                    continue
            except Exception:
                pass
            line, col = index.split(".")
            preceding = img_count_per_line.get(line, 0)
            plain_col = int(col) - preceding
            img_count_per_line[line] = preceding + 1
            image_records.append({
                "tcl_name": value,
                "plain_pos": f"{line}.{plain_col}",
                "is_window": True,
            })

    return text_segments, image_records


class ReadOnlyText(tk.Text):
    """Text widget that allows scrolling and selection but blocks editing."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._readonly = True

    def insert(self, *args, **kwargs):
        if self._readonly:
            return
        super().insert(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._readonly:
            return
        super().delete(*args, **kwargs)

    def set_readonly(self, value=True):
        self._readonly = value

    def set_text(self, text):
        self.set_readonly(False)
        super().delete("1.0", "end")
        super().insert("1.0", text)
        self.set_readonly(True)

CONFIG_PATH = os.path.join(DATA_DIR, "notes-and-settings.json")

DEFAULT_BG = "#1e1e2e"
DEFAULT_FG = "#cdd6f4"
LIGHT_BG = "#ffffff"
LIGHT_FG = "#000000"
DARK_BG = "#000000"
DARK_FG = "#ffffff"
DEFAULT_FONT_FAMILY = "Consolas"
DEFAULT_FONT_SIZE = 11
LABEL_PADX = 12
LABEL_PADY = 4
TRANSPARENT_KEY = "#ff00fe"
MAX_W = 400
MAX_H = 300
MIN_NOTE_W = 128
MIN_NOTE_H = 96
TITLEBAR_H = 24
HUB_DRAG_THRESHOLD_PX = 5
GLOBAL_RECOVERY_HOTKEY_LABEL = "Ctrl+Alt+Shift+T"


class GlobalRecoveryHotkey:
    HOTKEY_ID = 0x53504E
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_NOREPEAT = 0x4000
    VK_T = 0x54
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    ERROR_HOTKEY_ALREADY_REGISTERED = 1409

    def __init__(self, root, callback):
        self.root = root
        self.callback = callback
        self._ready = threading.Event()
        self._thread = None
        self._thread_id = None
        self._running = False
        self._start_error = None
        self._fires = queue.Queue()

    @staticmethod
    def is_supported():
        return sys.platform == "win32"

    def start(self):
        if not self.is_supported():
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._ready.clear()
        self._start_error = None
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=3.0):
            self._start_error = f"timed out while registering {GLOBAL_RECOVERY_HOTKEY_LABEL}"
            self.stop()
            self._warn_start_error()
            return False
        if self._start_error:
            self._warn_start_error()
            return False
        return self._running

    def stop(self):
        if not self._thread:
            return
        thread = self._thread
        thread_id = self._thread_id
        if thread.is_alive() and thread_id:
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.PostThreadMessageW.argtypes = [
                    wintypes.DWORD,
                    wintypes.UINT,
                    wintypes.WPARAM,
                    wintypes.LPARAM,
                ]
                user32.PostThreadMessageW.restype = wintypes.BOOL
                user32.PostThreadMessageW(thread_id, self.WM_QUIT, 0, 0)
            except Exception:
                pass
            thread.join(timeout=1.0)
        self._thread = None
        self._thread_id = None
        self._running = False

    def _message_loop(self):
        user32 = None
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            user32.RegisterHotKey.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                wintypes.UINT,
                wintypes.UINT,
            ]
            user32.RegisterHotKey.restype = wintypes.BOOL
            user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.UnregisterHotKey.restype = wintypes.BOOL
            user32.GetMessageW.argtypes = [
                ctypes.POINTER(wintypes.MSG),
                wintypes.HWND,
                wintypes.UINT,
                wintypes.UINT,
            ]
            user32.GetMessageW.restype = ctypes.c_int
            user32.PeekMessageW.argtypes = [
                ctypes.POINTER(wintypes.MSG),
                wintypes.HWND,
                wintypes.UINT,
                wintypes.UINT,
                wintypes.UINT,
            ]
            user32.PeekMessageW.restype = wintypes.BOOL
            user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user32.TranslateMessage.restype = wintypes.BOOL
            user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user32.DispatchMessageW.restype = ctypes.c_ssize_t
            kernel32.GetCurrentThreadId.restype = wintypes.DWORD

            msg = wintypes.MSG()
            self._thread_id = kernel32.GetCurrentThreadId()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

            modifiers = self.MOD_CONTROL | self.MOD_ALT | self.MOD_SHIFT | self.MOD_NOREPEAT
            if not user32.RegisterHotKey(None, self.HOTKEY_ID, modifiers, self.VK_T):
                self._start_error = ctypes.get_last_error()
                self._ready.set()
                return

            self._running = True
            self._ready.set()
            while True:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0:
                    break
                if result == -1:
                    self._start_error = ctypes.get_last_error()
                    break
                if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                    self._schedule_callback()
                else:
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            self._start_error = exc
            self._ready.set()
        finally:
            if self._running and user32 is not None:
                try:
                    user32.UnregisterHotKey(None, self.HOTKEY_ID)
                except Exception:
                    pass
            self._running = False

    def _schedule_callback(self):
        self._fires.put_nowait(True)

    def poll(self):
        fired = False
        while True:
            try:
                self._fires.get_nowait()
            except queue.Empty:
                break
            fired = True
        if fired:
            self.callback()

    def _warn_start_error(self):
        print(
            f"[ScrollyPollyNotely] Global recovery hotkey disabled: {self.failure_reason()}.",
            file=sys.stderr,
        )

    def failure_reason(self):
        if self._start_error == self.ERROR_HOTKEY_ALREADY_REGISTERED:
            return (
                f"{GLOBAL_RECOVERY_HOTKEY_LABEL} is already registered by another app "
                "or another Scrolly Polly Notely window"
            )
        if isinstance(self._start_error, BaseException):
            return str(self._start_error)
        return f"Windows error {self._start_error}"


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {
        "default_bg": DEFAULT_BG,
        "default_fg": DEFAULT_FG,
        "font_family": DEFAULT_FONT_FAMILY,
        "font_size": DEFAULT_FONT_SIZE,
        "default_transparent": False,
        "default_show_window_controls": True,
        "clickthrough_warned": False,
        "hub_always_on_top": True,
        "global_recovery_hotkey": True,
        "last_session": [],
        "presets": {},
        "minimized_groups": {},
    }


def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _show_font_family_picker(parent, anchor, title, bg, fg, current_family, font_size, apply_callback, sample_text):
    width = 340
    height = 410
    x = anchor.winfo_rootx()
    y = anchor.winfo_rooty() + anchor.winfo_height() + 5
    max_x = max(0, parent.winfo_screenwidth() - width)
    max_y = max(0, parent.winfo_screenheight() - height)
    x = min(max(0, x), max_x)
    y = min(max(0, y), max_y)

    popup = tk.Toplevel(parent)
    popup.title(title)
    popup.attributes("-topmost", True)
    popup.geometry(f"{width}x{height}+{x}+{y}")

    frame = tk.Frame(popup, bg=bg, padx=10, pady=10)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text=title, bg=bg, fg=fg,
             font=(DEFAULT_FONT_FAMILY, 10, "bold")).pack(anchor="w")

    search_var = tk.StringVar()
    search = tk.Entry(frame, textvariable=search_var, bg="#ffffff", fg="#000000",
                      insertbackground="#000000", relief="flat")
    search.pack(fill="x", pady=(6, 8))

    list_frame = tk.Frame(frame, bg=bg)
    list_frame.pack(fill="both", expand=True)
    scrollbar = tk.Scrollbar(list_frame)
    scrollbar.pack(side="right", fill="y")
    fonts = tk.Listbox(
        list_frame,
        activestyle="none",
        exportselection=False,
        yscrollcommand=scrollbar.set,
        bg="#ffffff",
        fg="#000000",
        selectbackground="#2d5f9a",
        selectforeground="#ffffff",
        relief="flat",
        height=12,
    )
    fonts.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=fonts.yview)

    sample = tk.Label(frame, text=sample_text, bg=bg, fg=fg,
                      font=(current_family, max(font_size, 12), "bold"))
    sample.pack(fill="x", pady=(8, 6))

    all_families = sorted(set(tkfont.families(parent)), key=str.lower)
    if current_family not in all_families:
        all_families.insert(0, current_family)

    def refresh(*_):
        query = search_var.get().strip().lower()
        fonts.delete(0, "end")
        for family in all_families:
            if not query or query in family.lower():
                fonts.insert("end", family)
        matches = fonts.get(0, "end")
        if current_family in matches:
            idx = matches.index(current_family)
            fonts.selection_set(idx)
            fonts.see(idx)
        elif matches:
            fonts.selection_set(0)

    def selected_family():
        selection = fonts.curselection()
        if not selection:
            return None
        return fonts.get(selection[0])

    def preview(*_):
        family = selected_family()
        if family:
            sample.config(font=(family, max(font_size, 12), "bold"))

    def apply_and_close(event=None):
        family = selected_family()
        if family:
            apply_callback(family)
        popup.destroy()
        return "break"

    def cancel(event=None):
        popup.destroy()
        return "break"

    button_row = tk.Frame(frame, bg=bg)
    button_row.pack(fill="x")
    tk.Button(button_row, text="OK", command=apply_and_close).pack(side="right")
    tk.Button(button_row, text="Cancel", command=cancel).pack(side="right", padx=(0, 6))

    search_var.trace_add("write", refresh)
    fonts.bind("<<ListboxSelect>>", preview)
    fonts.bind("<Double-Button-1>", apply_and_close)
    popup.bind("<Return>", apply_and_close)
    popup.bind("<Escape>", cancel)
    refresh()
    preview()
    search.focus_set()


class StickyLabel:
    def __init__(self, manager, text="Label", x=100, y=100, bg=None, fg=None,
                 transparent=None, font_size=None, width=None, height=None,
                 clickthrough=False, ontop=True, images=None, opacity=None,
                 font_family=None, show_window_controls=None):
        self.manager = manager
        cfg = manager.config

        self.bg = bg or cfg["default_bg"]
        self.fg = fg or cfg["default_fg"]
        self.font_family = font_family or cfg.get("font_family", DEFAULT_FONT_FAMILY)
        self.font_size = font_size or cfg.get("font_size", DEFAULT_FONT_SIZE)
        self.transparent = transparent if transparent is not None else cfg.get("default_transparent", False)
        self.show_window_controls = (
            show_window_controls
            if show_window_controls is not None
            else cfg.get("default_show_window_controls", True)
        )
        self.clickthrough = clickthrough
        self.ontop = ontop
        self.opacity = opacity if opacity is not None else 100

        self.win = tk.Toplevel(manager.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", self.ontop)
        self.win.attributes("-alpha", self.opacity / 100)
        geo = f"+{x}+{y}"
        if width and height:
            geo = f"{width}x{height}+{x}+{y}"
        self.win.geometry(geo)
        self.win.minsize(MIN_NOTE_W, MIN_NOTE_H)

        self.frame = tk.Frame(self.win, bg=self.bg, cursor="arrow")
        self.frame.pack(fill="both", expand=True)

        self.label = ReadOnlyText(
            self.frame,
            font=self._font_tuple(),
            bg=self.bg,
            fg=self.fg,
            padx=LABEL_PADX,
            pady=LABEL_PADY,
            cursor="arrow",
            wrap="word",
            relief="flat",
            width=1,
            height=1,
        )
        self._drag_x = 0
        self._drag_y = 0
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._resize_start_w = 0
        self._resize_start_h = 0
        self._entry = None
        self._photo_refs = []
        self._entry_photo_refs = []
        self._images = []
        self._image_name_map = {}
        self._image_frames = []
        self._img_rs_x = 0
        self._img_rs_w = 0
        self._img_rs_h = 0
        self._clickthrough_style_on = False
        self._maximized = False
        self._normal_geometry = None
        self._clean_snapshot_key = None

        self.titlebar = tk.Canvas(
            self.frame,
            bg=self.bg,
            height=TITLEBAR_H,
            cursor="fleur",
            highlightthickness=0,
            bd=0,
        )
        self.titlebar.pack(side="top", fill="x")
        self._titlebar_control_press = False
        self._titlebar_control_centers = {}
        self._titlebar_control_rects = {}
        self._render_titlebar_controls()

        self.label.set_text(text)
        self.label._sticky_label_ref = self

        self.label.pack(fill="both", expand=True)

        if images:
            _embed_images_into_widget(self.label, images, self._photo_refs)
            self._images = [dict(d) for d in images if os.path.exists(d.get("path", ""))]

        self._apply_checklist_tags()

        # Auto-size window to content (up to MAX_W x MAX_H)
        self.win.update_idletasks()
        if not (width and height):
            lines = int(self.label.index("end-1c").split(".")[0])
            new_w = 250
            new_h = min(max((lines * 20) + TITLEBAR_H + 32, MIN_NOTE_H), MAX_H)
            self.win.geometry(f"{new_w}x{new_h}+{x}+{y}")

        self.grip = tk.Label(
            self.frame,
            text="",
            bg=self.bg,
            fg=self.bg,
            width=2,
            height=1,
            cursor="size_nw_se",
        )
        self.grip.place(relx=1.0, rely=1.0, anchor="se")

        if self.transparent:
            self._apply_transparent(True)

        if self.clickthrough:
            self._apply_clickthrough(True)

        self.label.bind("<Button-1>", self._on_checklist_click)
        self.label.bind("<B1-Motion>", self._on_drag)
        self.label.bind("<MouseWheel>", self._on_mousewheel)
        self.label.bind("<Enter>", lambda e: self.label.focus_set())
        self.frame.bind("<Button-1>", self._start_drag)
        self.frame.bind("<B1-Motion>", self._on_drag)
        self.titlebar.bind("<Button-1>", self._on_titlebar_press)
        self.titlebar.bind("<B1-Motion>", self._on_titlebar_drag)
        self.titlebar.bind("<Motion>", self._on_titlebar_motion)
        self.titlebar.bind("<Leave>", lambda e: self.titlebar.config(cursor="fleur"))
        self.titlebar.bind("<Configure>", lambda e: self._render_titlebar_controls())
        self.label.bind("<Double-Button-1>", self._start_edit)
        self.label.bind("<Control-Delete>", lambda e: self._close())
        self.frame.bind("<Control-Delete>", lambda e: self._close())
        self.label.bind("<Button-3>", self._show_menu)
        self.frame.bind("<Button-3>", self._show_menu)
        self.titlebar.bind("<Button-3>", self._show_menu)
        self.grip.bind("<Button-1>", self._start_resize)
        self.grip.bind("<B1-Motion>", self._on_resize)
        self.win.bind("<Configure>", self._on_window_resize)

    def _font_tuple(self, size=None, family=None):
        return (family or self.font_family, size or self.font_size, "bold")

    def _style_window_controls(self, bg=None, fg=None):
        bg = bg or self.bg
        fg = fg or self.fg
        self.titlebar.config(bg=bg)
        self._render_titlebar_controls()

    def _render_titlebar_controls(self):
        self.titlebar.delete("all")
        self._titlebar_control_centers = {}
        self._titlebar_control_rects = {}
        if not self.show_window_controls:
            return
        width = max(self.titlebar.winfo_width(), MIN_NOTE_W)
        y = 12
        controls = [
            ("minimize", width - 96),
            ("maximize", width - 54),
            ("close", width - 18),
        ]
        for name, x in controls:
            self._titlebar_control_centers[name] = x
        self._titlebar_control_rects = {
            "minimize": (width - 112, 0, width - 80, 24),
            "maximize": (width - 70, 0, width - 38, 24),
            "close": (width - 34, 0, width, 24),
        }
        self.titlebar.create_line(width - 102, y, width - 90, y, fill=self.fg, width=2, tags=("minimize", "window_control"))
        if self._maximized:
            self.titlebar.create_rectangle(width - 61, y - 6, width - 51, y + 4, outline=self.fg, width=2, tags=("maximize", "window_control"))
            self.titlebar.create_rectangle(width - 57, y - 3, width - 47, y + 7, outline=self.fg, width=2, tags=("maximize", "window_control"))
        else:
            self.titlebar.create_rectangle(width - 60, y - 6, width - 48, y + 6, outline=self.fg, width=2, tags=("maximize", "window_control"))
        self.titlebar.create_line(width - 23, y - 5, width - 13, y + 5, fill=self.fg, width=2, tags=("close", "window_control"))
        self.titlebar.create_line(width - 13, y - 5, width - 23, y + 5, fill=self.fg, width=2, tags=("close", "window_control"))

    def _titlebar_hit_control(self, event):
        centers = self._titlebar_control_centers
        rects = self._titlebar_control_rects
        if not centers or not rects:
            return None
        y = getattr(event, "y", 12)
        for name in ("minimize", "maximize", "close"):
            left, top, right, bottom = rects[name]
            if left <= event.x <= right and top <= y <= bottom:
                return name
        return None

    def _on_titlebar_press(self, event):
        hit = self._titlebar_hit_control(event)
        self._titlebar_control_press = bool(hit)
        if hit == "minimize":
            self.manager._auto_minimize_single_label(self)
            return "break"
        if hit == "maximize":
            self._toggle_maximize_restore()
            return "break"
        if hit == "close":
            self._request_close()
            return "break"
        self._start_drag(event)
        return "break"

    def _on_titlebar_drag(self, event):
        if self._titlebar_control_press:
            return "break"
        self._on_drag(event)
        return "break"

    def _on_titlebar_motion(self, event):
        cursor = "hand2" if self._titlebar_hit_control(event) else "fleur"
        if self.titlebar.cget("cursor") != cursor:
            self.titlebar.config(cursor=cursor)
        return "break"

    def _toggle_maximize_restore(self):
        self.win.update_idletasks()
        if self._maximized:
            if self._normal_geometry:
                self.win.geometry(self._normal_geometry)
                self.win.update_idletasks()
            self._maximized = False
            self._render_titlebar_controls()
            return

        self._normal_geometry = self.win.geometry()
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        self.win.geometry(f"{screen_w}x{screen_h}+0+0")
        self.win.update_idletasks()
        self._maximized = True
        self._render_titlebar_controls()

    def _request_close(self):
        if not self.label.get("1.0", "end-1c").strip() and not self._images:
            self._close()
            return
        if self.is_clean_saved():
            self._close()
            return
        choice = messagebox.askyesnocancel(
            "Save note?",
            "Save this note before closing?",
            parent=self.win,
        )
        if choice is None:
            return
        if choice:
            self.manager._auto_minimize_single_label(self)
            return
        self._close()

    def _make_image_frame(self, photo, img_dict):
        frame = tk.Frame(self.label, bg=self.bg, cursor="arrow")
        img_label = tk.Label(frame, image=photo, bg=self.bg, cursor="arrow")
        img_label.pack()

        grip = tk.Label(frame, text="", bg=self.bg, fg=self.bg,
                        width=1, height=1, cursor="size_nw_se")
        grip.place(relx=1.0, rely=1.0, anchor="se")

        frame._photo = photo
        frame._img_dict = img_dict
        frame._img_label = img_label

        grip.bind("<Button-1>", lambda e: self._img_grip_start(e, frame))
        grip.bind("<B1-Motion>", lambda e: self._img_grip_drag(e, frame))
        grip.bind("<ButtonRelease-1>", lambda e: self._img_grip_end(e, frame))
        img_label.bind("<Button-3>", self._show_menu)

        self._image_frames.append(frame)
        return frame

    def _img_grip_start(self, event, frame):
        self._img_rs_x = event.x_root
        self._img_rs_w = frame._img_dict["width"]
        self._img_rs_h = frame._img_dict["height"]

    def _img_grip_drag(self, event, frame):
        if ImageTk is None:
            return
        try:
            from PIL import Image as PilImage
        except ImportError:
            return
        dx = event.x_root - self._img_rs_x
        new_w = max(20, self._img_rs_w + dx)
        ratio = new_w / self._img_rs_w
        new_h = max(10, int(self._img_rs_h * ratio))
        try:
            orig = PilImage.open(frame._img_dict["original_path"])
            resized = orig.resize((new_w, new_h))
            photo = ImageTk.PhotoImage(resized)
            frame._img_label.config(image=photo)
            frame._photo = photo
            frame._pending_w = new_w
            frame._pending_h = new_h
        except Exception:
            pass

    def _img_grip_end(self, event, frame):
        if not hasattr(frame, '_pending_w'):
            return
        new_w = frame._pending_w
        new_h = frame._pending_h
        img_dict = frame._img_dict

        orig_filename = os.path.basename(img_dict["original_path"])
        uid = orig_filename.replace("img_", "").replace(".png", "")
        new_path = os.path.join(IMAGE_DIR, f"img_{uid}_{new_w}x{new_h}.png")
        try:
            from PIL import Image as PilImage
            orig = PilImage.open(img_dict["original_path"])
            resized = orig.resize((new_w, new_h))
            resized.save(new_path)
        except Exception:
            return

        img_dict["path"] = new_path
        img_dict["width"] = new_w
        img_dict["height"] = new_h

        for i, ref in enumerate(self._photo_refs):
            if ref is getattr(frame, '_orig_photo', None):
                self._photo_refs[i] = frame._photo
                break

        if hasattr(frame, '_pending_w'):
            del frame._pending_w
        if hasattr(frame, '_pending_h'):
            del frame._pending_h

    def _on_window_resize(self, event):
        """Reflow text to match window width."""
        if self._entry:
            return
        pixel_w = self.win.winfo_width()
        font = self.label.cget("font")
        char_w = self.label.tk.call("font", "measure", font, "0")
        if char_w > 0:
            chars = max(10, (pixel_w - 2 * LABEL_PADX) // char_w)
            self.label.config(width=chars)

    def _apply_checklist_tags(self):
        """Scan text for checklist patterns and apply visual tags."""
        self.label.tag_remove("checked", "1.0", "end")
        self.label.tag_remove("unchecked", "1.0", "end")
        self.label.tag_config("checked", overstrike=True, foreground="#666666")

        content = self.label.get("1.0", "end-1c")
        for i, line in enumerate(content.split("\n"), start=1):
            if line.startswith("- [x] "):
                start = f"{i}.0"
                end = f"{i}.end"
                self.label.tag_add("checked", start, end)
            elif line.startswith("- [ ] "):
                start = f"{i}.0"
                end = f"{i}.end"
                self.label.tag_add("unchecked", start, end)

    def _toggle_checklist_item(self, index):
        """Toggle a checklist item at the given line index."""
        line_num = index.split(".")[0]
        line_start = f"{line_num}.0"
        line_end = f"{line_num}.end"
        line_text = self.label.get(line_start, line_end)

        if line_text.startswith("- [ ] "):
            new_line = "- [x] " + line_text[6:]
        elif line_text.startswith("- [x] "):
            new_line = "- [ ] " + line_text[6:]
        else:
            return False

        full_text = self.label.get("1.0", "end-1c")
        lines = full_text.split("\n")
        line_idx = int(line_num) - 1
        if line_idx < len(lines):
            lines[line_idx] = new_line

        # Sort: non-checklist first, then unchecked, then checked
        other = [l for l in lines if not l.startswith("- [ ]") and not l.startswith("- [x]")]
        unchecked = [l for l in lines if l.startswith("- [ ]")]
        checked = [l for l in lines if l.startswith("- [x]")]
        sorted_lines = other + unchecked + checked

        self.label.set_text("\n".join(sorted_lines))
        self._apply_checklist_tags()

        # Re-embed images if any (set_text wipes them)
        if self._images:
            for f in self._image_frames:
                f.destroy()
            self._image_frames = []
            new_refs = []
            _embed_images_into_widget(self.label, self._images, new_refs)
            self._photo_refs = new_refs

        return True

    def _on_checklist_click(self, event):
        """Handle click on checklist items. Falls through to drag if not a checklist line."""
        self.win.lift()
        idx = self.label.index(f"@{event.x},{event.y}")
        line_num = idx.split(".")[0]
        line_start = f"{line_num}.0"
        line_text = self.label.get(line_start, f"{line_num}.end")

        if line_text.startswith("- [ ] ") or line_text.startswith("- [x] "):
            self._toggle_checklist_item(idx)
            return "break"

        self._start_drag(event)
        return "break"

    def snapshot(self):
        self.win.update_idletasks()
        return {
            "text": self.label.get("1.0", "end-1c"),
            "x": self.win.winfo_x(),
            "y": self.win.winfo_y(),
            "width": self.win.winfo_width(),
            "height": self.win.winfo_height(),
            "bg": self.bg,
            "fg": self.fg,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "transparent": self.transparent,
            "clickthrough": self.clickthrough,
            "ontop": self.ontop,
            "images": list(self._images),
            "opacity": self.opacity,
            "show_window_controls": self.show_window_controls,
        }

    def _snapshot_dirty_key(self, snapshot=None):
        snapshot = snapshot or self.snapshot()
        comparable = {
            key: snapshot.get(key)
            for key in (
                "text",
                "bg",
                "fg",
                "font_family",
                "font_size",
                "transparent",
                "clickthrough",
                "ontop",
                "images",
                "opacity",
                "show_window_controls",
            )
        }
        return json.dumps(comparable, sort_keys=True, default=str)

    def mark_clean_saved(self):
        self._clean_snapshot_key = self._snapshot_dirty_key()

    def is_clean_saved(self):
        return (
            self._clean_snapshot_key is not None and
            self._clean_snapshot_key == self._snapshot_dirty_key()
        )

    def _apply_transparent(self, on):
        if on:
            self.win.config(bg=TRANSPARENT_KEY)
            self.frame.config(bg=TRANSPARENT_KEY)
            self.label.config(bg=TRANSPARENT_KEY)
            self.grip.config(bg=TRANSPARENT_KEY, fg=TRANSPARENT_KEY)
            self._style_window_controls(TRANSPARENT_KEY, self.fg)
            self.win.attributes("-transparentcolor", TRANSPARENT_KEY)
        else:
            self.win.config(bg=self.bg)
            self.frame.config(bg=self.bg)
            self.label.config(bg=self.bg)
            self.grip.config(bg=self.bg, fg=self.bg)
            self._style_window_controls(self.bg, self.fg)
            self.win.attributes("-transparentcolor", "")
            self.win.attributes("-alpha", self.opacity / 100)

    def _apply_clickthrough(self, on):
        self.clickthrough = on
        style_applied = self._set_window_clickthrough(on)
        if on:
            handler = (lambda e: "break") if style_applied else self._passthrough_click
            self.label.bind("<Button-1>", handler)
            self.label.bind("<B1-Motion>", lambda e: None)
            self.frame.bind("<Button-1>", handler)
            self.frame.bind("<B1-Motion>", lambda e: None)
        else:
            self.label.bind("<Button-1>", self._on_checklist_click)
            self.label.bind("<B1-Motion>", self._on_drag)
            self.frame.bind("<Button-1>", self._start_drag)
            self.frame.bind("<B1-Motion>", self._on_drag)
        self.win.attributes("-topmost", self.ontop)

    def _set_window_clickthrough(self, on):
        if os.name != "nt":
            self._clickthrough_style_on = False
            return False
        try:
            import ctypes
            self.win.update_idletasks()
            hwnd = self.win.winfo_id()
            if not hwnd:
                return False

            gwl_exstyle = -20
            ws_ex_transparent = 0x00000020
            ws_ex_layered = 0x00080000
            ws_ex_toolwindow = 0x00000080
            user32 = ctypes.windll.user32

            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            ex_style = get_long(hwnd, gwl_exstyle)
            if on:
                ex_style |= ws_ex_layered | ws_ex_transparent | ws_ex_toolwindow
            else:
                ex_style &= ~ws_ex_transparent
                ex_style |= ws_ex_layered | ws_ex_toolwindow
            set_long(hwnd, gwl_exstyle, ex_style)
            self.win.attributes("-alpha", self.opacity / 100)
            self._clickthrough_style_on = on
            return True
        except Exception:
            self._clickthrough_style_on = False
            return False

    def _passthrough_click(self, event):
        import ctypes
        self.win.withdraw()
        self.win.update_idletasks()
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
        def restore():
            self.win.deiconify()
            self.win.attributes("-topmost", self.ontop)
        self.win.after(80, restore)

    def _toggle_transparent(self):
        self.transparent = not self.transparent
        self._apply_transparent(self.transparent)

    def _apply_image_frame_bg(self):
        for frame in self._image_frames:
            if not frame.winfo_exists():
                continue
            frame.config(bg=self.bg)
            if hasattr(frame, "_img_label") and frame._img_label.winfo_exists():
                frame._img_label.config(bg=self.bg)
            for child in frame.winfo_children():
                if child is not getattr(frame, "_img_label", None):
                    child.config(bg=self.bg, fg=self.bg)

    def _apply_theme(self, bg, fg):
        self.bg = bg
        self.fg = fg
        self.transparent = False
        self.win.attributes("-transparentcolor", "")
        self.win.config(bg=self.bg)
        self.frame.config(bg=self.bg)
        self.label.config(bg=self.bg, fg=self.fg)
        self.grip.config(bg=self.bg, fg=self.bg)
        self._style_window_controls(self.bg, self.fg)
        self._apply_image_frame_bg()
        self.win.attributes("-alpha", self.opacity / 100)

    def _apply_light_mode(self):
        self._apply_theme(LIGHT_BG, LIGHT_FG)

    def _apply_dark_mode(self):
        self._apply_theme(DARK_BG, DARK_FG)

    def _toggle_clickthrough(self):
        if not self.clickthrough and not self.manager.config.get("clickthrough_warned", False):
            self.win.lift()
            ok = messagebox.askokcancel(
                "Enable click-through?",
                "Click-through makes this note ignore mouse clicks.\n\n"
                "To turn it back off, right-click the hub strip (+ gear x) and choose "
                "'Disable click-through on all notes'. You can also focus the app and press "
                "Ctrl+Shift+T, or press Ctrl+Alt+Shift+T anywhere on Windows while the "
                "global recovery hotkey is enabled.\n\n"
                "Enable click-through now?",
                parent=self.win,
            )
            if not ok:
                return
            self.manager.config["clickthrough_warned"] = True
            save_config(self.manager.config)
        self._apply_clickthrough(not self.clickthrough)

    def _toggle_ontop(self):
        self.ontop = not self.ontop
        self.win.attributes("-topmost", self.ontop)
        if self.clickthrough:
            self._set_window_clickthrough(True)

    def _start_resize(self, event):
        self.win.update_idletasks()
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._resize_start_w = self.win.winfo_width()
        self._resize_start_h = self.win.winfo_height()

    def _on_resize(self, event):
        dx = event.x_root - self._resize_start_x
        dy = event.y_root - self._resize_start_y
        new_w = max(MIN_NOTE_W, self._resize_start_w + dx)
        new_h = max(MIN_NOTE_H, self._resize_start_h + dy)
        self.win.geometry(f"{new_w}x{new_h}")

    def _start_drag(self, event):
        self.win.lift()
        self._drag_x = event.x_root - self.win.winfo_x()
        self._drag_y = event.y_root - self.win.winfo_y()
        return "break"

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.win.geometry(f"+{x}+{y}")
        return "break"

    def _on_mousewheel(self, event):
        self.label.yview_scroll(int(-1*(event.delta/120)), "units")
        return "break"

    def _start_edit(self, event):
        if self._entry:
            return "break"

        # Rebuild image name map from current label state
        self._image_name_map = {}
        photo_by_name = {str(p): p for p in self._photo_refs}
        for img_frame in self._image_frames:
            photo_by_name[str(img_frame._photo)] = img_frame._photo

        for item_type, value, index in self.label.dump("1.0", "end", all=True):
            if item_type == "image" and value in photo_by_name:
                for img_dict in self._images:
                    if self._image_name_map.get(value) is None:
                        self._image_name_map[value] = img_dict
                        break
            elif item_type == "window":
                for img_frame in self._image_frames:
                    if str(img_frame) == value:
                        tcl_name = str(img_frame._photo)
                        for img_dict in self._images:
                            if self._image_name_map.get(tcl_name) is None:
                                self._image_name_map[tcl_name] = img_dict
                                break
                        break

        self.label.pack_forget()
        self._entry = tk.Text(
            self.frame,
            font=self._font_tuple(),
            bg=self.bg,
            fg=self.fg,
            insertbackground=self.fg,
            relief="flat",
            height=1,
            width=20,
            wrap="word",
            undo=False,
        )

        # Reconstruct entry content from label dump to preserve image positions
        self._entry_photo_refs = []
        for item_type, value, index in self.label.dump("1.0", "end", all=True):
            if item_type == "text":
                self._entry.insert("end", value)
            elif item_type == "image":
                photo = photo_by_name.get(value)
                if photo:
                    self._entry_photo_refs.append(photo)
                    self._entry.image_create("end", image=photo)
            elif item_type == "window":
                for img_frame in self._image_frames:
                    if str(img_frame) == value:
                        photo = img_frame._photo
                        if photo:
                            self._entry_photo_refs.append(photo)
                            self._entry.image_create("end", image=photo)
                        break

        self._entry.pack(padx=LABEL_PADX, pady=LABEL_PADY, fill="both", expand=True)
        self._entry.focus_set()
        self._entry.tag_add("sel", "1.0", "end")
        self._entry.bind("<Return>", self._finish_edit)
        self._entry.bind("<Shift-Return>", self._soft_newline)
        self._entry.bind("<Escape>", self._cancel_edit)
        self._entry.bind("<FocusOut>", self._finish_edit)
        self._entry.bind("<KeyRelease>", self._resize_entry)
        self._entry.bind("<Control-v>", self._paste_image)
        self._entry.bind("<Button-3>", self._show_edit_menu)
        return "break"

    def _entry_cut(self):
        if self._entry:
            self._entry.event_generate("<<Cut>>")
            self._resize_entry(None)

    def _entry_copy(self):
        if self._entry:
            self._entry.event_generate("<<Copy>>")

    def _entry_paste(self):
        if not self._entry:
            return
        if self._paste_image(None) != "break":
            self._entry.event_generate("<<Paste>>")
        self._resize_entry(None)

    def _entry_select_all(self):
        if self._entry:
            end = "end-1c"
            if self._entry.get("1.0", end).endswith("\n"):
                end = "end-2c"
            self._entry.tag_remove("sel", "1.0", "end")
            self._entry.tag_add("sel", "1.0", end)
            self._entry.mark_set("insert", end)

    def _show_edit_menu(self, event):
        if not self._entry:
            return "break"
        self._entry.focus_set()
        menu = tk.Menu(self._entry, tearoff=0)
        menu.add_command(label="Cut", command=self._entry_cut)
        menu.add_command(label="Copy", command=self._entry_copy)
        menu.add_command(label="Paste", command=self._entry_paste)
        menu.add_separator()
        menu.add_command(label="Select all", command=self._entry_select_all)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _finish_edit(self, event=None):
        if not self._entry:
            if event:
                return "break"
            return

        # Step 1: Extract content from entry widget
        text_segments, image_records = _extract_image_records(self._entry)
        plain_text = "".join(text_segments).strip()

        # Step 2: Build new PhotoImage objects for self.label
        new_photo_refs = []
        new_images = []

        if ImageTk is not None:
            for rec in image_records:
                img_dict = self._image_name_map.get(rec["tcl_name"])
                if img_dict is None:
                    continue
                path = img_dict.get("path", "")
                if not os.path.exists(path):
                    continue
                try:
                    photo = ImageTk.PhotoImage(file=path)
                except Exception:
                    continue
                new_photo_refs.append(photo)
                new_images.append({
                    "path": img_dict["path"],
                    "original_path": img_dict["original_path"],
                    "width": img_dict["width"],
                    "height": img_dict["height"],
                    "position": rec["plain_pos"],
                })

        # Step 3: Commit to self.label
        if plain_text:
            self.label.set_text(plain_text)

        # Clear old image frames
        for f in self._image_frames:
            f.destroy()
        self._image_frames = []

        # Re-embed images as window frames
        per_line_count = {}
        for img_dict, photo in zip(new_images, new_photo_refs):
            plain_pos = img_dict["position"]
            try:
                line, col = plain_pos.split(".")
                count = per_line_count.get(line, 0)
                insert_idx = f"{line}.{int(col) + count}"
                per_line_count[line] = count + 1
            except (ValueError, AttributeError):
                insert_idx = "end"
            frame = self._make_image_frame(photo, img_dict)
            self.label.window_create(insert_idx, window=frame)

        # Atomically replace refs
        self._photo_refs = new_photo_refs
        self._images = new_images

        # Step 4: Cleanup
        self._entry_photo_refs = []
        self._entry.destroy()
        self._entry = None

        self.label.pack(padx=0, pady=0, fill="both", expand=True)

        self._apply_checklist_tags()

        if event:
            return "break"

    def _cancel_edit(self, event=None):
        if self._entry:
            self._entry_photo_refs = []
            self._entry.destroy()
            self._entry = None
            self.label.pack(padx=0, pady=0, fill="both", expand=True)

    def _soft_newline(self, event):
        self._entry.insert("insert", "\n")
        return "break"

    def _resize_entry(self, event):
        if self._entry:
            self._entry.update_idletasks()
            lines = int(self._entry.index("end-1c").split(".")[0])
            self._entry.config(height=max(1, min(lines, 10)))

    def _paste_image(self, event):
        if ImageGrab is None:
            return None

        img = ImageGrab.grabclipboard()
        if img is None or not hasattr(img, "size"):
            return None

        _ensure_image_dir()
        uid = uuid.uuid4().hex[:12]
        original_path = os.path.join(IMAGE_DIR, f"img_{uid}.png")
        img.save(original_path)

        max_w = max(50, self.win.winfo_width() - 2 * LABEL_PADX)
        if img.width > max_w:
            ratio = max_w / img.width
            new_w = max_w
            new_h = max(1, int(img.height * ratio))
            display_img = img.resize((new_w, new_h))
        else:
            new_w, new_h = img.width, img.height
            display_img = img

        display_path = os.path.join(IMAGE_DIR, f"img_{uid}_{new_w}x{new_h}.png")
        display_img.save(display_path)

        photo = ImageTk.PhotoImage(display_img)
        tcl_name = str(photo)
        self._entry_photo_refs.append(photo)

        new_dict = {
            "path": display_path,
            "original_path": original_path,
            "width": new_w,
            "height": new_h,
            "position": None,
        }
        self._image_name_map[tcl_name] = new_dict
        self._entry.image_create("insert", image=photo)
        return "break"

    def _resize_image_by_entry(self, img_dict):
        if ImageTk is None:
            return
        try:
            from PIL import Image as PilImage
        except ImportError:
            return

        new_w = simpledialog.askinteger(
            "Resize Image", "New width (px):",
            initialvalue=img_dict["width"], minvalue=10, maxvalue=MAX_W
        )
        if new_w is None:
            return

        orig = PilImage.open(img_dict["original_path"])
        new_h = max(1, int(orig.height * new_w / orig.width))

        orig_filename = os.path.basename(img_dict["original_path"])
        uid = orig_filename.replace("img_", "").replace(".png", "")
        new_path = os.path.join(IMAGE_DIR, f"img_{uid}_{new_w}x{new_h}.png")
        resized = orig.resize((new_w, new_h))
        resized.save(new_path)

        new_photo = ImageTk.PhotoImage(resized)

        # Find and replace the embed in self.label
        for item_type, value, idx in self.label.dump("1.0", "end", image=True):
            for i, ref in enumerate(self._photo_refs):
                if str(ref) == value:
                    self.label.set_readonly(False)
                    self.label.delete(idx)
                    self.label.set_readonly(True)
                    self.label.image_create(idx, image=new_photo)
                    self._photo_refs[i] = new_photo
                    img_dict["path"] = new_path
                    img_dict["width"] = new_w
                    img_dict["height"] = new_h
                    return

    def _resize_image(self, ex, ey):
        idx = self.label.index(f"@{ex},{ey}")
        end_idx = self.label.index(f"{idx}+1c")
        dump = list(self.label.dump(idx, end_idx, image=True))
        if not dump:
            return
        tcl_name = dump[0][1]
        for i, photo in enumerate(self._photo_refs):
            if str(photo) == tcl_name and i < len(self._images):
                self._resize_image_by_entry(self._images[i])
                return
        if self._images:
            self._resize_image_by_entry(self._images[0])

    def _delete_image(self, idx):
        win_dump = list(self.label.dump(idx, self.label.index(f"{idx}+1c"), window=True))
        img_dump = list(self.label.dump(idx, self.label.index(f"{idx}+1c"), image=True))

        if win_dump:
            win_path = win_dump[0][1]
            self.label.set_readonly(False)
            self.label.delete(idx)
            self.label.set_readonly(True)
            for i, frame in enumerate(self._image_frames):
                if str(frame) == win_path:
                    if i < len(self._images):
                        self._images.pop(i)
                    if i < len(self._photo_refs):
                        self._photo_refs.pop(i)
                    self._image_frames.pop(i)
                    frame.destroy()
                    break
        elif img_dump:
            tcl_name = img_dump[0][1]
            self.label.set_readonly(False)
            self.label.delete(idx)
            self.label.set_readonly(True)
            for i, ref in enumerate(self._photo_refs):
                if str(ref) == tcl_name:
                    self._photo_refs.pop(i)
                    if i < len(self._images):
                        self._images.pop(i)
                    break

    def _show_menu(self, event):
        menu = tk.Menu(self.win, tearoff=0)
        # Image hit-test
        img_dump = []
        win_dump = []
        idx = None
        if event.widget is self.label:
            idx = self.label.index(f"@{event.x},{event.y}")
            end_idx = self.label.index(f"{idx}+1c")
            img_dump = list(self.label.dump(idx, end_idx, image=True))
            win_dump = list(self.label.dump(idx, end_idx, window=True))
        if img_dump or win_dump:
            ex, ey = event.x, event.y
            menu.add_command(label="Resize image...", command=lambda: self._resize_image(ex, ey))
            menu.add_command(label="Delete image", command=lambda: self._delete_image(idx))
            menu.add_separator()
        menu.add_command(label="Background color...", command=self._pick_bg)
        menu.add_command(label="Text color...", command=self._pick_fg)
        menu.add_command(label="Light mode", command=self._apply_light_mode)
        menu.add_command(label="Dark mode", command=self._apply_dark_mode)
        menu.add_command(label="Font family...", command=self._pick_font_family)
        menu.add_command(label="Font size...", command=self._pick_font_size)
        menu.add_command(label="Opacity...", command=self._pick_opacity)
        trans_label = "✓ Transparent background" if self.transparent else "Transparent background"
        menu.add_command(label=trans_label, command=self._toggle_transparent)
        ct_label = "✓ Click-through" if self.clickthrough else "Click-through"
        menu.add_command(label=ct_label, command=self._toggle_clickthrough)
        ot_label = "✓ Always on top" if self.ontop else "Always on top"
        menu.add_command(label=ot_label, command=self._toggle_ontop)
        wc_label = "✓ Show window controls" if self.show_window_controls else "Show window controls"
        menu.add_command(label=wc_label, command=self._toggle_window_controls)
        menu.add_separator()
        menu.add_command(label="Duplicate", command=self._duplicate)
        menu.add_command(label="Save as...", command=self._save_as_minimized_group)
        menu.add_command(label="Stash & close", command=self._stash)
        menu.add_command(label="Close", command=self._close)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _pick_bg(self):
        color = colorchooser.askcolor(initialcolor=self.bg, title="Background Color")
        if color[1]:
            self.bg = color[1]
            if not self.transparent:
                self.label.config(bg=self.bg)
                self.frame.config(bg=self.bg)
                self.grip.config(bg=self.bg, fg=self.bg)
                self._style_window_controls(self.bg, self.fg)
                self._apply_image_frame_bg()

    def _pick_fg(self):
        color = colorchooser.askcolor(initialcolor=self.fg, title="Text Color")
        if color[1]:
            self.fg = color[1]
            self.label.config(fg=self.fg)
            self._style_window_controls(self.bg, self.fg)

    def _toggle_window_controls(self):
        self.show_window_controls = not self.show_window_controls
        self._render_titlebar_controls()
        if hasattr(self.manager, "_persist_last_session"):
            self.manager._persist_last_session()

    def _apply_font_family(self, family):
        if not family:
            return
        self.font_family = family
        self.label.config(font=self._font_tuple())
        if self._entry:
            self._entry.config(font=self._font_tuple())

    def _pick_font_family(self):
        _show_font_family_picker(
            self.manager.root,
            self.win,
            "Font family",
            self.bg,
            self.fg,
            self.font_family,
            self.font_size,
            self._apply_font_family,
            "The quick brown fox 123",
        )

    def _pick_font_size(self):
        size = simpledialog.askinteger("Font Size", "Enter font size:", initialvalue=self.font_size, minvalue=6, maxvalue=72)
        if size:
            self.font_size = size
            self.label.config(font=self._font_tuple())
            if self._entry:
                self._entry.config(font=self._font_tuple())

    def _pick_opacity(self):
        popup = tk.Toplevel(self.manager.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.geometry(f"+{self.win.winfo_x()}+{self.win.winfo_y() + self.win.winfo_height() + 5}")

        frame = tk.Frame(popup, bg=self.bg, padx=10, pady=10)
        frame.pack()

        tk.Label(frame, text="Opacity", bg=self.bg, fg=self.fg,
                 font=("Consolas", 9)).pack()

        scale = tk.Scale(frame, from_=20, to=100, orient="horizontal",
                         resolution=5, length=150, bg=self.bg, fg=self.fg,
                         highlightthickness=0, troughcolor="#333333")
        scale.set(self.opacity)
        scale.config(command=lambda val: self.win.attributes("-alpha", int(val) / 100))
        scale.pack()

        def close(e=None):
            self.opacity = scale.get()
            self.win.attributes("-alpha", self.opacity / 100)
            popup.destroy()

        ok_btn = tk.Label(frame, text=" OK ", bg="#333333", fg=self.fg,
                          font=("Consolas", 9, "bold"), cursor="hand2")
        ok_btn.pack(pady=(5, 0))
        ok_btn.bind("<Button-1>", close)
        popup.bind("<Escape>", close)

    def _duplicate(self):
        x = self.win.winfo_x() + 30
        y = self.win.winfo_y() + 30
        self.manager.spawn_label(
            text=self.label.get("1.0", "end-1c"), x=x, y=y, bg=self.bg, fg=self.fg,
            transparent=self.transparent, font_size=self.font_size,
            font_family=self.font_family,
            clickthrough=self.clickthrough,
            images=list(self._images),
        )

    def _save_as_minimized_group(self):
        self.manager._save_single_minimized_group(self)

    def _stash(self):
        import datetime
        data = self.snapshot()
        data["stashed_on"] = datetime.date.today().strftime("%#m/%#d")
        if "stash" not in self.manager.config:
            self.manager.config["stash"] = []
        self.manager.config["stash"].append(data)
        save_config(self.manager.config)
        self._close()

    def _close(self):
        self.win.destroy()
        if self in self.manager.labels:
            self.manager.labels.remove(self)
        if (hasattr(self.manager, "_persist_last_session") and
                not getattr(self.manager, "_suppress_close_persist", False)):
            self.manager._persist_last_session()


class LabelManager:
    def __init__(self, pending_restore=None):
        self.config = load_config()
        self.labels = []
        self.pending_restore = pending_restore

        self.root = tk.Tk()
        self.root.title("Pane Labels")
        self.root.overrideredirect(True)
        self.hub_ontop = self.config.get("hub_always_on_top", True)
        self.root.attributes("-topmost", self.hub_ontop)
        self.root.attributes("-alpha", 1.0)

        bg = self.config["default_bg"]
        fg = self.config["default_fg"]

        self.frame = tk.Frame(self.root, bg=bg)
        self.frame.pack()

        self.add_btn = tk.Label(self.frame, text=" + ", bg=bg, fg=fg,
                                font=("Consolas", 12, "bold"), padx=6, pady=2, cursor="hand2")
        self.add_btn.pack(side="left")
        self._bind_hub_button(self.add_btn, lambda e: self.spawn_label())

        self.settings_btn = tk.Label(self.frame, text=" \u2699 ", bg=bg, fg=fg,
                                     font=("Consolas", 12), padx=6, pady=2, cursor="hand2")
        self.settings_btn.pack(side="left")
        self._bind_hub_button(self.settings_btn, self._show_settings_menu)

        self.close_btn = tk.Label(self.frame, text=" \u00d7 ", bg=bg, fg=fg,
                                  font=("Consolas", 12, "bold"), padx=6, pady=2, cursor="hand2")
        self.close_btn.pack(side="left")
        self._bind_hub_button(self.close_btn, lambda e: self._quit())

        # Hub right-click — presets
        self.frame.bind("<Button-3>", self._show_hub_menu)
        self.add_btn.bind("<Button-3>", self._show_hub_menu)
        self.settings_btn.bind("<Button-3>", self._show_hub_menu)
        self.close_btn.bind("<Button-3>", self._show_hub_menu)

        self.frame.bind("<Button-1>", self._start_drag)
        self.frame.bind("<B1-Motion>", self._on_drag)

        # Plus key hotkey to create new label
        self.root.bind("<plus>", lambda e: self.spawn_label())
        self.root.bind("<KP_Add>", lambda e: self.spawn_label())
        self.root.bind_all("<Control-Shift-T>", lambda e: self._disable_all_clickthrough())
        self.root.bind_all("<Control-Shift-t>", lambda e: self._disable_all_clickthrough())

        self._drag_x = 0
        self._drag_y = 0
        self._hub_press_x_root = 0
        self._hub_press_y_root = 0
        self._hub_dragged = False
        self.global_recovery_hotkey = None
        self._global_recovery_hotkey_poll_after_id = None
        self._start_global_recovery_hotkey()

        threading.Thread(target=self._socket_listener, daemon=True).start()

        self.root.geometry("+10+10")

        # Restore last session
        for ldata in self.config.get("last_session", []):
            self._spawn_from_data(ldata)
        if self.pending_restore:
            self.root.after(0, lambda n=self.pending_restore: self._restore_minimized_group(n))
        self.root.after(200, self._publish_jump_list)

    def _socket_listener(self):
        port = self.config.get("socket_port", 47210)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.listen()
            while True:
                try:
                    conn, _ = s.accept()
                    with conn:
                        data = conn.recv(4096).decode("utf-8", errors="replace").strip()
                        if data:
                            message = _decode_ipc_message(data)
                            self.root.after(0, lambda m=message: self._handle_ipc_message(m))
                except Exception:
                    break

    def _handle_ipc_message(self, message):
        if message.get("type") == "restore_minimized":
            self._restore_minimized_group(message.get("name", ""))
            self._bring_to_front()
            return
        self.spawn_label(text=message.get("text", ""))

    def _bring_to_front(self):
        self.root.lift()
        try:
            self.root.attributes("-topmost", True)
            self.root.after(250, lambda: self.root.attributes("-topmost", self.config.get("hub_always_on_top", True)))
            self.root.focus_force()
        except tk.TclError:
            pass

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _bind_hub_button(self, widget, command):
        widget.bind("<ButtonPress-1>", self._start_hub_button_drag)
        widget.bind("<B1-Motion>", self._on_hub_button_drag)
        widget.bind("<ButtonRelease-1>", lambda e: self._release_hub_button(e, command))

    def _start_hub_button_drag(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()
        self._hub_press_x_root = event.x_root
        self._hub_press_y_root = event.y_root
        self._hub_dragged = False

    def _on_hub_button_drag(self, event):
        if (abs(event.x_root - self._hub_press_x_root) > HUB_DRAG_THRESHOLD_PX or
                abs(event.y_root - self._hub_press_y_root) > HUB_DRAG_THRESHOLD_PX):
            self._hub_dragged = True
        if self._hub_dragged:
            self._on_drag(event)

    def _release_hub_button(self, event, command):
        if not self._hub_dragged:
            command(event)

    def _start_global_recovery_hotkey(self):
        if not self.config.get("global_recovery_hotkey", True):
            return False
        if not GlobalRecoveryHotkey.is_supported():
            return False
        self.global_recovery_hotkey = GlobalRecoveryHotkey(
            self.root,
            self._recover_clickthrough_from_hotkey,
        )
        started = self.global_recovery_hotkey.start()
        if started:
            self._schedule_global_recovery_hotkey_poll()
        return started

    def _stop_global_recovery_hotkey(self):
        if self._global_recovery_hotkey_poll_after_id is not None:
            try:
                self.root.after_cancel(self._global_recovery_hotkey_poll_after_id)
            except Exception:
                pass
            self._global_recovery_hotkey_poll_after_id = None
        if self.global_recovery_hotkey:
            self.global_recovery_hotkey.stop()
            self.global_recovery_hotkey = None

    def _schedule_global_recovery_hotkey_poll(self):
        if self.global_recovery_hotkey and self._global_recovery_hotkey_poll_after_id is None:
            self._global_recovery_hotkey_poll_after_id = self.root.after(
                100,
                self._poll_global_recovery_hotkey,
            )

    def _poll_global_recovery_hotkey(self):
        self._global_recovery_hotkey_poll_after_id = None
        if not self.global_recovery_hotkey:
            return
        try:
            self.global_recovery_hotkey.poll()
        except Exception:
            pass
        finally:
            self._schedule_global_recovery_hotkey_poll()

    def _recover_clickthrough_from_hotkey(self):
        self._disable_all_clickthrough()
        if self.hub_ontop:
            self.root.attributes("-topmost", True)
        self.root.lift()

    def spawn_label(self, text="Label", x=None, y=None, bg=None, fg=None,
                    transparent=None, font_size=None, width=None, height=None,
                    clickthrough=False, ontop=True, images=None, opacity=None,
                    font_family=None, show_window_controls=None):
        if x is None:
            x = self.root.winfo_x() + 50
        if y is None:
            y = self.root.winfo_y() + 50
        label = StickyLabel(self, text=text, x=x, y=y, bg=bg, fg=fg,
                            transparent=transparent, font_size=font_size,
                            font_family=font_family,
                            width=width, height=height, clickthrough=clickthrough, ontop=ontop,
                            images=images, opacity=opacity,
                            show_window_controls=show_window_controls)
        self.labels.append(label)
        return label

    def _spawn_from_data(self, d):
        label = self.spawn_label(
            text=d.get("text", "Label"),
            x=d.get("x", 100), y=d.get("y", 100),
            bg=d.get("bg"), fg=d.get("fg"),
            transparent=d.get("transparent", False),
            font_family=d.get("font_family"),
            font_size=d.get("font_size"),
            width=d.get("width"), height=d.get("height"),
            clickthrough=d.get("clickthrough", False),
            ontop=d.get("ontop", True),
            images=d.get("images", []),
            opacity=d.get("opacity"),
            show_window_controls=d.get("show_window_controls"),
        )
        label.mark_clean_saved()
        return label

    def _get_snapshots(self):
        return [l.snapshot() for l in self.labels]

    def _persist_last_session(self):
        self.config["last_session"] = self._get_snapshots()
        save_config(self.config)

    # --- Hub right-click menu (presets) ---
    def _show_hub_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        ot_label = "✓ Always on top" if self.hub_ontop else "Always on top"
        menu.add_command(label=ot_label, command=self._toggle_hub_ontop)
        if GlobalRecoveryHotkey.is_supported():
            gh_label = "✓ Global recovery hotkey" if self.config.get("global_recovery_hotkey", True) else "Global recovery hotkey"
            menu.add_command(label=gh_label, command=self._toggle_global_recovery_hotkey)
        else:
            menu.add_command(label="Global recovery hotkey (Windows only)", state="disabled")
        menu.add_separator()
        menu.add_command(label="Save preset...", command=self._save_preset)

        presets = self.config.get("presets", {})
        if presets:
            load_menu = tk.Menu(menu, tearoff=0)
            del_menu = tk.Menu(menu, tearoff=0)
            for name in sorted(presets.keys()):
                load_menu.add_command(label=name, command=lambda n=name: self._load_preset(n))
                del_menu.add_command(label=name, command=lambda n=name: self._delete_preset(n))
            menu.add_cascade(label="Load preset", menu=load_menu)
            menu.add_cascade(label="Delete preset", menu=del_menu)

        menu.add_separator()
        minimized_menu = tk.Menu(menu, tearoff=0)
        minimized_menu.add_command(label="Save current as...", command=self._save_minimized_group)
        minimized_groups = self.config.get("minimized_groups", {})
        if minimized_groups:
            minimized_menu.add_separator()
            for name in sorted(minimized_groups.keys()):
                group_menu = tk.Menu(minimized_menu, tearoff=0)
                group_menu.add_command(label="Restore", command=lambda n=name: self._restore_minimized_group(n))
                group_menu.add_command(label="Delete", command=lambda n=name: self._delete_minimized_group(n))
                minimized_menu.add_cascade(
                    label=self._minimized_group_label(name, minimized_groups[name]),
                    menu=group_menu,
                )
        menu.add_cascade(label="Minimized", menu=minimized_menu)

        stash = self.config.get("stash", [])
        if stash:
            menu.add_separator()
            stash_menu = tk.Menu(menu, tearoff=0)
            for i, item in enumerate(stash):
                label = f"{item.get('text', 'Label')} ({item.get('stashed_on', '?')})"
                stash_menu.add_command(label=label, command=lambda idx=i: self._restore_stash(idx))
            stash_menu.add_separator()
            stash_menu.add_command(label="Clear stash", command=self._clear_stash)
            menu.add_cascade(label="Stash", menu=stash_menu)

        if any(label.clickthrough for label in self.labels):
            menu.add_separator()
            menu.add_command(label="Disable click-through on all notes", command=self._disable_all_clickthrough)

        menu.tk_popup(event.x_root, event.y_root)

    def _save_preset(self):
        name = simpledialog.askstring("Save Preset", "Preset name:")
        if name:
            if "presets" not in self.config:
                self.config["presets"] = {}
            self.config["presets"][name] = self._get_snapshots()
            save_config(self.config)

    def _today_label(self):
        return datetime.date.today().isoformat()

    def _display_saved_on(self, saved_on):
        try:
            parsed = datetime.date.fromisoformat(saved_on)
            return f"{parsed.month}/{parsed.day}"
        except (TypeError, ValueError):
            return saved_on or "?"

    def _minimized_group_label(self, name, group):
        count = len(group.get("labels", []))
        suffix = "note" if count == 1 else "notes"
        saved_on = self._display_saved_on(group.get("saved_on"))
        return f"{name} ({count} {suffix} - {saved_on})"

    def _publish_jump_list(self):
        if os.environ.get("SCROLLY_POLLY_DISABLE_JUMPLIST") == "1":
            return False
        if windows_jumplist is None:
            return False
        return windows_jumplist.publish_saved_notes(
            self.config,
            self._minimized_group_label,
            icon_path=_jump_list_icon_path(),
        )

    def _sanitize_auto_name(self, text):
        text = re.sub(r"[\x00-\x1f\x7f]", "", text or "")
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r'[<>:"/\\|?*]', "", text)
        return text.strip().rstrip(".")

    def _truncate_auto_name(self, name, limit=32):
        if len(name) <= limit:
            return name
        boundary = name.rfind(" ", 0, limit + 1)
        if boundary >= 20:
            return name[:boundary].strip().rstrip(".")
        return name[:limit].strip().rstrip(".")

    def _unique_minimized_name(self, base):
        groups = self.config.get("minimized_groups", {})
        existing = {name.casefold() for name in groups}
        candidate = self._truncate_auto_name(base) or "Untitled note"
        if candidate.casefold() not in existing:
            return candidate

        index = 2
        while True:
            suffix = f" {index}"
            trimmed_base = self._truncate_auto_name(base, max(1, 32 - len(suffix))) or "Untitled"
            candidate = f"{trimmed_base}{suffix}"
            if candidate.casefold() not in existing:
                return candidate
            index += 1

    def _auto_minimized_name(self, snapshot):
        text = snapshot.get("text", "")
        source = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                source = stripped
                break
        if not source:
            source = " ".join(text.split())
        base = self._truncate_auto_name(self._sanitize_auto_name(source))
        if not base:
            base = "Image note" if snapshot.get("images") else "Untitled note"
        return self._unique_minimized_name(base)

    def _store_single_minimized_snapshot(self, name, snapshot):
        minimized_groups = dict(self.config.get("minimized_groups", {}))
        minimized_groups[name] = {
            "saved_on": self._today_label(),
            "labels": [snapshot],
        }
        staged_config = dict(self.config)
        staged_config["minimized_groups"] = minimized_groups
        save_config(staged_config)
        self.config = staged_config

    def _auto_minimize_single_label(self, label):
        if label not in self.labels:
            return
        snapshot = label.snapshot()
        name = self._auto_minimized_name(snapshot)
        self._store_single_minimized_snapshot(name, snapshot)
        self._suppress_close_persist = True
        try:
            label._close()
        finally:
            self._suppress_close_persist = False
        self.config["last_session"] = self._get_snapshots()
        save_config(self.config)
        self._publish_jump_list()

    def _save_minimized_group(self):
        if not self.labels:
            messagebox.showinfo("Minimized", "No notes are open to save.")
            return

        name = simpledialog.askstring("Save Minimized Group", "Group name:")
        if name is None:
            return
        name = name.strip()
        if not name:
            return

        minimized_groups = dict(self.config.get("minimized_groups", {}))
        if name in minimized_groups:
            overwrite = messagebox.askyesno(
                "Replace Minimized Group",
                f"Replace the saved minimized group '{name}'?",
            )
            if not overwrite:
                return

        minimized_groups[name] = {
            "saved_on": self._today_label(),
            "labels": self._get_snapshots(),
        }
        staged_config = dict(self.config)
        staged_config["minimized_groups"] = minimized_groups
        save_config(staged_config)
        self.config = staged_config
        self._close_all(persist=False)
        self.config["last_session"] = self._get_snapshots()
        save_config(self.config)
        self._publish_jump_list()

    def _save_single_minimized_group(self, label):
        if label not in self.labels:
            return

        name = simpledialog.askstring("Save Note", "Note name:")
        if name is None:
            return
        name = name.strip()
        if not name:
            return

        minimized_groups = dict(self.config.get("minimized_groups", {}))
        if name in minimized_groups:
            overwrite = messagebox.askyesno(
                "Replace Saved Note",
                f"Replace the saved note '{name}'?",
            )
            if not overwrite:
                return

        self._store_single_minimized_snapshot(name, label.snapshot())
        self._suppress_close_persist = True
        try:
            label._close()
        finally:
            self._suppress_close_persist = False
        self.config["last_session"] = self._get_snapshots()
        save_config(self.config)
        self._publish_jump_list()

    def _restore_minimized_group(self, name):
        group = self.config.get("minimized_groups", {}).get(name)
        if not group:
            return
        for d in group.get("labels", []):
            self._spawn_from_data(d)
        self.config["last_session"] = self._get_snapshots()
        save_config(self.config)

    def _delete_minimized_group(self, name):
        groups = self.config.get("minimized_groups", {})
        if name in groups:
            delete = messagebox.askyesno(
                "Delete Minimized Group",
                f"Delete the saved minimized group '{name}'?",
            )
            if not delete:
                return
            del groups[name]
            self.config["minimized_groups"] = groups
            save_config(self.config)
            self._publish_jump_list()

    def _load_preset(self, name):
        self._close_all()
        for d in self.config["presets"].get(name, []):
            self._spawn_from_data(d)

    def _delete_preset(self, name):
        if name in self.config.get("presets", {}):
            del self.config["presets"][name]
            save_config(self.config)

    def _saved_notes_items(self):
        items = []

        def first_line(text):
            for line in (text or "").splitlines():
                line = line.strip()
                if line:
                    return line
            return ""

        def preview_from_labels(labels):
            for data in labels:
                line = first_line(data.get("text", ""))
                if line:
                    return line
                if data.get("images"):
                    return "Image note"
            return ""

        def date_key(value):
            if not value:
                return ""
            try:
                return datetime.date.fromisoformat(value).isoformat()
            except (TypeError, ValueError):
                return ""

        for name in sorted(self.config.get("minimized_groups", {}).keys()):
            group = self.config["minimized_groups"][name]
            count = len(group.get("labels", []))
            suffix = "note" if count == 1 else "notes"
            saved_on = group.get("saved_on", "?")
            preview = preview_from_labels(group.get("labels", []))
            items.append({
                "kind": "minimized",
                "kind_label": "Minimized",
                "name": name,
                "title": name,
                "date": saved_on,
                "count": count,
                "preview": preview,
                "label": f"[Minimized] {name} | {count} {suffix} | {self._display_saved_on(saved_on)}",
                "search": " ".join(["minimized", name, saved_on or "", preview]).casefold(),
                "sort_date": date_key(saved_on),
            })
        for idx, item in enumerate(self.config.get("stash", [])):
            text = item.get("text", "Label").strip().splitlines()
            title = text[0].strip() if text else "Label"
            if len(title) > 48:
                title = title[:45] + "..."
            preview = ""
            for line in text[1:]:
                if line.strip():
                    preview = line.strip()
                    break
            if not preview:
                preview = title
            saved_on = item.get("stashed_on", "?")
            items.append({
                "kind": "stash",
                "kind_label": "Stash",
                "index": idx,
                "title": title,
                "date": saved_on,
                "count": 1,
                "preview": preview,
                "label": f"[Stash] {title} | 1 note | {self._display_saved_on(saved_on)}",
                "search": " ".join(["stash", title, saved_on or "", preview]).casefold(),
                "sort_date": date_key(saved_on),
            })
        for name in sorted(self.config.get("presets", {}).keys()):
            notes = self.config["presets"].get(name, [])
            count = len(notes)
            suffix = "note" if count == 1 else "notes"
            preview = preview_from_labels(notes)
            items.append({
                "kind": "preset",
                "kind_label": "Preset",
                "name": name,
                "title": name,
                "date": "",
                "count": count,
                "preview": preview,
                "label": f"[Preset] {name} | {count} {suffix}",
                "search": " ".join(["preset", name, preview]).casefold(),
                "sort_date": "",
            })
        return sorted(items, key=lambda item: (item.get("sort_date", ""), item.get("title", "").casefold()), reverse=True)

    def _delete_stash_item(self, idx):
        stash = self.config.get("stash", [])
        if 0 <= idx < len(stash):
            del stash[idx]
            self.config["stash"] = stash
            save_config(self.config)

    def _show_saved_notes_window(self):
        popup = tk.Toplevel(self.root)
        popup.title("Saved notes")
        popup.attributes("-topmost", True)
        popup.geometry(f"680x460+{self.root.winfo_x() + 40}+{self.root.winfo_y() + 40}")

        bg = self.config.get("default_bg", DEFAULT_BG)
        fg = self.config.get("default_fg", DEFAULT_FG)
        frame = tk.Frame(popup, bg=bg, padx=10, pady=10)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Saved notes", bg=bg, fg=fg,
                 font=(DEFAULT_FONT_FAMILY, 11, "bold")).pack(anchor="w")

        search_var = tk.StringVar()
        search = tk.Entry(frame, textvariable=search_var, bg="#ffffff", fg="#000000", relief="flat")
        search.pack(fill="x", pady=(8, 8))

        content = tk.Frame(frame, bg=bg)
        content.pack(fill="both", expand=True, pady=(0, 8))

        list_frame = tk.Frame(content, bg=bg)
        list_frame.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        saved_list = tk.Listbox(
            list_frame,
            activestyle="none",
            exportselection=False,
            yscrollcommand=scrollbar.set,
            bg="#ffffff",
            fg="#000000",
            selectbackground="#2d5f9a",
            selectforeground="#ffffff",
            relief="flat",
        )
        saved_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=saved_list.yview)

        preview_frame = tk.Frame(content, bg=bg, width=220, padx=10)
        preview_frame.pack(side="right", fill="y")
        tk.Label(preview_frame, text="Preview", bg=bg, fg=fg,
                 font=(DEFAULT_FONT_FAMILY, 10, "bold")).pack(anchor="w")
        meta_var = tk.StringVar(value="Select a saved item")
        preview_var = tk.StringVar(value="")
        tk.Label(preview_frame, textvariable=meta_var, bg=bg, fg=fg, justify="left",
                 anchor="nw", wraplength=210).pack(fill="x", pady=(8, 6), anchor="nw")
        tk.Label(preview_frame, textvariable=preview_var, bg=bg, fg=fg, justify="left",
                 anchor="nw", wraplength=210).pack(fill="both", expand=True, anchor="nw")

        items = []
        all_items = []

        def refresh():
            nonlocal items, all_items
            all_items = self._saved_notes_items()
            query = search_var.get().strip().casefold()
            items = [
                item for item in all_items
                if not query or query in item.get("search", "")
            ]
            saved_list.delete(0, "end")
            if not all_items:
                saved_list.insert("end", "No saved notes yet")
                saved_list.config(state="disabled")
                update_preview(None)
                return
            if not items:
                saved_list.insert("end", "No matches")
                saved_list.config(state="disabled")
                update_preview(None)
                return
            saved_list.config(state="normal")
            for item in items:
                saved_list.insert("end", item["label"])
            saved_list.selection_set(0)
            update_preview(items[0])

        def selected_item():
            if not items:
                return None
            selection = saved_list.curselection()
            if not selection:
                return None
            return items[selection[0]]

        def update_preview(item=None):
            if item is None:
                item = selected_item()
            if not item:
                meta_var.set("Select a saved item")
                preview_var.set("")
                return
            suffix = "note" if item.get("count") == 1 else "notes"
            date = item.get("date") or "No date"
            meta_var.set(
                f"{item.get('kind_label', item.get('kind', '') )}\n"
                f"{item.get('title', '')}\n"
                f"{item.get('count', 0)} {suffix} · {date}"
            )
            preview_var.set(item.get("preview") or "No preview")

        def open_selected(event=None):
            item = selected_item()
            if not item:
                return "break"
            if item["kind"] == "minimized":
                self._restore_minimized_group(item["name"])
            elif item["kind"] == "stash":
                self._restore_stash(item["index"])
            elif item["kind"] == "preset":
                self._load_preset(item["name"])
            refresh()
            return "break"

        def delete_selected():
            item = selected_item()
            if not item:
                return
            if item["kind"] == "minimized":
                self._delete_minimized_group(item["name"])
            elif item["kind"] == "stash":
                delete = messagebox.askyesno(
                    "Delete Stashed Note",
                    "Delete this stashed note?",
                    parent=popup,
                )
                if delete:
                    self._delete_stash_item(item["index"])
            elif item["kind"] == "preset":
                delete = messagebox.askyesno(
                    "Delete Preset",
                    f"Delete preset '{item['name']}'?",
                    parent=popup,
                )
                if delete:
                    self._delete_preset(item["name"])
            refresh()

        def open_data_folder():
            folder = os.path.dirname(CONFIG_PATH)
            os.makedirs(folder, exist_ok=True)
            if os.name == "nt":
                os.startfile(folder)
            else:
                messagebox.showinfo("Data folder", folder, parent=popup)

        button_row = tk.Frame(frame, bg=bg)
        button_row.pack(fill="x")
        tk.Button(button_row, text="Open", command=open_selected).pack(side="left")
        tk.Button(button_row, text="Delete", command=delete_selected).pack(side="left", padx=(6, 0))
        tk.Button(button_row, text="Open data folder", command=open_data_folder).pack(side="left", padx=(6, 0))
        tk.Button(button_row, text="Close", command=popup.destroy).pack(side="right")

        saved_list.bind("<Double-Button-1>", open_selected)
        saved_list.bind("<<ListboxSelect>>", lambda e: update_preview())
        search_var.trace_add("write", lambda *args: refresh())
        search.focus_set()
        popup.bind("<Return>", open_selected)
        popup.bind("<Escape>", lambda e: popup.destroy())
        popup._saved_notes_search = search
        popup._saved_notes_list = saved_list
        popup._saved_notes_meta_var = meta_var
        popup._saved_notes_preview_var = preview_var
        popup._saved_notes_refresh = refresh
        refresh()

    def _restore_stash(self, idx):
        stash = self.config.get("stash", [])
        if idx < len(stash):
            item = stash.pop(idx)
            item.pop("stashed_on", None)
            self.config["stash"] = stash
            save_config(self.config)
            self._spawn_from_data(item)

    def _clear_stash(self):
        self.config["stash"] = []
        save_config(self.config)

    def _disable_all_clickthrough(self):
        for label in list(self.labels):
            if label.clickthrough:
                label._apply_clickthrough(False)

    def _toggle_hub_ontop(self):
        self.hub_ontop = not self.hub_ontop
        self.root.attributes("-topmost", self.hub_ontop)
        self.config["hub_always_on_top"] = self.hub_ontop
        save_config(self.config)

    def _toggle_global_recovery_hotkey(self):
        enabled = not self.config.get("global_recovery_hotkey", True)
        if enabled:
            self.config["global_recovery_hotkey"] = True
            if self._start_global_recovery_hotkey():
                save_config(self.config)
            else:
                reason = (
                    self.global_recovery_hotkey.failure_reason()
                    if self.global_recovery_hotkey
                    else f"{GLOBAL_RECOVERY_HOTKEY_LABEL} is unavailable"
                )
                self.config["global_recovery_hotkey"] = False
                self._stop_global_recovery_hotkey()
                save_config(self.config)
                messagebox.showwarning(
                    "Global recovery hotkey unavailable",
                    f"Scrolly Polly Notely could not register {GLOBAL_RECOVERY_HOTKEY_LABEL}: "
                    f"{reason}.\n\nThe hub menu and focused Ctrl+Shift+T recovery still work.",
                    parent=self.root,
                )
        else:
            self.config["global_recovery_hotkey"] = False
            save_config(self.config)
            self._stop_global_recovery_hotkey()

    # --- Gear settings menu ---
    def _show_settings_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Default background...", command=self._set_default_bg)
        menu.add_command(label="Default text color...", command=self._set_default_fg)
        menu.add_command(label="Default font family...", command=self._set_default_font_family)
        menu.add_command(label="Default light mode", command=self._set_default_light_mode)
        menu.add_command(label="Default dark mode", command=self._set_default_dark_mode)
        trans_label = "✓ Default: transparent background" if self.config.get("default_transparent") else "Default: transparent background"
        menu.add_command(label=trans_label, command=self._toggle_default_transparent)
        controls_label = "✓ Default: show window controls" if self.config.get("default_show_window_controls", True) else "Default: show window controls"
        menu.add_command(label=controls_label, command=self._toggle_default_window_controls)
        menu.add_separator()
        menu.add_command(label="Saved notes...", command=self._show_saved_notes_window)
        menu.add_command(label="Close all labels", command=self._close_all)
        menu.tk_popup(event.x_root, event.y_root)

    def _toggle_default_transparent(self):
        self.config["default_transparent"] = not self.config.get("default_transparent", False)
        save_config(self.config)

    def _toggle_default_window_controls(self):
        self.config["default_show_window_controls"] = not self.config.get("default_show_window_controls", True)
        save_config(self.config)

    def _set_default_bg(self):
        color = colorchooser.askcolor(initialcolor=self.config["default_bg"], title="Default Background")
        if color[1]:
            self.config["default_bg"] = color[1]
            save_config(self.config)
            self._update_hub_colors()

    def _set_default_fg(self):
        color = colorchooser.askcolor(initialcolor=self.config["default_fg"], title="Default Text Color")
        if color[1]:
            self.config["default_fg"] = color[1]
            save_config(self.config)
            self._update_hub_colors()

    def _set_default_font_family(self):
        font_size = self.config.get("font_size", DEFAULT_FONT_SIZE)
        current = self.config.get("font_family", DEFAULT_FONT_FAMILY)

        def apply_default(family):
            self.config["font_family"] = family
            save_config(self.config)

        _show_font_family_picker(
            self.root,
            self.root,
            "Default font family",
            self.config["default_bg"],
            self.config["default_fg"],
            current,
            font_size,
            apply_default,
            "New notes will use this font",
        )

    def _set_default_theme(self, bg, fg):
        self.config["default_bg"] = bg
        self.config["default_fg"] = fg
        self.config["default_transparent"] = False
        save_config(self.config)
        self._update_hub_colors()

    def _set_default_light_mode(self):
        self._set_default_theme(LIGHT_BG, LIGHT_FG)

    def _set_default_dark_mode(self):
        self._set_default_theme(DARK_BG, DARK_FG)

    def _update_hub_colors(self):
        bg = self.config["default_bg"]
        fg = self.config["default_fg"]
        self.frame.config(bg=bg)
        self.add_btn.config(bg=bg, fg=fg)
        self.settings_btn.config(bg=bg, fg=fg)
        self.close_btn.config(bg=bg, fg=fg)

    def _close_all(self, persist=True):
        self._suppress_close_persist = True
        try:
            for label in self.labels[:]:
                label._close()
        finally:
            self._suppress_close_persist = False
        if persist:
            self._persist_last_session()

    def _quit(self):
        self._stop_global_recovery_hotkey()
        # Auto-save session on close
        self.config["last_session"] = self._get_snapshots()
        save_config(self.config)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--restore-saved")
    args, _ = parser.parse_known_args(argv)
    return args


def main(argv=None):
    args = _parse_args(argv)
    if windows_jumplist is not None:
        windows_jumplist.set_app_user_model_id()
    if args.restore_saved:
        sent = _send_ipc_command({"type": "restore_minimized", "name": args.restore_saved})
        if sent:
            return 0
    manager = LabelManager(pending_restore=args.restore_saved)
    manager.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
