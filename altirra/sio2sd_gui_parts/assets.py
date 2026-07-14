"""Application asset helpers."""

import ctypes
import os
import sys
import tkinter as tk


APP_USER_MODEL_ID = 'pawelbanas.sio2sd.gui'


def set_windows_app_id():
    if os.name != 'nt':
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID)
    except Exception:
        pass


def asset_path(project_root, bundle_root, name):
    candidates = [
        os.path.join(bundle_root, 'assets', name),
        os.path.join(project_root, 'assets', name),
    ]
    if getattr(sys, 'frozen', False):
        candidates.append(os.path.join(os.path.dirname(sys.executable),
                                       'assets', name))
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return candidates[0]


def apply_window_icon(window, project_root, bundle_root):
    ico_path = asset_path(project_root, bundle_root, 'sio2sd_gui_icon.ico')
    png_path = asset_path(project_root, bundle_root, 'sio2sd_gui_icon.png')

    if os.name == 'nt' and os.path.exists(ico_path):
        try:
            window.iconbitmap(default=ico_path)
        except tk.TclError:
            pass

    if os.path.exists(png_path):
        try:
            photo = tk.PhotoImage(file=png_path)
            window.iconphoto(True, photo)
            window._app_icon_photo = photo
        except tk.TclError:
            pass
