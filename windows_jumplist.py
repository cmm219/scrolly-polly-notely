import os
import sys
import subprocess


APP_AUMID = "ScrollyPollyNotely.App"
JUMP_LIST_CATEGORY = "Saved notes"


def is_windows():
    return os.name == "nt"


def set_app_user_model_id(app_id=APP_AUMID):
    if not is_windows():
        return False
    try:
        from win32com.shell import shell
        shell.SetCurrentProcessExplicitAppUserModelID(app_id)
        return True
    except Exception:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            return True
        except Exception:
            return False


def get_launch_parts():
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    script = os.path.abspath(sys.argv[0] or __file__)
    return sys.executable, f'"{script}"'


def build_saved_note_entries(config, label_func):
    entries = []
    groups = config.get("minimized_groups", {})
    for name in sorted(groups.keys()):
        entries.append({
            "name": name,
            "title": label_func(name, groups[name]),
        })
    return entries


def _quote_arg(value):
    return subprocess.list2cmdline([str(value)])


def _shell_link(title, target, arguments, working_dir, icon_path=None, app_id=APP_AUMID):
    import pythoncom
    from win32com.shell import shell
    from win32com.propsys import propsys, pscon

    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink,
        None,
        pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_IShellLink,
    )
    link.SetPath(target)
    link.SetArguments(arguments)
    if working_dir:
        link.SetWorkingDirectory(working_dir)
    if icon_path and os.path.exists(icon_path):
        link.SetIconLocation(icon_path, 0)
    link.SetDescription(title)

    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_Title, propsys.PROPVARIANTType(title))
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(app_id))
    store.Commit()
    return link


def publish_saved_notes(config, label_func, icon_path=None, app_id=APP_AUMID):
    if not is_windows():
        return False
    try:
        import pythoncom
        from win32com.shell import shell

        pythoncom.CoInitialize()
        target, base_args = get_launch_parts()
        working_dir = os.path.dirname(target)
        entries = build_saved_note_entries(config, label_func)

        dest = pythoncom.CoCreateInstance(
            shell.CLSID_DestinationList,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_ICustomDestinationList,
        )
        dest.SetAppID(app_id)
        dest.BeginList()

        collection = pythoncom.CoCreateInstance(
            shell.CLSID_EnumerableObjectCollection,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IObjectCollection,
        )
        for entry in entries:
            restore_arg = f"--restore-saved {_quote_arg(entry['name'])}"
            args = f"{base_args} {restore_arg}".strip()
            collection.AddObject(_shell_link(entry["title"], target, args, working_dir, icon_path, app_id))

        array = collection.QueryInterface(shell.IID_IObjectArray)
        if entries:
            dest.AppendCategory(JUMP_LIST_CATEGORY, array)
        dest.CommitList()
        return True
    except Exception as exc:
        print(f"[ScrollyPollyNotely] Jump List update failed: {exc}", file=sys.stderr)
        return False


def create_shortcut(shortcut_path, target_path, working_dir=None, icon_path=None, app_id=APP_AUMID):
    if not is_windows():
        return False
    try:
        import pythoncom
        from win32com.shell import shell
        from win32com.propsys import propsys, pscon

        pythoncom.CoInitialize()
        link = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLink,
        )
        link.SetPath(target_path)
        if working_dir:
            link.SetWorkingDirectory(working_dir)
        if icon_path and os.path.exists(icon_path):
            link.SetIconLocation(icon_path, 0)

        store = link.QueryInterface(propsys.IID_IPropertyStore)
        store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(app_id))
        store.Commit()

        persist = link.QueryInterface(pythoncom.IID_IPersistFile)
        os.makedirs(os.path.dirname(shortcut_path), exist_ok=True)
        persist.Save(shortcut_path, True)
        return True
    except Exception as exc:
        print(f"[ScrollyPollyNotely] Shortcut update failed: {exc}", file=sys.stderr)
        return False
