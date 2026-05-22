import os, sys, shutil, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

TEST_DATA_DIR = os.path.join(tempfile.gettempdir(), "scrolly_polly_notely_tests")
os.environ["SCROLLY_POLLY_NOTELY_DATA_DIR"] = TEST_DATA_DIR
os.environ["SCROLLY_POLLY_DISABLE_JUMPLIST"] = "1"
IMAGE_DIR = os.path.join(TEST_DATA_DIR, "pasted-images")

class TestImageDir(unittest.TestCase):
    def setUp(self):
        if os.path.exists(IMAGE_DIR):
            shutil.rmtree(IMAGE_DIR)

    def test_ensure_image_dir_creates_dir(self):
        import labels
        labels._ensure_image_dir()
        self.assertTrue(os.path.isdir(IMAGE_DIR))

    def test_ensure_image_dir_idempotent(self):
        import labels
        labels._ensure_image_dir()
        labels._ensure_image_dir()
        self.assertTrue(os.path.isdir(IMAGE_DIR))

    def test_config_persists_to_env_data_dir(self):
        if os.path.exists(TEST_DATA_DIR):
            shutil.rmtree(TEST_DATA_DIR)
        import labels
        cfg = labels.load_config()
        cfg["last_session"] = [{"text": "saved in test dir"}]
        labels.save_config(cfg)
        self.assertEqual(labels.CONFIG_PATH, os.path.join(TEST_DATA_DIR, "notes-and-settings.json"))
        self.assertTrue(os.path.exists(labels.CONFIG_PATH))
        loaded = labels.load_config()
        self.assertEqual(loaded["last_session"][0]["text"], "saved in test dir")

    def test_default_config_includes_recovery_settings(self):
        if os.path.exists(TEST_DATA_DIR):
            shutil.rmtree(TEST_DATA_DIR)
        import labels
        cfg = labels.load_config()
        self.assertFalse(cfg["clickthrough_warned"])
        self.assertTrue(cfg["hub_always_on_top"])
        self.assertTrue(cfg["global_recovery_hotkey"])

import tkinter as tk

_root = None

def get_root():
    global _root
    if _root is None:
        _root = tk.Tk()
        _root.withdraw()
    return _root

class TestStickyLabelAttributes(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def _make_label(self):
        return self.labels.StickyLabel(self.mgr, text="Test", x=0, y=0)

    def test_has_image_attributes(self):
        lbl = self._make_label()
        self.assertEqual(lbl._photo_refs, [])
        self.assertEqual(lbl._entry_photo_refs, [])
        self.assertEqual(lbl._images, [])
        self.assertEqual(lbl._image_name_map, {})
        lbl.win.destroy()

    def test_snapshot_includes_images_key(self):
        lbl = self._make_label()
        snap = lbl.snapshot()
        self.assertIn("images", snap)
        self.assertEqual(snap["images"], [])
        lbl.win.destroy()

    def test_snapshot_images_reflects_state(self):
        lbl = self._make_label()
        fake = {"path": "pasted-images/x.png", "original_path": "pasted-images/x.png",
                "width": 100, "height": 80, "position": "1.0"}
        lbl._images = [fake]
        snap = lbl.snapshot()
        self.assertEqual(len(snap["images"]), 1)
        self.assertEqual(snap["images"][0]["path"], "pasted-images/x.png")
        lbl.win.destroy()

    def test_has_visible_minimize_save_button(self):
        lbl = self._make_label()
        self.assertEqual(lbl.titlebar.cget("bg"), lbl.bg)
        self.assertEqual(lbl.frame.cget("cursor"), "arrow")
        self.assertEqual(lbl.label.cget("cursor"), "arrow")
        self.assertEqual(lbl.titlebar.cget("cursor"), "fleur")
        self.assertEqual(int(lbl.titlebar.cget("height")), 24)
        self.assertGreaterEqual(lbl.win.winfo_height(), self.labels.MIN_NOTE_H)
        self.assertTrue(lbl.titlebar.bind("<Button-1>"))
        self.assertTrue(lbl.titlebar.bind("<Motion>"))
        lbl.win.update()
        width = lbl.titlebar.winfo_width()
        centers = lbl._titlebar_control_centers
        self.assertEqual(centers["minimize"], width - 96)
        self.assertEqual(centers["maximize"], width - 54)
        self.assertEqual(centers["close"], width - 18)
        self.assertGreater(centers["minimize"], width / 2)
        control_items = lbl.titlebar.find_withtag("window_control")
        self.assertGreaterEqual(len(control_items), 4)
        self.assertTrue(lbl.titlebar.find_withtag("minimize"))
        self.assertTrue(lbl.titlebar.find_withtag("maximize"))
        self.assertTrue(lbl.titlebar.find_withtag("close"))
        self.assertEqual(lbl._titlebar_control_rects["close"], (width - 34, 0, width, 24))
        event = type("Event", (), {"x": centers["minimize"], "y": 12})()
        self.assertEqual(lbl._titlebar_hit_control(event), "minimize")
        event.x = centers["maximize"]
        self.assertEqual(lbl._titlebar_hit_control(event), "maximize")
        event.x = centers["close"]
        self.assertEqual(lbl._titlebar_hit_control(event), "close")
        event.x = width - 76
        self.assertIsNone(lbl._titlebar_hit_control(event))
        lbl._on_titlebar_motion(event)
        self.assertEqual(lbl.titlebar.cget("cursor"), "fleur")
        event.x = centers["close"]
        lbl._on_titlebar_motion(event)
        self.assertEqual(lbl.titlebar.cget("cursor"), "hand2")
        event.x = 0
        lbl._on_titlebar_motion(event)
        self.assertEqual(lbl.titlebar.cget("cursor"), "fleur")
        lbl.win.destroy()

    def test_can_hide_window_controls_for_label_mode(self):
        import unittest.mock as mock
        lbl = self._make_label()
        self.mgr.labels.append(lbl)

        with mock.patch.object(self.mgr, "_persist_last_session") as persist:
            lbl._toggle_window_controls()

        self.assertFalse(lbl.show_window_controls)
        self.assertEqual(lbl.titlebar.find_withtag("window_control"), ())
        self.assertEqual(lbl._titlebar_control_rects, {})
        event = type("Event", (), {"x": lbl.titlebar.winfo_width() - 18, "y": 12})()
        self.assertIsNone(lbl._titlebar_hit_control(event))
        self.assertFalse(lbl.snapshot()["show_window_controls"])
        persist.assert_called_once()
        lbl.win.destroy()

    def test_maximize_restore_toggles_geometry(self):
        lbl = self._make_label()
        lbl.win.update_idletasks()
        original = lbl.win.geometry()
        lbl._toggle_maximize_restore()
        self.assertTrue(lbl._maximized)
        self.assertNotEqual(lbl.win.geometry(), original)
        lbl._toggle_maximize_restore()
        self.assertFalse(lbl._maximized)
        self.assertEqual(lbl.win.geometry(), original)
        lbl.win.destroy()

    def test_close_button_cancel_keeps_note(self):
        import unittest.mock as mock
        lbl = self._make_label()
        self.mgr.labels.append(lbl)
        with mock.patch("labels.messagebox.askyesnocancel", return_value=None):
            lbl._request_close()
        self.assertIn(lbl, self.mgr.labels)
        self.assertTrue(lbl.win.winfo_exists())
        lbl.win.destroy()

    def test_close_button_discard_closes_note(self):
        import unittest.mock as mock
        lbl = self._make_label()
        self.mgr.labels.append(lbl)
        with mock.patch("labels.messagebox.askyesnocancel", return_value=False):
            lbl._request_close()
        self.assertNotIn(lbl, self.mgr.labels)
        self.assertEqual(self.mgr.config["last_session"], [])

    def test_close_button_save_auto_names_and_closes_note(self):
        import unittest.mock as mock
        lbl = self._make_label()
        self.mgr.labels.append(lbl)
        with mock.patch("labels.messagebox.askyesnocancel", return_value=True), \
             mock.patch("labels.simpledialog.askstring") as askstring, \
             mock.patch("labels.save_config"):
            lbl._request_close()
        askstring.assert_not_called()
        self.assertNotIn(lbl, self.mgr.labels)
        self.assertIn("Test", self.mgr.config["minimized_groups"])
        saved = self.mgr.config["minimized_groups"]["Test"]["labels"][0]
        self.assertEqual(saved["text"], "Test")

    def test_close_clean_saved_note_skips_save_prompt(self):
        import unittest.mock as mock
        lbl = self._make_label()
        self.mgr.labels.append(lbl)
        lbl.mark_clean_saved()

        with mock.patch("labels.messagebox.askyesnocancel") as ask, \
             mock.patch("labels.simpledialog.askstring") as askstring, \
             mock.patch("labels.save_config"):
            lbl._request_close()

        ask.assert_not_called()
        askstring.assert_not_called()
        self.assertNotIn(lbl, self.mgr.labels)
        self.assertEqual(self.mgr.config.get("minimized_groups", {}), {})

    def test_clean_saved_note_movement_does_not_trigger_save_prompt(self):
        import unittest.mock as mock
        lbl = self._make_label()
        self.mgr.labels.append(lbl)
        lbl.mark_clean_saved()
        lbl.win.geometry("260x140+45+55")

        with mock.patch("labels.messagebox.askyesnocancel") as ask, \
             mock.patch("labels.save_config"):
            lbl._request_close()

        ask.assert_not_called()
        self.assertNotIn(lbl, self.mgr.labels)

    def test_changed_saved_note_still_prompts_on_close(self):
        import unittest.mock as mock
        lbl = self._make_label()
        self.mgr.labels.append(lbl)
        lbl.mark_clean_saved()
        lbl.label.set_text("Changed")

        with mock.patch("labels.messagebox.askyesnocancel", return_value=None) as ask:
            lbl._request_close()

        ask.assert_called_once()
        self.assertIn(lbl, self.mgr.labels)
        lbl.win.destroy()

class TestIpcAndJumpList(unittest.TestCase):
    def test_ipc_command_round_trips_and_plain_text_stays_text(self):
        import labels
        command = {"type": "restore_minimized", "name": "Work"}
        encoded = labels._encode_ipc_command(command)
        self.assertEqual(labels._decode_ipc_message(encoded), command)
        self.assertEqual(labels._decode_ipc_message("plain note"), {"type": "text", "text": "plain note"})

    def test_jump_list_entries_use_saved_note_labels(self):
        import labels, windows_jumplist
        cfg = {
            "minimized_groups": {
                "beta": {"saved_on": "2026-05-20", "labels": [{"text": "b"}]},
                "alpha": {"saved_on": "2026-05-21", "labels": [{"text": "a"}, {"text": "b"}]},
            }
        }
        mgr = labels.LabelManager.__new__(labels.LabelManager)
        entries = windows_jumplist.build_saved_note_entries(cfg, mgr._minimized_group_label)
        self.assertEqual([e["name"] for e in entries], ["alpha", "beta"])
        self.assertEqual(entries[0]["title"], "alpha (2 notes - 5/21)")
        self.assertEqual(entries[1]["title"], "beta (1 note - 5/20)")

    def test_handle_restore_ipc_restores_without_removing_group(self):
        import labels, unittest.mock as mock
        root = get_root()
        mgr = labels.LabelManager.__new__(labels.LabelManager)
        mgr.config = labels.load_config()
        mgr.config["minimized_groups"] = {
            "work": {"saved_on": "2026-05-21", "labels": [{"text": "restored", "x": 0, "y": 0}]}
        }
        mgr.config["last_session"] = []
        mgr.labels = []
        mgr.root = root
        mgr.frame = tk.Frame(root)
        with mock.patch("labels.save_config"):
            mgr._handle_ipc_message({"type": "restore_minimized", "name": "work"})
        self.assertEqual(len(mgr.labels), 1)
        self.assertIn("work", mgr.config["minimized_groups"])
        for lbl in mgr.labels[:]:
            lbl.win.destroy()
        mgr.labels = []

class TestSpawnFromDataImages(unittest.TestCase):
    def setUp(self):
        import labels, shutil
        self.labels = labels
        self.root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = self.root
        self.mgr.frame = tk.Frame(self.root)
        labels._ensure_image_dir()
        self.test_png = os.path.join(labels.IMAGE_DIR, "test_img_100x50.png")
        try:
            from PIL import Image as PilImage
            img = PilImage.new("RGB", (100, 50), color=(255, 0, 0))
            img.save(self.test_png)
        except ImportError:
            self.skipTest("Pillow not installed")

    def tearDown(self):
        if os.path.exists(self.test_png):
            os.remove(self.test_png)

    def test_spawn_from_data_with_image_loads_it(self):
        data = {
            "text": "hello",
            "x": 0, "y": 0,
            "images": [{
                "path": self.test_png,
                "original_path": self.test_png,
                "width": 100, "height": 50,
                "position": "1.5"
            }]
        }
        self.mgr._spawn_from_data(data)
        lbl = self.mgr.labels[-1]
        self.assertEqual(len(lbl._images), 1)
        self.assertEqual(len(lbl._photo_refs), 1)
        lbl.win.destroy()

    def test_spawn_from_data_missing_file_skips(self):
        data = {
            "text": "hello",
            "x": 0, "y": 0,
            "images": [{
                "path": "pasted-images/nonexistent.png",
                "original_path": "pasted-images/nonexistent.png",
                "width": 100, "height": 50,
                "position": "1.0"
            }]
        }
        self.mgr._spawn_from_data(data)
        lbl = self.mgr.labels[-1]
        self.assertEqual(len(lbl._images), 0)
        lbl.win.destroy()


class TestPasteImage(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)
        labels._ensure_image_dir()

    def _make_label_in_edit(self):
        lbl = self.labels.StickyLabel(self.mgr, text="Hi", x=0, y=0)
        lbl._entry = tk.Text(lbl.frame, undo=False)
        lbl._entry.insert("1.0", "Hi")
        lbl._entry.pack()
        return lbl

    def test_paste_image_with_no_clipboard_image_returns_none(self):
        try:
            from PIL import ImageGrab
        except ImportError:
            self.skipTest("Pillow not installed")
        import unittest.mock as mock
        lbl = self._make_label_in_edit()
        with mock.patch("labels.ImageGrab.grabclipboard", return_value=None):
            result = lbl._paste_image(None)
        self.assertIsNone(result)
        lbl.win.destroy()

    def test_paste_image_creates_file_and_embeds(self):
        try:
            from PIL import Image as PilImage, ImageGrab
        except ImportError:
            self.skipTest("Pillow not installed")
        import unittest.mock as mock
        lbl = self._make_label_in_edit()
        fake_img = PilImage.new("RGB", (200, 100), color=(0, 128, 0))
        with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake_img):
            result = lbl._paste_image(None)
        self.assertEqual(result, "break")
        self.assertEqual(len(lbl._entry_photo_refs), 1)
        import glob
        pngs = glob.glob(os.path.join(self.labels.IMAGE_DIR, "*.png"))
        self.assertTrue(len(pngs) >= 1)
        for f in pngs:
            os.remove(f)
        lbl.win.destroy()


class TestFinishEditRoundTrip(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)
        labels._ensure_image_dir()

    def test_finish_edit_plain_text_round_trips(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hello", x=0, y=0)
        lbl._start_edit(None)
        lbl._entry.delete("1.0", "end")
        lbl._entry.insert("1.0", "world")
        lbl._finish_edit(None)
        self.assertEqual(lbl.label.get("1.0", "end-1c"), "world")
        lbl.win.destroy()

    def test_finish_edit_with_image_preserves_image(self):
        try:
            from PIL import Image as PilImage
        except ImportError:
            self.skipTest("Pillow not installed")
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._start_edit(None)
        fake_img = PilImage.new("RGB", (50, 30), color=(255, 0, 0))
        with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake_img):
            lbl._paste_image(None)
        lbl._finish_edit(None)
        self.assertEqual(len(lbl._images), 1)
        self.assertEqual(len(lbl._photo_refs), 1)
        for img_dict in lbl._images:
            for key in ("path", "original_path"):
                p = img_dict.get(key, "")
                if os.path.exists(p):
                    os.remove(p)
        lbl.win.destroy()


class TestTextReflow(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def test_label_width_changes_on_window_resize(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hello", x=0, y=0, width=200, height=100)
        lbl.win.update_idletasks()
        w1 = lbl.label.cget("width")
        # Simulate resize to wider
        lbl.win.geometry("400x100+0+0")
        lbl.win.update_idletasks()
        lbl._on_window_resize(None)
        w2 = lbl.label.cget("width")
        self.assertGreater(w2, w1)
        lbl.win.destroy()


class TestOpacity(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def test_default_opacity_is_100(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.assertEqual(lbl.opacity, 100)
        lbl.win.destroy()

    def test_custom_opacity_applied(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0, opacity=50)
        self.assertEqual(lbl.opacity, 50)
        alpha = lbl.win.attributes("-alpha")
        self.assertAlmostEqual(float(alpha), 0.50, places=1)
        lbl.win.destroy()

    def test_snapshot_includes_opacity(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0, opacity=70)
        snap = lbl.snapshot()
        self.assertEqual(snap["opacity"], 70)
        lbl.win.destroy()

    def test_spawn_from_data_restores_opacity(self):
        data = {"text": "hi", "x": 0, "y": 0, "opacity": 60}
        self.mgr._spawn_from_data(data)
        lbl = self.mgr.labels[-1]
        self.assertEqual(lbl.opacity, 60)
        lbl.win.destroy()


class TestThemeModes(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = {
            "default_bg": labels.DEFAULT_BG,
            "default_fg": labels.DEFAULT_FG,
            "font_size": labels.DEFAULT_FONT_SIZE,
            "default_transparent": False,
            "global_recovery_hotkey": True,
            "last_session": [],
            "presets": {},
        }
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.global_recovery_hotkey = None
        self.mgr._global_recovery_hotkey_poll_after_id = None
        self.mgr.frame = tk.Frame(root, bg=labels.DEFAULT_BG)
        self.mgr.add_btn = tk.Label(self.mgr.frame, bg=labels.DEFAULT_BG, fg=labels.DEFAULT_FG)
        self.mgr.settings_btn = tk.Label(self.mgr.frame, bg=labels.DEFAULT_BG, fg=labels.DEFAULT_FG)
        self.mgr.close_btn = tk.Label(self.mgr.frame, bg=labels.DEFAULT_BG, fg=labels.DEFAULT_FG)

    def test_light_mode_sets_existing_appearance_fields(self):
        lbl = self.labels.StickyLabel(
            self.mgr, text="hi", x=0, y=0,
            bg=self.labels.DEFAULT_BG, fg=self.labels.DEFAULT_FG,
            transparent=True,
        )
        lbl._apply_light_mode()
        self.assertEqual(lbl.bg, self.labels.LIGHT_BG)
        self.assertEqual(lbl.fg, self.labels.LIGHT_FG)
        self.assertFalse(lbl.transparent)
        self.assertEqual(lbl.label.cget("bg"), self.labels.LIGHT_BG)
        self.assertEqual(lbl.label.cget("fg"), self.labels.LIGHT_FG)
        snap = lbl.snapshot()
        self.assertEqual(snap["bg"], self.labels.LIGHT_BG)
        self.assertEqual(snap["fg"], self.labels.LIGHT_FG)
        self.assertFalse(snap["transparent"])
        lbl.win.destroy()

    def test_light_mode_updates_image_frame_backgrounds(self):
        lbl = self.labels.StickyLabel(
            self.mgr, text="hi", x=0, y=0,
            bg=self.labels.DEFAULT_BG, fg=self.labels.DEFAULT_FG,
        )
        photo = tk.PhotoImage(width=1, height=1)
        lbl._photo_refs.append(photo)
        frame = lbl._make_image_frame(photo, {
            "path": "pasted-images/x.png",
            "original_path": "pasted-images/x.png",
            "width": 1,
            "height": 1,
            "position": "1.0",
        })
        lbl._apply_light_mode()
        self.assertEqual(frame.cget("bg"), self.labels.LIGHT_BG)
        self.assertEqual(frame._img_label.cget("bg"), self.labels.LIGHT_BG)
        grip = [child for child in frame.winfo_children() if child is not frame._img_label][0]
        self.assertEqual(grip.cget("bg"), self.labels.LIGHT_BG)
        self.assertEqual(grip.cget("fg"), self.labels.LIGHT_BG)
        lbl.win.destroy()

    def test_dark_mode_sets_black_and_white(self):
        lbl = self.labels.StickyLabel(
            self.mgr, text="hi", x=0, y=0,
            bg=self.labels.LIGHT_BG, fg=self.labels.LIGHT_FG,
            transparent=True,
        )
        lbl._apply_dark_mode()
        self.assertEqual(lbl.bg, self.labels.DARK_BG)
        self.assertEqual(lbl.fg, self.labels.DARK_FG)
        self.assertFalse(lbl.transparent)
        self.assertEqual(lbl.label.cget("bg"), self.labels.DARK_BG)
        self.assertEqual(lbl.label.cget("fg"), self.labels.DARK_FG)
        lbl.win.destroy()

    def test_light_mode_snapshot_round_trips_through_spawn(self):
        lbl = self.labels.StickyLabel(
            self.mgr, text="hi", x=0, y=0,
            bg=self.labels.DEFAULT_BG, fg=self.labels.DEFAULT_FG,
            transparent=True,
        )
        lbl._apply_light_mode()
        data = lbl.snapshot()
        lbl.win.destroy()

        self.mgr._spawn_from_data(data)
        restored = self.mgr.labels[-1]
        self.assertEqual(restored.bg, self.labels.LIGHT_BG)
        self.assertEqual(restored.fg, self.labels.LIGHT_FG)
        self.assertFalse(restored.transparent)
        self.assertEqual(restored.label.cget("bg"), self.labels.LIGHT_BG)
        self.assertEqual(restored.label.cget("fg"), self.labels.LIGHT_FG)
        restored.win.destroy()

    def test_default_light_mode_reuses_existing_default_fields(self):
        import unittest.mock as mock
        with mock.patch("labels.save_config"):
            self.mgr._set_default_light_mode()
        self.assertEqual(self.mgr.config["default_bg"], self.labels.LIGHT_BG)
        self.assertEqual(self.mgr.config["default_fg"], self.labels.LIGHT_FG)
        self.assertFalse(self.mgr.config["default_transparent"])

    def test_default_dark_mode_reuses_existing_default_fields(self):
        import unittest.mock as mock
        self.mgr.config["default_bg"] = self.labels.LIGHT_BG
        self.mgr.config["default_fg"] = self.labels.LIGHT_FG
        self.mgr.config["default_transparent"] = True
        with mock.patch("labels.save_config"):
            self.mgr._set_default_dark_mode()
        self.assertEqual(self.mgr.config["default_bg"], self.labels.DARK_BG)
        self.assertEqual(self.mgr.config["default_fg"], self.labels.DARK_FG)
        self.assertFalse(self.mgr.config["default_transparent"])

    def test_transparent_mode_uses_non_text_key_color(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_transparent(True)
        self.assertEqual(lbl.label.cget("bg"), self.labels.TRANSPARENT_KEY)
        self.assertNotEqual(self.labels.TRANSPARENT_KEY.lower(), self.labels.DARK_BG)
        self.assertNotEqual(self.labels.TRANSPARENT_KEY.lower(), self.labels.DARK_FG)
        self.assertNotEqual(self.labels.TRANSPARENT_KEY.lower(), self.labels.LIGHT_BG)
        self.assertNotEqual(self.labels.TRANSPARENT_KEY.lower(), self.labels.LIGHT_FG)
        lbl.win.destroy()

    def test_clickthrough_toggle_tracks_state_and_restores_topmost(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        with mock.patch.object(lbl, "_set_window_clickthrough", return_value=True) as style:
            lbl._apply_clickthrough(True)
            self.assertTrue(lbl.clickthrough)
            lbl._apply_clickthrough(False)
            self.assertFalse(lbl.clickthrough)
        self.assertEqual(style.call_count, 2)
        self.assertEqual(lbl.win.attributes("-topmost"), lbl.ontop)
        lbl.win.destroy()

    def test_disable_all_clickthrough_turns_off_each_note(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.mgr.labels.append(lbl)
        with mock.patch.object(lbl, "_set_window_clickthrough", return_value=True):
            lbl._apply_clickthrough(True)
            self.mgr._disable_all_clickthrough()
        self.assertFalse(lbl.clickthrough)
        lbl.win.destroy()

    def test_clickthrough_first_enable_warns_and_can_cancel(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.mgr.config["clickthrough_warned"] = False
        with mock.patch("labels.messagebox.askokcancel", return_value=False) as ask, \
             mock.patch.object(lbl, "_set_window_clickthrough", return_value=True) as style:
            lbl._toggle_clickthrough()
        ask.assert_called_once()
        style.assert_not_called()
        self.assertFalse(lbl.clickthrough)
        self.assertFalse(self.mgr.config["clickthrough_warned"])
        lbl.win.destroy()

    def test_clickthrough_first_enable_persists_warning_ack(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.mgr.config["clickthrough_warned"] = False
        with mock.patch("labels.messagebox.askokcancel", return_value=True) as ask, \
             mock.patch("labels.save_config") as save, \
             mock.patch.object(lbl, "_set_window_clickthrough", return_value=True) as style:
            lbl._toggle_clickthrough()
        _, kwargs = ask.call_args
        self.assertEqual(kwargs["parent"], lbl.win)
        self.assertTrue(lbl.clickthrough)
        self.assertTrue(self.mgr.config["clickthrough_warned"])
        save.assert_called_once_with(self.mgr.config)
        style.assert_called_once_with(True)
        lbl.win.destroy()

    def test_clickthrough_skips_warning_after_ack(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.mgr.config["clickthrough_warned"] = True
        with mock.patch("labels.messagebox.askokcancel") as ask, \
             mock.patch.object(lbl, "_set_window_clickthrough", return_value=True):
            lbl._toggle_clickthrough()
        ask.assert_not_called()
        self.assertTrue(lbl.clickthrough)
        lbl.win.destroy()

    def test_hub_always_on_top_toggle_persists(self):
        import unittest.mock as mock
        self.mgr.hub_ontop = True
        self.mgr.config["hub_always_on_top"] = True
        with mock.patch("labels.save_config") as save:
            self.mgr._toggle_hub_ontop()
        self.assertFalse(self.mgr.hub_ontop)
        self.assertFalse(self.mgr.config["hub_always_on_top"])
        self.assertFalse(bool(self.mgr.root.attributes("-topmost")))
        save.assert_called_once_with(self.mgr.config)

    def test_hub_button_release_click_runs_command(self):
        called = []
        self.mgr._hub_dragged = False
        event = type("E", (), {})()
        self.mgr._release_hub_button(event, lambda e: called.append(e))
        self.assertEqual(called, [event])

    def test_hub_button_release_after_drag_skips_command(self):
        called = []
        self.mgr._hub_dragged = True
        event = type("E", (), {})()
        self.mgr._release_hub_button(event, lambda e: called.append(e))
        self.assertEqual(called, [])

    def test_hub_button_drag_threshold_classifies_motion(self):
        import unittest.mock as mock
        event = type("E", (), {})()
        self.mgr._hub_press_x_root = 100
        self.mgr._hub_press_y_root = 100
        self.mgr._hub_dragged = False

        event.x_root = 100 + self.labels.HUB_DRAG_THRESHOLD_PX
        event.y_root = 100
        self.mgr._on_hub_button_drag(event)
        self.assertFalse(self.mgr._hub_dragged)

        event.x_root = 100 + self.labels.HUB_DRAG_THRESHOLD_PX + 1
        with mock.patch.object(self.mgr, "_on_drag") as drag:
            self.mgr._on_hub_button_drag(event)
        self.assertTrue(self.mgr._hub_dragged)
        drag.assert_called_once_with(event)

    def test_manager_binds_clickthrough_recovery_hotkeys(self):
        import inspect
        source = inspect.getsource(self.labels.LabelManager.__init__)
        self.assertIn('bind_all("<Control-Shift-T>"', source)
        self.assertIn('bind_all("<Control-Shift-t>"', source)

    def test_start_global_recovery_hotkey_uses_worker_on_windows(self):
        import unittest.mock as mock
        self.mgr.config["global_recovery_hotkey"] = True
        self.mgr.global_recovery_hotkey = None
        with mock.patch("labels.GlobalRecoveryHotkey") as hotkey:
            hotkey.is_supported.return_value = True
            hotkey.return_value.start.return_value = True
            with mock.patch.object(self.mgr.root, "after", return_value="after-1") as after:
                result = self.mgr._start_global_recovery_hotkey()
        self.assertTrue(result)
        hotkey.assert_called_once_with(self.mgr.root, self.mgr._recover_clickthrough_from_hotkey)
        hotkey.return_value.start.assert_called_once()
        after.assert_called_once_with(100, self.mgr._poll_global_recovery_hotkey)
        self.assertEqual(self.mgr._global_recovery_hotkey_poll_after_id, "after-1")

    def test_start_global_recovery_hotkey_skips_when_disabled(self):
        import unittest.mock as mock
        self.mgr.config["global_recovery_hotkey"] = False
        self.mgr.global_recovery_hotkey = None
        with mock.patch("labels.GlobalRecoveryHotkey") as hotkey:
            result = self.mgr._start_global_recovery_hotkey()
        self.assertFalse(result)
        hotkey.assert_not_called()

    def test_toggle_global_recovery_hotkey_stops_existing_worker(self):
        import unittest.mock as mock
        worker = mock.Mock()
        self.mgr.global_recovery_hotkey = worker
        self.mgr._global_recovery_hotkey_poll_after_id = "after-1"
        self.mgr.config["global_recovery_hotkey"] = True
        with mock.patch("labels.save_config") as save, \
             mock.patch.object(self.mgr.root, "after_cancel") as after_cancel:
            self.mgr._toggle_global_recovery_hotkey()
        self.assertFalse(self.mgr.config["global_recovery_hotkey"])
        self.assertIsNone(self.mgr.global_recovery_hotkey)
        self.assertIsNone(self.mgr._global_recovery_hotkey_poll_after_id)
        worker.stop.assert_called_once()
        after_cancel.assert_called_once_with("after-1")
        save.assert_called_once_with(self.mgr.config)

    def test_toggle_global_recovery_hotkey_enable_saves_on_success(self):
        import unittest.mock as mock
        self.mgr.config["global_recovery_hotkey"] = False
        with mock.patch.object(self.mgr, "_start_global_recovery_hotkey", return_value=True) as start, \
             mock.patch("labels.save_config") as save:
            self.mgr._toggle_global_recovery_hotkey()
        start.assert_called_once()
        self.assertTrue(self.mgr.config["global_recovery_hotkey"])
        save.assert_called_once_with(self.mgr.config)

    def test_toggle_global_recovery_hotkey_enable_reverts_on_failure(self):
        import unittest.mock as mock
        worker = mock.Mock()
        worker.failure_reason.return_value = "shortcut conflict"
        self.mgr.global_recovery_hotkey = worker
        self.mgr.config["global_recovery_hotkey"] = False
        with mock.patch.object(self.mgr, "_start_global_recovery_hotkey", return_value=False), \
             mock.patch("labels.save_config") as save, \
             mock.patch("labels.messagebox.showwarning") as warning:
            self.mgr._toggle_global_recovery_hotkey()
        self.assertFalse(self.mgr.config["global_recovery_hotkey"])
        self.assertIsNone(self.mgr.global_recovery_hotkey)
        worker.stop.assert_called_once()
        save.assert_called_once_with(self.mgr.config)
        warning.assert_called_once()
        self.assertIn("shortcut conflict", warning.call_args.args[1])

    def test_global_recovery_hotkey_fire_queues_recovery_for_poll(self):
        import unittest.mock as mock
        root = mock.Mock()
        callback = mock.Mock()
        hotkey = self.labels.GlobalRecoveryHotkey(root, callback)
        hotkey._schedule_callback()
        root.after.assert_not_called()
        hotkey.poll()
        callback.assert_called_once()

    def test_global_recovery_hotkey_unsupported_off_windows(self):
        import unittest.mock as mock
        with mock.patch.object(self.labels.sys, "platform", "linux"):
            self.assertFalse(self.labels.GlobalRecoveryHotkey.is_supported())
            root = mock.Mock()
            hotkey = self.labels.GlobalRecoveryHotkey(root, mock.Mock())
            self.assertFalse(hotkey.start())
            root.after.assert_not_called()

    def test_global_recovery_warning_names_conflict(self):
        import io
        import unittest.mock as mock
        hotkey = self.labels.GlobalRecoveryHotkey(mock.Mock(), mock.Mock())
        hotkey._start_error = self.labels.GlobalRecoveryHotkey.ERROR_HOTKEY_ALREADY_REGISTERED
        stream = io.StringIO()
        with mock.patch("labels.sys.stderr", stream):
            hotkey._warn_start_error()
        self.assertIn("already registered by another app", stream.getvalue())

    def test_global_recovery_failure_reason_stringifies_exception(self):
        import unittest.mock as mock
        hotkey = self.labels.GlobalRecoveryHotkey(mock.Mock(), mock.Mock())
        hotkey._start_error = RuntimeError("boom")
        self.assertEqual(hotkey.failure_reason(), "boom")

    def test_global_recovery_poll_reschedules_after_exception(self):
        import unittest.mock as mock
        worker = mock.Mock()
        worker.poll.side_effect = RuntimeError("during shutdown")
        self.mgr.global_recovery_hotkey = worker
        self.mgr._global_recovery_hotkey_poll_after_id = "old"
        with mock.patch.object(self.mgr.root, "after", return_value="new") as after:
            self.mgr._poll_global_recovery_hotkey()
        worker.poll.assert_called_once()
        after.assert_called_once_with(100, self.mgr._poll_global_recovery_hotkey)
        self.assertEqual(self.mgr._global_recovery_hotkey_poll_after_id, "new")

    def test_recover_clickthrough_from_hotkey_disables_and_lifts_hub(self):
        import unittest.mock as mock
        self.mgr.hub_ontop = True
        with mock.patch.object(self.mgr, "_disable_all_clickthrough") as disable, \
             mock.patch.object(self.mgr.root, "attributes") as attrs, \
             mock.patch.object(self.mgr.root, "lift") as lift:
            self.mgr._recover_clickthrough_from_hotkey()
        disable.assert_called_once()
        attrs.assert_called_once_with("-topmost", True)
        lift.assert_called_once()


class TestFontFamily(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = {
            "default_bg": labels.DEFAULT_BG,
            "default_fg": labels.DEFAULT_FG,
            "font_family": labels.DEFAULT_FONT_FAMILY,
            "font_size": labels.DEFAULT_FONT_SIZE,
            "default_transparent": False,
            "last_session": [],
            "presets": {},
        }
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def test_font_family_defaults_to_consolas(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.assertEqual(lbl.font_family, self.labels.DEFAULT_FONT_FAMILY)
        snap = lbl.snapshot()
        self.assertEqual(snap["font_family"], self.labels.DEFAULT_FONT_FAMILY)
        lbl.win.destroy()

    def test_apply_font_family_updates_snapshot(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_font_family("Arial")
        self.assertEqual(lbl.font_family, "Arial")
        snap = lbl.snapshot()
        self.assertEqual(snap["font_family"], "Arial")
        lbl.win.destroy()

    def test_font_family_round_trips_through_spawn(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_font_family("Arial")
        data = lbl.snapshot()
        lbl.win.destroy()

        self.mgr._spawn_from_data(data)
        restored = self.mgr.labels[-1]
        self.assertEqual(restored.font_family, "Arial")
        self.assertEqual(restored.snapshot()["font_family"], "Arial")
        restored.win.destroy()

    def test_spawn_uses_default_font_family_for_new_notes(self):
        self.mgr.config["font_family"] = "Arial"
        self.mgr.spawn_label(text="hi", x=0, y=0)
        lbl = self.mgr.labels[-1]
        self.assertEqual(lbl.font_family, "Arial")
        lbl.win.destroy()

    def test_duplicate_carries_font_family(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_font_family("Arial")
        self.mgr.labels.append(lbl)
        lbl._duplicate()
        duplicate = self.mgr.labels[-1]
        self.assertEqual(duplicate.font_family, "Arial")
        lbl.win.destroy()
        duplicate.win.destroy()

    def test_stash_restore_carries_font_family(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_font_family("Arial")
        self.mgr.labels.append(lbl)
        with mock.patch("labels.save_config"):
            lbl._stash()
            self.mgr._restore_stash(0)
        restored = self.mgr.labels[-1]
        self.assertEqual(restored.font_family, "Arial")
        restored.win.destroy()

    def test_preset_load_carries_font_family(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_font_family("Arial")
        self.mgr.labels.append(lbl)
        with mock.patch("labels.simpledialog.askstring", return_value="font-test"), \
             mock.patch("labels.save_config"):
            self.mgr._save_preset()
            self.mgr._load_preset("font-test")
        restored = self.mgr.labels[-1]
        self.assertEqual(restored.font_family, "Arial")
        restored.win.destroy()


class TestMinimizedGroups(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = {
            "default_bg": labels.DEFAULT_BG,
            "default_fg": labels.DEFAULT_FG,
            "font_family": labels.DEFAULT_FONT_FAMILY,
            "font_size": labels.DEFAULT_FONT_SIZE,
            "default_transparent": False,
            "clickthrough_warned": False,
            "hub_always_on_top": True,
            "global_recovery_hotkey": True,
            "last_session": [{"text": "old"}],
            "presets": {},
            "minimized_groups": {},
        }
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def tearDown(self):
        for lbl in self.mgr.labels[:]:
            if lbl.win.winfo_exists():
                lbl.win.destroy()
        self.mgr.labels = []

    def _add_label(self, text="hi"):
        lbl = self.labels.StickyLabel(self.mgr, text=text, x=0, y=0)
        self.mgr.labels.append(lbl)
        return lbl

    def test_save_minimized_group_stores_snapshots_and_closes_notes(self):
        import unittest.mock as mock
        self._add_label("one")
        self._add_label("two")

        with mock.patch("labels.simpledialog.askstring", return_value="work"), \
             mock.patch.object(self.mgr, "_today_label", return_value="2026-05-21"), \
             mock.patch("labels.save_config") as save_config:
            self.mgr._save_minimized_group()

        group = self.mgr.config["minimized_groups"]["work"]
        self.assertEqual(group["saved_on"], "2026-05-21")
        self.assertEqual([d["text"] for d in group["labels"]], ["one", "two"])
        self.assertEqual(self.mgr.labels, [])
        self.assertEqual(self.mgr.config["last_session"], [])
        self.assertEqual(save_config.call_count, 2)

    def test_save_minimized_group_cancel_and_blank_are_noops(self):
        import unittest.mock as mock
        lbl = self._add_label("keep")

        with mock.patch("labels.simpledialog.askstring", return_value=None), \
             mock.patch("labels.save_config") as save_config:
            self.mgr._save_minimized_group()
        self.assertEqual(self.mgr.labels, [lbl])
        self.assertEqual(self.mgr.config["minimized_groups"], {})
        save_config.assert_not_called()

        with mock.patch("labels.simpledialog.askstring", return_value="  "), \
             mock.patch("labels.save_config") as save_config:
            self.mgr._save_minimized_group()
        self.assertEqual(self.mgr.labels, [lbl])
        self.assertEqual(self.mgr.config["minimized_groups"], {})
        save_config.assert_not_called()

    def test_save_minimized_group_with_no_notes_shows_info(self):
        import unittest.mock as mock
        with mock.patch("labels.messagebox.showinfo") as showinfo, \
             mock.patch("labels.simpledialog.askstring") as askstring, \
             mock.patch("labels.save_config") as save_config:
            self.mgr._save_minimized_group()
        showinfo.assert_called_once()
        askstring.assert_not_called()
        save_config.assert_not_called()

    def test_save_minimized_group_overwrite_decline_is_noop(self):
        import unittest.mock as mock
        lbl = self._add_label("new")
        self.mgr.config["minimized_groups"]["work"] = {
            "saved_on": "2026-05-20",
            "labels": [{"text": "old"}],
        }

        with mock.patch("labels.simpledialog.askstring", return_value="work"), \
             mock.patch("labels.messagebox.askyesno", return_value=False), \
             mock.patch("labels.save_config") as save_config:
            self.mgr._save_minimized_group()

        self.assertEqual(self.mgr.labels, [lbl])
        self.assertEqual(self.mgr.config["minimized_groups"]["work"]["labels"], [{"text": "old"}])
        save_config.assert_not_called()

    def test_save_minimized_group_save_failure_does_not_close_notes(self):
        import unittest.mock as mock
        lbl = self._add_label("keep")

        with mock.patch("labels.simpledialog.askstring", return_value="work"), \
             mock.patch("labels.save_config", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.mgr._save_minimized_group()

        self.assertEqual(self.mgr.labels, [lbl])
        self.assertEqual(self.mgr.config["last_session"], [{"text": "old"}])
        self.assertEqual(self.mgr.config["minimized_groups"], {})

    def test_save_minimized_group_overwrite_accept_replaces_only_that_group(self):
        import unittest.mock as mock
        self._add_label("new")
        self.mgr.config["minimized_groups"] = {
            "work": {"saved_on": "2026-05-20", "labels": [{"text": "old"}]},
            "other": {"saved_on": "2026-05-19", "labels": [{"text": "other"}]},
        }

        with mock.patch("labels.simpledialog.askstring", return_value="work"), \
             mock.patch("labels.messagebox.askyesno", return_value=True), \
             mock.patch.object(self.mgr, "_today_label", return_value="2026-05-21"), \
             mock.patch("labels.save_config"):
            self.mgr._save_minimized_group()

        self.assertEqual(self.mgr.config["minimized_groups"]["work"]["saved_on"], "2026-05-21")
        self.assertEqual(self.mgr.config["minimized_groups"]["work"]["labels"][0]["text"], "new")
        self.assertEqual(self.mgr.config["minimized_groups"]["other"]["labels"], [{"text": "other"}])

    def test_save_single_note_as_minimized_group_saves_and_closes_note(self):
        import unittest.mock as mock
        lbl = self._add_label("single")

        with mock.patch("labels.simpledialog.askstring", return_value="single-note"), \
             mock.patch.object(self.mgr, "_today_label", return_value="2026-05-21"), \
             mock.patch("labels.save_config") as save_config:
            lbl._save_as_minimized_group()

        group = self.mgr.config["minimized_groups"]["single-note"]
        self.assertEqual(group["saved_on"], "2026-05-21")
        self.assertEqual([d["text"] for d in group["labels"]], ["single"])
        self.assertEqual(self.mgr.labels, [])
        self.assertEqual(self.mgr.config["last_session"], [])
        self.assertEqual(save_config.call_count, 2)

    def test_save_single_note_cancel_is_noop(self):
        import unittest.mock as mock
        lbl = self._add_label("single")

        with mock.patch("labels.simpledialog.askstring", return_value=None), \
             mock.patch("labels.save_config") as save_config:
            lbl._save_as_minimized_group()

        self.assertEqual(self.mgr.labels, [lbl])
        self.assertEqual(self.mgr.config["minimized_groups"], {})
        save_config.assert_not_called()

    def test_auto_minimize_single_note_uses_first_non_empty_line_without_prompt(self):
        import unittest.mock as mock
        lbl = self._add_label("\n   First real note title with extra words\nbody")

        with mock.patch("labels.simpledialog.askstring") as askstring, \
             mock.patch.object(self.mgr, "_today_label", return_value="2026-05-21"), \
             mock.patch("labels.save_config") as save_config:
            self.mgr._auto_minimize_single_label(lbl)

        askstring.assert_not_called()
        self.assertIn("First real note title with extra", self.mgr.config["minimized_groups"])
        group = self.mgr.config["minimized_groups"]["First real note title with extra"]
        self.assertEqual(group["saved_on"], "2026-05-21")
        self.assertEqual(group["labels"][0]["text"], "\n   First real note title with extra words\nbody")
        self.assertEqual(self.mgr.labels, [])
        self.assertEqual(self.mgr.config["last_session"], [])
        self.assertEqual(save_config.call_count, 2)

    def test_auto_minimize_single_note_adds_case_insensitive_suffix(self):
        import unittest.mock as mock
        lbl = self._add_label("meeting notes")
        self.mgr.config["minimized_groups"] = {
            "Meeting Notes": {"saved_on": "2026-05-20", "labels": [{"text": "old"}]},
        }

        with mock.patch("labels.simpledialog.askstring") as askstring, \
             mock.patch("labels.save_config"):
            self.mgr._auto_minimize_single_label(lbl)

        askstring.assert_not_called()
        self.assertIn("Meeting Notes", self.mgr.config["minimized_groups"])
        self.assertIn("meeting notes 2", self.mgr.config["minimized_groups"])
        self.assertEqual(self.mgr.config["minimized_groups"]["Meeting Notes"]["labels"], [{"text": "old"}])

    def test_auto_minimize_single_note_fallback_names(self):
        text_name = self.mgr._auto_minimized_name({"text": "   \n", "images": []})
        image_name = self.mgr._auto_minimized_name({"text": "", "images": [{"path": "pasted-images/x.png"}]})

        self.assertEqual(text_name, "Untitled note")
        self.assertEqual(image_name, "Image note")

    def test_restore_minimized_group_appends_and_keeps_group_saved(self):
        import unittest.mock as mock
        existing = self._add_label("existing")
        self.mgr.config["minimized_groups"]["work"] = {
            "saved_on": "2026-05-21",
            "labels": [{"text": "restored", "x": 0, "y": 0}],
        }

        with mock.patch("labels.save_config") as save_config:
            self.mgr._restore_minimized_group("work")

        self.assertEqual(self.mgr.labels[0], existing)
        self.assertEqual(len(self.mgr.labels), 2)
        self.assertEqual(self.mgr.labels[-1].snapshot()["text"], "restored")
        self.assertIn("work", self.mgr.config["minimized_groups"])
        self.assertEqual(len(self.mgr.config["last_session"]), 2)
        save_config.assert_called_once_with(self.mgr.config)

    def test_delete_minimized_group_removes_only_selected_group(self):
        import unittest.mock as mock
        self.mgr.config["minimized_groups"] = {
            "work": {"saved_on": "2026-05-21", "labels": []},
            "other": {"saved_on": "2026-05-20", "labels": []},
        }

        with mock.patch("labels.messagebox.askyesno", return_value=True), \
             mock.patch("labels.save_config") as save_config:
            self.mgr._delete_minimized_group("work")

        self.assertNotIn("work", self.mgr.config["minimized_groups"])
        self.assertIn("other", self.mgr.config["minimized_groups"])
        save_config.assert_called_once_with(self.mgr.config)

    def test_delete_minimized_group_decline_is_noop(self):
        import unittest.mock as mock
        self.mgr.config["minimized_groups"] = {
            "work": {"saved_on": "2026-05-21", "labels": []},
        }

        with mock.patch("labels.messagebox.askyesno", return_value=False), \
             mock.patch("labels.save_config") as save_config:
            self.mgr._delete_minimized_group("work")

        self.assertIn("work", self.mgr.config["minimized_groups"])
        save_config.assert_not_called()

    def test_minimized_group_preserves_image_records_for_restore(self):
        import unittest.mock as mock
        image_record = {
            "path": "pasted-images/x.png",
            "original_path": "pasted-images/x.png",
            "width": 100,
            "height": 80,
            "position": "1.0",
        }
        lbl = self._add_label("image")
        lbl._images = [image_record]

        with mock.patch("labels.simpledialog.askstring", return_value="images"), \
             mock.patch("labels.save_config"):
            self.mgr._save_minimized_group()

        saved = self.mgr.config["minimized_groups"]["images"]["labels"][0]
        self.assertEqual(saved["images"], [image_record])

        with mock.patch.object(self.mgr, "_spawn_from_data") as spawn_from_data, \
             mock.patch("labels.save_config"):
            self.mgr._restore_minimized_group("images")
        spawn_from_data.assert_called_once_with(saved)

    def test_saved_notes_items_lists_minimized_stash_and_presets(self):
        self.mgr.config["minimized_groups"] = {
            "work": {"saved_on": "2026-05-21", "labels": [{"text": "a"}, {"text": "b"}]},
        }
        self.mgr.config["stash"] = [
            {"text": "stashed note\nbody", "stashed_on": "5/20"},
        ]
        self.mgr.config["presets"] = {
            "layout": [{"text": "preset"}],
        }

        labels = [item["label"] for item in self.mgr._saved_notes_items()]

        self.assertIn("[Minimized] work | 2 notes | 5/21", labels)
        self.assertIn("[Stash] stashed note | 1 note | 5/20", labels)
        self.assertIn("[Preset] layout | 1 note", labels)

    def test_saved_notes_items_include_search_preview_and_recent_sort(self):
        self.mgr.config["minimized_groups"] = {
            "older": {"saved_on": "2026-05-20", "labels": [{"text": "old task\nbody"}]},
            "newer": {"saved_on": "2026-05-21", "labels": [{"text": "new task\nbody"}]},
        }
        self.mgr.config["stash"] = [
            {"text": "stashed title\nstashed body", "stashed_on": "2026-05-22"},
        ]
        self.mgr.config["presets"] = {
            "layout": [{"text": "preset body"}],
        }

        items = self.mgr._saved_notes_items()

        self.assertEqual(items[0]["title"], "stashed title")
        self.assertEqual(items[1]["title"], "newer")
        newer = next(item for item in items if item["title"] == "newer")
        self.assertEqual(newer["kind_label"], "Minimized")
        self.assertEqual(newer["preview"], "new task")
        self.assertIn("new task", newer["search"])
        preset = next(item for item in items if item["title"] == "layout")
        self.assertEqual(preset["kind_label"], "Preset")
        self.assertEqual(preset["preview"], "preset body")

    def test_delete_stash_item_removes_one_saved_note(self):
        import unittest.mock as mock
        self.mgr.config["stash"] = [
            {"text": "first", "stashed_on": "5/20"},
            {"text": "second", "stashed_on": "5/21"},
        ]

        with mock.patch("labels.save_config") as save_config:
            self.mgr._delete_stash_item(0)

        self.assertEqual([item["text"] for item in self.mgr.config["stash"]], ["second"])
        save_config.assert_called_once_with(self.mgr.config)

    def test_settings_menu_includes_saved_notes_entry(self):
        import inspect
        source = inspect.getsource(self.labels.LabelManager._show_settings_menu)
        self.assertIn("Saved notes...", source)


class TestEditModeContextMenu(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def test_edit_mode_has_right_click_menu_binding(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._start_edit(type("E", (), {"x": 0, "y": 0, "x_root": 0, "y_root": 0})())
        self.assertTrue(lbl._entry.bind("<Button-3>"))
        lbl.win.destroy()

    def test_entry_select_all_selects_text(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hello", x=0, y=0)
        lbl._start_edit(type("E", (), {"x": 0, "y": 0, "x_root": 0, "y_root": 0})())
        lbl._entry_select_all()
        selected = lbl._entry.get("sel.first", "sel.last")
        self.assertEqual(selected, "hello")
        lbl.win.destroy()


class TestImageGripResize(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)
        labels._ensure_image_dir()

    def _paste_image(self, lbl, w=100, h=60):
        try:
            from PIL import Image as PilImage
        except ImportError:
            self.skipTest("Pillow not installed")
        import unittest.mock as mock
        evt = type('E', (), {'x':0,'y':0,'x_root':0,'y_root':0})()
        lbl._start_edit(evt)
        lbl.win.update_idletasks()
        fake = PilImage.new("RGB", (w, h), color=(255, 0, 0))
        with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake):
            lbl._paste_image(None)
        lbl._finish_edit(None)
        lbl.win.update_idletasks()

    def test_image_embedded_as_window(self):
        lbl = self.labels.StickyLabel(self.mgr, text="test", x=0, y=0)
        self._paste_image(lbl)
        windows = list(lbl.label.dump("1.0", "end", window=True))
        self.assertTrue(len(windows) >= 1, "Expected window_create embed")
        lbl.win.destroy()

    def test_image_frame_has_grip(self):
        lbl = self.labels.StickyLabel(self.mgr, text="test", x=0, y=0)
        self._paste_image(lbl)
        self.assertTrue(len(lbl._image_frames) >= 1)
        frame = lbl._image_frames[0]
        children = frame.winfo_children()
        self.assertEqual(len(children), 2)  # image label + grip
        lbl.win.destroy()

    def test_image_survives_edit_roundtrip_with_windows(self):
        lbl = self.labels.StickyLabel(self.mgr, text="test", x=0, y=0)
        self._paste_image(lbl)
        count_before = len(lbl._images)
        evt = type('E', (), {'x':0,'y':0,'x_root':0,'y_root':0})()
        lbl._start_edit(evt)
        lbl.win.update_idletasks()
        lbl._finish_edit(None)
        lbl.win.update_idletasks()
        self.assertEqual(len(lbl._images), count_before)
        lbl.win.destroy()

    def tearDown(self):
        import glob
        for f in glob.glob(os.path.join(self.labels.IMAGE_DIR, "*.png")):
            os.remove(f)


class TestChecklist(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def test_checked_items_get_tag(self):
        lbl = self.labels.StickyLabel(self.mgr, text="- [x] done\n- [ ] todo", x=0, y=0)
        lbl.win.update_idletasks()
        ranges = lbl.label.tag_ranges("checked")
        self.assertTrue(len(ranges) > 0, "Expected 'checked' tag on completed item")
        lbl.win.destroy()

    def test_toggle_unchecked_to_checked(self):
        lbl = self.labels.StickyLabel(self.mgr, text="- [ ] task", x=0, y=0)
        lbl.win.update_idletasks()
        lbl._toggle_checklist_item("1.0")
        text = lbl.label.get("1.0", "end-1c")
        self.assertIn("- [x]", text)
        lbl.win.destroy()

    def test_toggle_checked_to_unchecked(self):
        lbl = self.labels.StickyLabel(self.mgr, text="- [x] done", x=0, y=0)
        lbl.win.update_idletasks()
        lbl._toggle_checklist_item("1.0")
        text = lbl.label.get("1.0", "end-1c")
        self.assertIn("- [ ]", text)
        lbl.win.destroy()

    def test_checked_items_sort_to_bottom(self):
        lbl = self.labels.StickyLabel(
            self.mgr,
            text="- [ ] alpha\n- [ ] beta\n- [ ] gamma",
            x=0, y=0
        )
        lbl.win.update_idletasks()
        # Check the first item
        lbl._toggle_checklist_item("1.0")
        text = lbl.label.get("1.0", "end-1c")
        lines = text.strip().split("\n")
        # "alpha" should now be checked and at the bottom
        self.assertTrue(lines[-1].startswith("- [x]"), f"Last line should be checked, got: {lines[-1]}")
        self.assertIn("alpha", lines[-1])
        lbl.win.destroy()


if __name__ == "__main__":
    unittest.main()
