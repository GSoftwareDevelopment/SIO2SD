"""SIO2SDGuiConfigMixin."""

import json
import os
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from sio2sd_server import SIO2SDServerRuntime


class SIO2SDGuiConfigMixin:
    def _ensure_runtime_files(self):
        if not getattr(sys, 'frozen', False):
            return
        for name in ('sio2sd.atdevice', 'xexboot.bin'):
            source = os.path.join(self.bundle_root, 'altirra', name)
            target = os.path.join(self.project_root, 'altirra', name)
            if not os.path.exists(source) or os.path.exists(target):
                continue
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source, target)
            except OSError:
                pass

    def _add_check_item(self, parent, row, column, key, textvariable,
                        padx=(0, 0), pady=(0, 0)):
        item = ttk.Frame(parent)
        item.grid(row=row, column=column, sticky='w', padx=padx, pady=pady)
        icon = tk.Label(item, text='✗', fg='#b3261e', width=2,
                        font=('Segoe UI Symbol', 11, 'bold'))
        icon.pack(side='left')
        ttk.Label(item, textvariable=textvariable).pack(side='left')
        self.check_icon_labels[key] = icon

    def _set_check_item(self, key, textvariable, ok, text):
        textvariable.set(text)
        icon = self.check_icon_labels.get(key)
        if icon is None:
            return
        icon.configure(
            text='✓' if ok else '✗',
            fg='#12805c' if ok else '#b3261e')

    def _load_settings(self):
        try:
            with open(self.settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _default_sio2sd_config(self):
        cfg = bytearray(16)
        cfg[0] = 6
        cfg[1] = 40
        cfg[4] = int(self.settings.get('device_id', 0)) & 3
        cfg[5] = 1
        return cfg

    def _load_sio2sd_config(self):
        cfg = self._default_sio2sd_config()
        saved = self.settings.get('sio2sd_config')
        if isinstance(saved, list):
            for idx, value in enumerate(saved[:16]):
                try:
                    cfg[idx] = int(value) & 0xFF
                except (TypeError, ValueError):
                    pass
        return cfg

    def _settings_snapshot(self):
        return {
            'sd_dir': self.sd_dir.get().strip() or self.default_sd,
            'device_id': self.device_id.get(),
            'port': int(self.port.get()),
            'read_only': bool(self.read_only.get()),
            'device_visible': bool(self.device_visible.get()),
            'topdrive_turbo': bool(self.topdrive_turbo.get()),
            'sio2sd_config': list(self._config_from_controls()),
            'verbose': bool(self.verbose.get()),
            'auto_start': bool(self.auto_start.get()),
            'cfg_selector': bool(self.cfg_selector.get()),
            'preserve_drive_mapping': bool(self.preserve_drive_mapping.get()),
            'mini_on_top': bool(self.mini_on_top.get()),
            'file_filter': self.file_filter.get(),
            'browser_drive': self.browser_drive.get(),
            'gui_mode': self._current_gui_mode(),
            'geometry': self._last_full_geometry or self.geometry(),
        }

    def _save_settings(self):
        try:
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self._settings_snapshot(), f, indent=2)
        except OSError as exc:
            self._log('Nie mozna zapisac ustawien: %s' % exc)

    def _queue_save_settings(self):
        if self._save_settings_job is not None:
            self.after_cancel(self._save_settings_job)
        self._save_settings_job = self.after(300, self._flush_queued_settings)

    def _flush_queued_settings(self):
        self._save_settings_job = None
        self._save_settings()

    def _apply_saved_geometry(self):
        geometry = self.settings.get('geometry')
        if isinstance(geometry, str) and 'x' in geometry:
            try:
                self.geometry(geometry)
            except tk.TclError:
                pass

    def _remember_full_geometry(self, _event=None):
        if self.state() != 'withdrawn':
            self._last_full_geometry = self.geometry()

    def _file_filter_changed(self, *_args):
        self._refresh_files()
        self._queue_save_settings()

    def _verbose_changed(self, *_args):
        enabled = bool(self.verbose.get())
        if self.runtime is not None:
            self.runtime.set_verbose(enabled)
        self._queue_save_settings()

    def _cfg_selector_changed(self, *_args):
        enabled = bool(self.cfg_selector.get())
        if self.runtime is not None:
            self.runtime.set_cfg_selector(enabled)
        self._queue_save_settings()
        self._update_mini_lcd()

    def _device_visible_changed(self, *_args):
        enabled = bool(self.device_visible.get())
        if self.runtime is not None:
            self.runtime.set_device_enabled(enabled)
        self.cfg_status.set('SIO2SD %s' %
                            ('widoczny dla Atari' if enabled else
                             'niewidoczny dla Atari'))
        self._queue_save_settings()

    def _topdrive_turbo_changed(self, *_args):
        enabled = bool(self.topdrive_turbo.get())
        if self.runtime is not None:
            self.runtime.set_topdrive_turbo(enabled)
        self.cfg_status.set('TopDrive turbo %s' %
                            ('wlaczony' if enabled else 'wylaczony'))
        self._queue_save_settings()

    def _config_controls_changed(self, *_args):
        if self._updating_config_controls:
            return
        cfg = self._config_from_controls()
        self.sio2sd_config = bytearray(cfg)
        self._set_config_byte_vars(cfg)
        self._refresh_config_summary(cfg)
        self._queue_save_settings()
        if self.runtime is not None:
            if self._apply_config_job is not None:
                self.after_cancel(self._apply_config_job)
            self._apply_config_job = self.after(300, self._auto_apply_sio2sd_config)

    def _raw_config_changed(self, *_args):
        if self._updating_config_controls or self._syncing_config_bytes:
            return
        cfg = bytearray(self._config_from_raw_vars())
        self.sio2sd_config = cfg
        self._updating_config_controls = True
        try:
            self.cfg_hsindex.set(cfg[0])
            self.cfg_turbo_hsindex.set(cfg[1])
            self.device_id.set(str(cfg[4] & 3))
            self.cfg_atr_write_protect.set(bool(cfg[5] & 1))
        finally:
            self._updating_config_controls = False
        self._refresh_config_summary(cfg)
        self._queue_save_settings()
        if self.runtime is not None:
            if self._apply_config_job is not None:
                self.after_cancel(self._apply_config_job)
            self._apply_config_job = self.after(300, self._auto_apply_sio2sd_config)

    def _byte_var(self, variable, default=0):
        try:
            return max(0, min(255, int(variable.get())))
        except (tk.TclError, ValueError):
            return default

    def _config_from_raw_vars(self):
        cfg = bytearray(self.sio2sd_config[:16])
        for idx, variable in enumerate(self.cfg_byte_vars):
            cfg[idx] = self._byte_var(variable, cfg[idx])
        return bytes(cfg)

    def _set_config_byte_vars(self, config):
        cfg = bytearray(bytes(config)[:16].ljust(16, b'\0'))
        self._syncing_config_bytes = True
        try:
            for idx, variable in enumerate(self.cfg_byte_vars):
                if self._byte_var(variable, -1) != cfg[idx]:
                    variable.set(cfg[idx])
        finally:
            self._syncing_config_bytes = False

    def _config_from_controls(self):
        cfg = bytearray(self._config_from_raw_vars())
        cfg[0] = self._byte_var(self.cfg_hsindex, cfg[0])
        cfg[1] = self._byte_var(self.cfg_turbo_hsindex, cfg[1])
        try:
            cfg[4] = (cfg[4] & 0xFC) | (int(self.device_id.get()) & 3)
        except ValueError:
            cfg[4] &= 0xFC
        if self.cfg_atr_write_protect.get():
            cfg[5] |= 1
        else:
            cfg[5] &= 0xFE
        return bytes(cfg)

    def _apply_config_to_controls(self, config):
        cfg = bytearray(bytes(config)[:16].ljust(16, b'\0'))
        self._updating_config_controls = True
        try:
            self.sio2sd_config = cfg
            self.cfg_hsindex.set(cfg[0])
            self.cfg_turbo_hsindex.set(cfg[1])
            self.device_id.set(str(cfg[4] & 3))
            self.cfg_atr_write_protect.set(bool(cfg[5] & 1))
            self._set_config_byte_vars(cfg)
            self._refresh_config_summary(cfg)
        finally:
            self._updating_config_controls = False

    def _refresh_config_summary(self, config=None):
        cfg = bytes(config) if config is not None else self._config_from_controls()
        self.cfg_raw.set(' '.join('%02X' % b for b in cfg))

    def _read_sio2sd_config(self):
        if self.runtime is not None:
            cfg = self.runtime.get_config()
            self._apply_config_to_controls(cfg)
            self.cfg_status.set('Odczytano z dzialajacego serwera')
        else:
            self._apply_config_to_controls(self.sio2sd_config)
            self.cfg_status.set('Serwer nie dziala - pokazano zapisane ustawienia')

    def _auto_apply_sio2sd_config(self):
        self._apply_config_job = None
        if self.runtime is None:
            return
        cfg = self._config_from_controls()
        self.sio2sd_config = bytearray(cfg)
        self._refresh_config_summary()
        if cfg != self.runtime.get_config():
            self.runtime.set_config(cfg)
            self.cfg_status.set('Zastosowano automatycznie')

    def _apply_sio2sd_config(self):
        if self._apply_config_job is not None:
            self.after_cancel(self._apply_config_job)
            self._apply_config_job = None
        cfg = self._config_from_controls()
        self.sio2sd_config = bytearray(cfg)
        self._refresh_config_summary()
        if self.runtime is not None:
            self.runtime.set_config(cfg)
            self.cfg_status.set('Zastosowano w dzialajacym serwerze')
        else:
            self.cfg_status.set('Zapisano do uzycia przy starcie serwera')
        self._queue_save_settings()

    def _current_gui_mode(self):
        if self.mini_window is not None and self.mini_window.winfo_exists():
            if self.state() == 'withdrawn':
                return 'mini'
        return 'full'

    def _apply_startup_state(self):
        if self.auto_start.get():
            self._start_server()
        if self.settings.get('gui_mode') == 'mini':
            self._show_mini(hide_main=True)

    def _browse_sd(self):
        path = filedialog.askdirectory(initialdir=self.sd_dir.get() or self.default_sd)
        if path:
            self.sd_dir.set(path)
            self._update_card_root_label()
            self._update_checklist()
            self._refresh_files()
            self._save_settings()

    def _update_card_root_label(self):
        base = self.sd_dir.get().strip()
        self.card_root.set(os.path.join(base, 'Atari') if base else '')

    def _update_checklist(self):
        card_root = self._card_file_root()
        if os.path.isdir(card_root):
            self._set_check_item('card_root', self.check_card_root, True,
                                 'Katalog Atari: gotowy')
        else:
            self._set_check_item('card_root', self.check_card_root, False,
                                 'Katalog Atari: zostanie utworzony')

        atdevice = os.path.join(self.project_root, 'altirra', 'sio2sd.atdevice')
        if os.path.isfile(atdevice):
            self._set_check_item('device_file', self.check_device_file, True,
                                 'sio2sd.atdevice: dostepny')
        else:
            self._set_check_item('device_file', self.check_device_file, False,
                                 'sio2sd.atdevice: brak pliku')

        if self.runtime is not None and self.runtime.running:
            self._set_check_item('server', self.check_server, True,
                                 'Serwer TCP: dziala na porcie %s' %
                                 self.port.get())
        else:
            self._set_check_item('server', self.check_server, False,
                                 'Serwer TCP: zatrzymany')
