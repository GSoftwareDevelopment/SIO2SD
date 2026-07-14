#!/usr/bin/env python3
"""Prosty graficzny panel sterowania serwerem SIO2SD dla Altirry."""

import os
import queue
import sys
import tkinter as tk

from sio2sd_gui_parts.actions import SIO2SDGuiActionsMixin
from sio2sd_gui_parts.assets import (apply_window_icon,
                                      set_windows_app_id)
from sio2sd_gui_parts.browser import SIO2SDGuiBrowserMixin
from sio2sd_gui_parts.config import SIO2SDGuiConfigMixin
from sio2sd_gui_parts.constants import (ATR_FILESYSTEMS, ATR_FORMATS,
                                        DOT_MATRIX_FONT,
                                        SHOW_EXPERIMENTAL_ATR_CREATOR)
from sio2sd_gui_parts.log import SIO2SDGuiLogMixin
from sio2sd_gui_parts.mini import SIO2SDGuiMiniMixin
from sio2sd_gui_parts.ui import SIO2SDGuiUiMixin


class SIO2SDGui(SIO2SDGuiActionsMixin, SIO2SDGuiBrowserMixin,
                SIO2SDGuiConfigMixin, SIO2SDGuiLogMixin,
                SIO2SDGuiMiniMixin, SIO2SDGuiUiMixin, tk.Tk):
    SHOW_EXPERIMENTAL_ATR_CREATOR = SHOW_EXPERIMENTAL_ATR_CREATOR
    ATR_FORMATS = ATR_FORMATS
    ATR_FILESYSTEMS = ATR_FILESYSTEMS
    DOT_MATRIX_FONT = DOT_MATRIX_FONT

    def __init__(self):
        super().__init__()
        self.title('SIO2SD dla Altirry')
        self.minsize(860, 560)

        if getattr(sys, 'frozen', False):
            self.project_root = os.path.dirname(os.path.abspath(sys.executable))
            self.bundle_root = getattr(sys, '_MEIPASS', self.project_root)
        else:
            self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.bundle_root = self.project_root
        apply_window_icon(self, self.project_root,
                          self.bundle_root)
        self.default_sd = os.path.join(self.project_root, 'sd')
        self.settings_path = os.path.join(self.project_root,
                                          'sio2sd_gui_settings.json')
        self._ensure_runtime_files()
        self.settings = self._load_settings()

        self.runtime = None
        self.log_queue = queue.Queue()
        self.activity_queue = queue.Queue()
        self._log_compact_entries = {}
        self.sio2sd_config = self._load_sio2sd_config()
        self._updating_config_controls = False
        self._syncing_config_bytes = False
        self._apply_config_job = None

        self.sd_dir = tk.StringVar(value=self.settings.get('sd_dir',
                                                           self.default_sd))
        self.card_root = tk.StringVar(value='')
        self.device_id = tk.StringVar(value=str(self.settings.get('device_id',
                                                                  '0')))
        self.port = tk.IntVar(value=int(self.settings.get('port', 9977)))
        self.read_only = tk.BooleanVar(value=bool(self.settings.get('read_only',
                                                                    False)))
        self.cfg_hsindex = tk.IntVar(value=self.sio2sd_config[0])
        self.cfg_turbo_hsindex = tk.IntVar(value=self.sio2sd_config[1])
        self.cfg_atr_write_protect = tk.BooleanVar(
            value=bool(self.sio2sd_config[5] & 1))
        self.cfg_byte_vars = [
            tk.IntVar(value=self.sio2sd_config[idx]) for idx in range(16)
        ]
        self.device_visible = tk.BooleanVar(value=bool(
            self.settings.get('device_visible', True)))
        self.topdrive_turbo = tk.BooleanVar(value=bool(
            self.settings.get('topdrive_turbo', True)))
        self.cfg_raw = tk.StringVar(value='')
        self.cfg_status = tk.StringVar(value='')
        self.verbose = tk.BooleanVar(value=bool(self.settings.get('verbose',
                                                                 True)))
        self.auto_start = tk.BooleanVar(value=bool(self.settings.get('auto_start',
                                                                     False)))
        self.cfg_selector = tk.BooleanVar(value=bool(
            self.settings.get('cfg_selector', False)))
        self.preserve_drive_mapping = tk.BooleanVar(value=bool(
            self.settings.get('preserve_drive_mapping', False)))
        self.status = tk.StringVar(value='Serwer zatrzymany')
        self.check_card_root = tk.StringVar(value='')
        self.check_device_file = tk.StringVar(value='')
        self.check_server = tk.StringVar(value='')
        self.check_connection = tk.StringVar(value='Altirra: brak polaczenia')
        self.check_icon_labels = {}
        self.mini_window = None
        self.mini_drive = tk.IntVar(value=1)
        self.mini_line1 = tk.StringVar(value='SIO2SD')
        self.mini_line2 = tk.StringVar(value='Serwer zatrzymany')
        self.mini_on_top = tk.BooleanVar(value=bool(
            self.settings.get('mini_on_top', True)))
        self.mini_top_button = None
        self.mini_lcd_canvas = None
        self.mini_led_canvases = {}
        self.status_led_canvases = {}
        self.mini_led_jobs = {}
        self.mini_sio_override = None
        self.mini_sio_clear_job = None
        self.file_filter = tk.StringVar(value=self.settings.get(
            'file_filter', 'Obrazy i programy'))
        self.file_search = tk.StringVar(value='')
        self.browser_drive = tk.StringVar(value=self.settings.get(
            'browser_drive', 'D1:'))
        self.file_items = {}
        self._last_drive_signature = None
        self._last_full_geometry = self.settings.get('geometry')
        self._save_settings_job = None

        self._build_ui()
        self._refresh_config_summary()
        self._apply_saved_geometry()
        if self.settings.get('gui_mode') == 'mini':
            self.withdraw()
        self._update_checklist()
        self._refresh_drives()
        self._refresh_files()
        self.file_filter.trace_add('write', self._file_filter_changed)
        self.browser_drive.trace_add('write', lambda *_: self._queue_save_settings())
        self.file_search.trace_add('write', lambda *_: self._refresh_files())
        self.auto_start.trace_add('write', lambda *_: self._queue_save_settings())
        self.device_id.trace_add('write', self._config_controls_changed)
        self.cfg_hsindex.trace_add('write', self._config_controls_changed)
        self.cfg_turbo_hsindex.trace_add('write',
                                         self._config_controls_changed)
        self.cfg_atr_write_protect.trace_add('write',
                                             self._config_controls_changed)
        for variable in self.cfg_byte_vars:
            variable.trace_add('write', self._raw_config_changed)
        self.device_visible.trace_add('write', self._device_visible_changed)
        self.topdrive_turbo.trace_add('write', self._topdrive_turbo_changed)
        self.verbose.trace_add('write', self._verbose_changed)
        self.cfg_selector.trace_add('write', self._cfg_selector_changed)
        self.preserve_drive_mapping.trace_add(
            'write', lambda *_: self._queue_save_settings())
        self.mini_on_top.trace_add('write',
                                   lambda *_: self._queue_save_settings())
        self.bind('<Configure>', self._remember_full_geometry)
        self.after(150, self._drain_log)
        self.after(500, self._auto_refresh_drives)
        self.after(100, self._apply_startup_state)
        self.protocol('WM_DELETE_WINDOW', self._on_close)


def main():
    set_windows_app_id()
    app = SIO2SDGui()
    app._update_card_root_label()
    app.mainloop()


if __name__ == '__main__':
    main()
