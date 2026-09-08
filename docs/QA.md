# Note safety regression coverage

Run `python -m pytest -q` and `python tests/stress_test.py`.
Test bootstrap uses unique owned temporary storage per process before importing
the app. Legacy cases reset their shared settings before each test; new
regressions use per-case subdirectories. Run the stress command separately.
Never substitute a live notes directory for a test fixture.

| Known failure | Prevention / regression |
|---|---|
| QA-01: tests deleted the live image folder | `_test_support.py`, guarded recursive cleanup, `test_storage_and_recursive_cleanup_are_confined` |
| QA-02: interrupted JSON writes corrupted notes | Atomic replacement, validated backup recovery; `test_note_storage.py` failure-injection cases |
| QA-03: minimizing active edits saved stale content | Pure live snapshot; `test_live_minimize_preserves_text_images_and_writes_once`, quit integration smoke |
| QA-04: preset restore destroyed open notes | Additive restore; `test_preset_restore_is_additive_and_durable` |
| QA-05: restore/close consumed the last stash copy | Reusable stash sources; `test_restored_stash_keeps_reusable_source_after_close` |
| QA-06: search retained stale placeholder rows | Enable-before-clear; `test_search_recovers_and_finds_all_group_bodies` |
| QA-07: read-only text accepted ordinary keys | Tcl write guard; `test_readonly_tcl_mutations_and_real_keys_are_blocked` |
| QA-08: deleting all text restored old content | Empty/whitespace commits; `test_commit_preserves_exact_text` |
| QA-09: clipboard payloads truncated at 4096 bytes | Bounded EOF framing; fragmentation, Unicode, timeout, overflow and helper-port tests in `test_note_ipc.py` |
| QA-10: duplicate dropped appearance and aliased images | Snapshot duplication with separate records/PhotoImages; `test_duplicate_preserves_all_properties_and_owns_images` |

Additional checks cover failed-transfer rollback, loss of a reusable source,
autosave failure/retry, undo stack purity, kernel lock recovery after process
death, and legacy app detection on an occupied port. Save transactions put the
complete group/session state in one JSON document before closing any windows.
Deleting a saved source does not delete shared image files.

Test changes replace old two-save call counts with one complete write while
retaining the saved-content and post-close session assertions. Clean-note tests
now establish a real reusable saved source before asserting no prompt.

The stress script constructs menus but mocks native popup presentation, and
uses synthetic image clipboard values. It does not certify native menu,
screen-reader, mixed-DPI, multi-monitor, global-hotkey conflict, or packaged
Windows Jump List behavior. Those remain manual release checks.


Native QA found an additional event-loop regression: a Python Tcl-command
proxy let a caught `bad text index "tk::anchor1"` error escape `mainloop()`.
The write guard now runs inside Tcl, preserving normal caught-error behavior.
`tests/test_native_text.py` compares caught errors with stock Tk Text, verifies
the next event-loop tick, direct-error fidelity, per-widget toggles, internal
text/image updates and repeated parent/double-destroy cleanup.

Native Windows inspection also found that Tk note text is exposed as generic
panes and hub controls as unnamed images in UI Automation. Screen-reader
accessibility remains an observed limitation, not a passed check. A temporary
QA harness adds OS frames because the desktop automation tool does not list
the product's borderless windows; its results do not certify borderless shell
discovery or every mixed-DPI setup. Native menus, typing, undo/redo, autosave,
duplicate, and the actual hotkey-conflict warning were exercised with synthetic
notes. Jump List COM publication used a separate QA app identity.
