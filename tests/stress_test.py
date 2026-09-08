"""Stress test: simulates real user flows to find bugs."""
import tkinter as tk
import contextlib
import sys, os, traceback
from unittest import mock
from _test_support import assert_test_storage

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def main():
    results = []
    def log(test, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        results.append((test, passed, detail))
        print(f"  [{status}] {test}" + (f" -- {detail}" if detail else ""))

    def safe(fn, name):
        try:
            fn()
            return True
        except Exception as e:
            log(name, False, f"CRASH: {e}")
            traceback.print_exc()
            return False

    class FakeEvent:
        def __init__(self, x=5, y=5, x_root=100, y_root=100, widget=None):
            self.widget = widget
            self.x = x
            self.y = y
            self.x_root = x_root
            self.y_root = y_root

    print("=== STRESS TEST: Real User Flows ===\n")

    import labels
    assert_test_storage()
    try:
        from PIL import Image as PilImage, ImageTk, ImageGrab
        HAS_PIL = True
    except ImportError:
        HAS_PIL = False
        print("WARNING: Pillow not installed, skipping image tests")

    with mock.patch.object(labels.LabelManager, "_start_socket_listener"), \
         mock.patch.object(labels.LabelManager, "_start_global_recovery_hotkey"):
        mgr = labels.LabelManager()
    popup_patch = mock.patch.object(tk.Menu, "tk_popup")
    try:
        popup_patch.start()  # Build menus without a native modal menu interaction.
        mgr.root.update_idletasks()

        # ============================================
        # FLOW 1: Create note, resize via grip, edit, check size preserved
        # ============================================
        print("[Flow 1: Resize persistence through edit]")
        mgr.spawn_label(text="resize me")
        lbl = mgr.labels[-1]
        mgr.root.update_idletasks()

        lbl._start_resize(FakeEvent(x_root=0, y_root=0))
        lbl._on_resize(FakeEvent(x_root=200, y_root=150))
        mgr.root.update_idletasks()
        w_after_resize = lbl.win.winfo_width()
        h_after_resize = lbl.win.winfo_height()
        log(f"Resized to {w_after_resize}x{h_after_resize}", w_after_resize > 250)

        lbl._start_edit(FakeEvent())
        mgr.root.update_idletasks()
        lbl._entry.delete("1.0", "end")
        lbl._entry.insert("1.0", "resized and edited")
        lbl._finish_edit(None)
        mgr.root.update_idletasks()
        w_after_edit = lbl.win.winfo_width()
        h_after_edit = lbl.win.winfo_height()
        log(f"Size preserved after edit: {w_after_edit}x{h_after_edit}",
            w_after_edit == w_after_resize,
            f"was {w_after_resize}, now {w_after_edit}")

        ok = safe(lambda: lbl._show_menu(FakeEvent(widget=lbl.label)), "Right-click after resize+edit")
        if ok:
            log("Right-click after resize+edit", True)

        # ============================================
        # FLOW 2: Create, paste image, finish, right-click
        # ============================================
        print("\n[Flow 2: Paste image then right-click]")
        if HAS_PIL:
            mgr.spawn_label(text="img note")
            lbl2 = mgr.labels[-1]
            mgr.root.update_idletasks()

            lbl2._start_edit(FakeEvent())
            mgr.root.update_idletasks()
            fake_img = PilImage.new("RGB", (100, 60), color=(255, 0, 0))
            with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake_img):
                lbl2._paste_image(None)
            mgr.root.update_idletasks()
            log("Image pasted in edit mode", len(lbl2._entry_photo_refs) >= 1)

            lbl2._finish_edit(None)
            mgr.root.update_idletasks()
            log("Finish edit with image", len(lbl2._images) >= 1)

            ok = safe(lambda: lbl2._show_menu(FakeEvent(widget=lbl2.label, x=5, y=5)), "Right-click after image paste")
            if ok:
                log("Right-click after image paste", True)

            ok = safe(lambda: lbl2._show_menu(FakeEvent(widget=lbl2.label, x=50, y=15)), "Right-click on image area")
            if ok:
                log("Right-click on image area", True)

        # ============================================
        # FLOW 3: Multiple edits in a row
        # ============================================
        print("\n[Flow 3: Multiple edits in a row]")
        mgr.spawn_label(text="multi edit")
        lbl3 = mgr.labels[-1]
        mgr.root.update_idletasks()

        for i in range(5):
            lbl3._start_edit(FakeEvent())
            mgr.root.update_idletasks()
            lbl3._entry.delete("1.0", "end")
            lbl3._entry.insert("1.0", f"edit #{i+1}")
            lbl3._finish_edit(None)
            mgr.root.update_idletasks()

        text = lbl3.label.get("1.0", "end-1c")
        log("5 edits in a row", text == "edit #5", f"got '{text}'")

        ok = safe(lambda: lbl3._show_menu(FakeEvent(widget=lbl3.label)), "Right-click after 5 edits")
        if ok:
            log("Right-click after 5 edits", True)

        # ============================================
        # FLOW 4: Paste image, edit again, paste another, finish
        # ============================================
        print("\n[Flow 4: Multiple images across edits]")
        if HAS_PIL:
            mgr.spawn_label(text="multi img")
            lbl4 = mgr.labels[-1]
            mgr.root.update_idletasks()

            lbl4._start_edit(FakeEvent())
            fake1 = PilImage.new("RGB", (80, 40), color=(0, 255, 0))
            with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake1):
                lbl4._paste_image(None)
            lbl4._finish_edit(None)
            mgr.root.update_idletasks()
            count1 = len(lbl4._images)
            log(f"First image pasted ({count1})", count1 == 1)

            lbl4._start_edit(FakeEvent())
            mgr.root.update_idletasks()
            log("Re-edit loads existing images", len(lbl4._entry_photo_refs) >= 1)

            fake2 = PilImage.new("RGB", (60, 30), color=(0, 0, 255))
            with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake2):
                lbl4._paste_image(None)
            lbl4._finish_edit(None)
            mgr.root.update_idletasks()
            count2 = len(lbl4._images)
            log(f"Second image added ({count2})", count2 == 2)

            ok = safe(lambda: lbl4._show_menu(FakeEvent(widget=lbl4.label)), "Right-click after 2 images")
            if ok:
                log("Right-click after 2 images", True)

        # ============================================
        # FLOW 5: Paste image, cancel, check state
        # ============================================
        print("\n[Flow 5: Paste then cancel]")
        if HAS_PIL:
            mgr.spawn_label(text="cancel test")
            lbl5 = mgr.labels[-1]
            mgr.root.update_idletasks()

            lbl5._start_edit(FakeEvent())
            fake3 = PilImage.new("RGB", (70, 35), color=(128, 128, 0))
            with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake3):
                lbl5._paste_image(None)
            lbl5._cancel_edit(None)
            mgr.root.update_idletasks()
            log("Cancel after paste: no images kept", len(lbl5._images) == 0)
            log("Cancel: text unchanged", lbl5.label.get("1.0", "end-1c") == "cancel test")

            ok = safe(lambda: lbl5._show_menu(FakeEvent(widget=lbl5.label)), "Right-click after cancel")
            if ok:
                log("Right-click after cancel", True)

        # ============================================
        # FLOW 6: Delete image via _delete_image
        # ============================================
        print("\n[Flow 6: Delete image]")
        if HAS_PIL:
            mgr.spawn_label(text="delete me")
            lbl6 = mgr.labels[-1]
            mgr.root.update_idletasks()

            lbl6._start_edit(FakeEvent())
            fake4 = PilImage.new("RGB", (90, 45), color=(255, 128, 0))
            with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake4):
                lbl6._paste_image(None)
            lbl6._finish_edit(None)
            mgr.root.update_idletasks()
            log("Image present before delete", len(lbl6._images) == 1)

            found_idx = None
            for item_type, value, idx in lbl6.label.dump("1.0", "end", window=True):
                if item_type == "window":
                    found_idx = idx
                    break
            if not found_idx:
                for item_type, value, idx in lbl6.label.dump("1.0", "end", image=True):
                    if item_type == "image":
                        found_idx = idx
                        break

            if found_idx:
                ok = safe(lambda: lbl6._delete_image(found_idx), "Delete image")
                if ok:
                    mgr.root.update_idletasks()
                    log("Image deleted from _images", len(lbl6._images) == 0, f"remaining: {len(lbl6._images)}")
                    log("Photo refs cleaned", len(lbl6._photo_refs) == 0, f"remaining: {len(lbl6._photo_refs)}")
            else:
                log("Could not find image to delete", False, "no image in dump")

            ok = safe(lambda: lbl6._show_menu(FakeEvent(widget=lbl6.label)), "Right-click after delete")
            if ok:
                log("Right-click after delete", True)

            # Edit after delete
            ok = safe(lambda: (lbl6._start_edit(FakeEvent()), lbl6._finish_edit(None)), "Edit after delete")
            if ok:
                mgr.root.update_idletasks()
                log("Edit after delete works", True)

        # ============================================
        # FLOW 7: Resize image
        # ============================================
        print("\n[Flow 7: Resize image]")
        if HAS_PIL:
            mgr.spawn_label(text="resize img")
            lbl7 = mgr.labels[-1]
            mgr.root.update_idletasks()

            lbl7._start_edit(FakeEvent())
            fake5 = PilImage.new("RGB", (120, 80), color=(0, 200, 200))
            with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake5):
                lbl7._paste_image(None)
            lbl7._finish_edit(None)
            mgr.root.update_idletasks()

            orig_w = lbl7._images[0]["width"]

            def do_resize():
                if lbl7._image_frames:
                    frame = lbl7._image_frames[0]
                    # Simulate grip drag: start, drag to shrink by 60px, release
                    lbl7._img_grip_start(FakeEvent(x_root=200), frame)
                    lbl7._img_grip_drag(FakeEvent(x_root=140), frame)  # -60px = new width ~60
                    lbl7._img_grip_end(FakeEvent(x_root=140), frame)
                    mgr.root.update_idletasks()
                else:
                    # Fallback to dialog method if no frames
                    with mock.patch("labels.simpledialog.askinteger", return_value=60):
                        lbl7._resize_image_by_entry(lbl7._images[0])
                    mgr.root.update_idletasks()

            ok = safe(do_resize, "Resize image")
            if ok:
                new_w = lbl7._images[0]["width"]
                log("Width changed", new_w != orig_w, f"was {orig_w}, now {new_w}")
                log("Height scaled", lbl7._images[0]["height"] != 80, f"got {lbl7._images[0]['height']}")
                log("Path updated", f"{new_w}x" in lbl7._images[0]["path"])

            # Edit after resize
            lbl7._start_edit(FakeEvent())
            mgr.root.update_idletasks()
            log("Edit after resize loads entry", lbl7._entry is not None)
            lbl7._finish_edit(None)
            mgr.root.update_idletasks()
            log("Finish after resize preserves images", len(lbl7._images) >= 1)

            ok = safe(lambda: lbl7._show_menu(FakeEvent(widget=lbl7.label)), "Right-click after resize+edit")
            if ok:
                log("Right-click after resize+edit", True)

        # ============================================
        # FLOW 8: Duplicate with image then edit duplicate
        # ============================================
        print("\n[Flow 8: Duplicate with image then edit]")
        if HAS_PIL:
            mgr.spawn_label(text="dup source")
            lbl8 = mgr.labels[-1]
            mgr.root.update_idletasks()

            lbl8._start_edit(FakeEvent())
            fake6 = PilImage.new("RGB", (50, 25), color=(200, 0, 200))
            with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake6):
                lbl8._paste_image(None)
            lbl8._finish_edit(None)
            mgr.root.update_idletasks()

            count_before = len(mgr.labels)
            lbl8._duplicate()
            mgr.root.update_idletasks()
            log("Duplicate created", len(mgr.labels) == count_before + 1)

            dup = mgr.labels[-1]
            log("Dup has images", len(dup._images) >= 1)

            dup._start_edit(FakeEvent())
            mgr.root.update_idletasks()
            log("Edit dup loads images", len(dup._entry_photo_refs) >= 1)
            dup._finish_edit(None)
            mgr.root.update_idletasks()
            log("Finish edit on dup preserves images", len(dup._images) >= 1)

        # ============================================
        # FLOW 9: Full persist round-trip
        # ============================================
        print("\n[Flow 9: Full persist round-trip]")
        if HAS_PIL:
            snap = lbl8.snapshot()
            log("Snapshot has images", len(snap.get("images", [])) >= 1)

            mgr._spawn_from_data(snap)
            mgr.root.update_idletasks()
            restored = mgr.labels[-1]
            log("Restored has images", len(restored._images) >= 1)
            log("Restored has photo refs", len(restored._photo_refs) >= 1)

            restored._start_edit(FakeEvent())
            mgr.root.update_idletasks()
            log("Edit restored note works", restored._entry is not None)
            restored._finish_edit(None)
            mgr.root.update_idletasks()
            log("Finish edit on restored preserves images", len(restored._images) >= 1)

        # ============================================
        # FLOW 10: Rapid create/edit/close cycle
        # ============================================
        print("\n[Flow 10: Rapid create/edit/close cycle]")
        for i in range(10):
            mgr.spawn_label(text=f"rapid {i}")
            rapid = mgr.labels[-1]
            mgr.root.update_idletasks()
            rapid._start_edit(FakeEvent())
            mgr.root.update_idletasks()
            rapid._finish_edit(None)
            mgr.root.update_idletasks()
            rapid._close()
            mgr.root.update_idletasks()
        log("10 rapid create/edit/close cycles", True)

    finally:
        popup_patch.stop()
        mgr._autosave_enabled = False
        with contextlib.suppress(tk.TclError):
            for pending in mgr.root.tk.call("after", "info"):
                mgr.root.after_cancel(pending)
            mgr.root.destroy()

    # --- Summary ---
    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    print(f"\n{'='*50}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(results)}")
    if failed:
        print("\nFAILURES:")
        for name, p, detail in results:
            if not p:
                print(f"  FAIL: {name} -- {detail}")
    print(f"{'='*50}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
