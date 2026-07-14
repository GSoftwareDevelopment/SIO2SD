"""SIO2SDGuiActionsMixin."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from sio2sd_server import EmptyDisk, SIO2SDServerRuntime, clean_name


class SIO2SDGuiActionsMixin:
    def _open_card_root(self):
        path = self.card_root.get() or os.path.join(self.sd_dir.get(), 'Atari')
        if not path:
            return
        os.makedirs(path, exist_ok=True)
        try:
            os.startfile(path)
        except AttributeError:
            messagebox.showinfo('Katalog Atari', path)
        except OSError as exc:
            messagebox.showerror('Nie mozna otworzyc katalogu', str(exc))

    def _card_file_root(self):
        if self.runtime is not None and self.runtime.card is not None:
            return self.runtime.card.root
        root = self.card_root.get().strip()
        if root:
            return root
        base = self.sd_dir.get().strip() or self.default_sd
        return os.path.join(base, 'Atari')


    # --------------------------------------------------------------- actions

    def _start_server(self):
        if self.runtime is not None and self.runtime.running:
            return
        root = self.sd_dir.get().strip() or self.default_sd
        try:
            runtime = SIO2SDServerRuntime(
                root=root,
                devid=int(self.device_id.get()),
                read_only=self.read_only.get(),
                port=int(self.port.get()),
                verbose=self.verbose.get(),
                log=self._log,
                activity=self._activity,
                cfg_selector=self.cfg_selector.get(),
                config=self._config_from_controls(),
                device_enabled=self.device_visible.get(),
                topdrive_turbo=self.topdrive_turbo.get())
            card = runtime.start()
        except Exception as exc:
            messagebox.showerror('Nie mozna uruchomic serwera', str(exc))
            return
        self.runtime = runtime
        self._apply_config_to_controls(runtime.get_config())
        self.sd_dir.set(root)
        self.card_root.set(card.root)
        self.status.set('Serwer dziala na localhost:%d' % runtime.port)
        self._update_checklist()
        self._save_settings()
        self._refresh_files()
        self._refresh_drives()
        self._update_mini_lcd()

    def _stop_server(self):
        if self.runtime is None:
            return
        try:
            self.runtime.stop()
        except Exception as exc:
            messagebox.showerror('Nie mozna zatrzymac serwera', str(exc))
        self.runtime = None
        self.status.set('Serwer zatrzymany')
        self._set_check_item('connection', self.check_connection, False,
                             'Altirra: brak polaczenia')
        for name in ('SIOACT', 'SDACT', 'ERROR'):
            job = self.mini_led_jobs.pop(name, None)
            if job is not None:
                self.after_cancel(job)
            self._draw_mini_led(name, False)
            self._draw_status_led(name, False)
        self._update_checklist()
        self._refresh_drives()
        self._update_mini_lcd()

    def _mount_file(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        drive = self._selected_drive()
        if drive is None:
            return
        initial = runtime.card.root if runtime.card else self.default_sd
        path = filedialog.askopenfilename(initialdir=initial)
        if not path:
            return
        self._mount_path_to_drive(path, drive)

    def _mount_empty(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        drive = self._selected_drive()
        if drive is None:
            return
        try:
            runtime.card.mount_empty(
                drive, reset_mapping=not self.preserve_drive_mapping.get())
            self._activity('SDACT')
            self._log('D%d: podpieto pusty dysk' % drive)
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad pustego dysku', str(exc))
        self._refresh_drives()

    def _choose_atr_format(self):
        win = tk.Toplevel(self)
        win.title('Nowy ATR')
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()

        choice = tk.StringVar(value=self.ATR_FORMATS[0][0])
        filesystem = tk.StringVar(value=self.ATR_FILESYSTEMS[0][0])
        sectors_var = tk.StringVar(value=str(self.ATR_FORMATS[0][1]))
        sector_size_var = tk.StringVar(value=str(self.ATR_FORMATS[0][2]))
        volume_var = tk.StringVar(value='')
        result = {'format': None}

        frame = ttk.Frame(win, padding=12)
        frame.grid(row=0, column=0, sticky='nsew')
        ttk.Label(frame, text='System plikow').grid(
            row=0, column=0, sticky='w')
        fs_combo = ttk.Combobox(
            frame, textvariable=filesystem,
            values=[fmt[0] for fmt in self.ATR_FILESYSTEMS],
            state='readonly', width=28)
        fs_combo.grid(row=1, column=0, columnspan=2, sticky='ew',
                      pady=(4, 10))

        ttk.Label(frame, text='Geometria').grid(
            row=2, column=0, sticky='w')
        combo = ttk.Combobox(
            frame, textvariable=choice,
            values=[fmt[0] for fmt in self.ATR_FORMATS],
            state='readonly', width=28)
        combo.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(4, 10))

        ttk.Label(frame, text='Sektory').grid(row=4, column=0, sticky='w')
        sectors_entry = ttk.Entry(frame, textvariable=sectors_var, width=10)
        sectors_entry.grid(row=5, column=0, sticky='ew', padx=(0, 8))
        ttk.Label(frame, text='Bajtow/sektor').grid(row=4, column=1,
                                                    sticky='w')
        sector_size_combo = ttk.Combobox(
            frame, textvariable=sector_size_var,
            values=('128', '256'), state='readonly', width=10)
        sector_size_combo.grid(row=5, column=1, sticky='ew')

        ttk.Label(frame, text='VOLUME (SDX)').grid(
            row=6, column=0, columnspan=2, sticky='w', pady=(10, 0))
        volume_entry = ttk.Entry(frame, textvariable=volume_var, width=16)
        volume_entry.grid(row=7, column=0, columnspan=2, sticky='ew',
                          pady=(4, 0))
        combo.focus_set()

        def preset_changed(_event=None):
            selected = choice.get()
            for label, sectors, sector_size in self.ATR_FORMATS:
                if label == selected:
                    sectors_var.set(str(sectors))
                    sector_size_var.set(str(sector_size))
                    break

        combo.bind('<<ComboboxSelected>>', preset_changed)

        def accept():
            try:
                sectors = int(sectors_var.get().strip())
                sector_size = int(sector_size_var.get().strip())
            except ValueError:
                messagebox.showerror('Nowy ATR',
                                     'Podaj liczbe sektorow i rozmiar sektora.',
                                     parent=win)
                return
            if sectors <= 0 or sector_size not in (128, 256):
                messagebox.showerror(
                    'Nowy ATR',
                    'Geometria musi miec dodatnia liczbe sektorow i sektor 128 albo 256 bajtow.',
                    parent=win)
                return
            fs_key = 'blank'
            for label, key in self.ATR_FILESYSTEMS:
                if label == filesystem.get():
                    fs_key = key
                    break
            if fs_key == 'dos2' and (sector_size != 128 or sectors != 720):
                messagebox.showerror(
                    'Nowy ATR',
                    'DOS 2.x wymaga formatu SD 90 KB (720 x 128).',
                    parent=win)
                return
            if fs_key == 'mydos':
                if sector_size == 128 and sectors != 720:
                    messagebox.showerror(
                        'Nowy ATR',
                        'MyDOS z sektorami 128B jest dostepny dla SD 90 KB.',
                        parent=win)
                    return
                if sector_size == 256 and sectors > 1792:
                    messagebox.showerror(
                        'Nowy ATR',
                        'Ta geometria MyDOS wymaga rozszerzonego VTOC.',
                        parent=win)
                    return
            if fs_key == 'sdx' and sector_size != 128:
                messagebox.showerror(
                    'Nowy ATR',
                    'SDX jest teraz generowany dla sektorow 128B.',
                    parent=win)
                return
            result['format'] = {
                'total_sectors': sectors,
                'sector_size': sector_size,
                'filesystem': fs_key,
                'volume_label': volume_var.get(),
            }
            win.destroy()

        def cancel():
            win.destroy()

        ttk.Button(frame, text='Utworz', command=accept).grid(
            row=8, column=0, sticky='e', padx=(0, 6), pady=(12, 0))
        ttk.Button(frame, text='Anuluj', command=cancel).grid(
            row=8, column=1, sticky='w', pady=(12, 0))
        win.bind('<Return>', lambda _event: accept())
        win.bind('<Escape>', lambda _event: cancel())
        win.protocol('WM_DELETE_WINDOW', cancel)
        win.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - win.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - win.winfo_height()) // 2)
        win.geometry('+%d+%d' % (x, y))
        self.wait_window(win)
        return result['format']

    def _create_atr_drive(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        drive = self._selected_drive()
        if drive is None:
            return
        fmt = self._choose_atr_format()
        if fmt is None:
            return
        try:
            path = runtime.card.create_empty_atr(
                total_sectors=fmt['total_sectors'],
                sector_size=fmt['sector_size'],
                filesystem=fmt['filesystem'],
                volume_label=fmt.get('volume_label'))
            runtime.card.mount(
                drive, path,
                reset_mapping=not self.preserve_drive_mapping.get())
            self._activity('SDACT')
            self._log('D%d: utworzono i zamontowano %s' %
                      (drive, os.path.basename(path)))
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad tworzenia ATR', str(exc))
            return
        self._refresh_files()
        self._refresh_drives()

    def _unmount(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        drive = self._selected_drive()
        if drive is None:
            return
        try:
            runtime.card.umount(
                drive, reset_mapping=not self.preserve_drive_mapping.get())
            self._activity('SDACT')
            self._log('D%d: odmontowano' % drive)
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad odmontowania', str(exc))
        self._refresh_drives()

    def _map_drive_to_virtual(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        drive = self._selected_drive()
        if drive is None:
            return
        vslot = self._selected_virtual_slot()
        if vslot is None:
            return
        try:
            runtime.card.map_drive_to_virtual(drive, vslot)
            self._activity('SDACT')
            self._log('D%d: mapowanie -> V%d' % (drive, vslot))
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad mapowania', str(exc))
            return
        self._refresh_drives()

    def _reset_drive_mapping(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        drive = self._selected_drive()
        if drive is None:
            return
        try:
            runtime.card.reset_drive_mapping(drive)
            self._activity('SDACT')
            self._log('D%d: mapowanie -> D%d' % (drive, drive))
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad mapowania', str(exc))
            return
        self._refresh_drives()

    def _swap_drive_virtual(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        drive = self._selected_drive()
        if drive is None:
            return
        vslot = self._selected_virtual_slot()
        if vslot is None:
            return
        try:
            runtime.card.swap_drive_with_virtual(drive, vslot)
            self._activity('SDACT')
            self._log('D%d <-> V%d: zamieniono sloty' % (drive, vslot))
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad zamiany slotow', str(exc))
            return
        self._refresh_drives()


    def _mount_selected_file(self):
        path = self._selected_file_path()
        if path is None:
            return
        drive = self._browser_drive_number()
        if drive is None:
            return
        self._mount_path_to_drive(path, drive)

    def _mount_path_to_drive(self, path, drive):
        runtime = self._require_runtime()
        if runtime is None:
            return False
        try:
            runtime.card.mount(
                drive, runtime.card.find_file(path),
                reset_mapping=not self.preserve_drive_mapping.get())
            self._activity('SDACT')
            self._log('D%d: zamontowano %s' % (drive, path))
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad montowania', str(exc))
            return False
        self._refresh_drives()
        return True

    def _mount_virtual_file(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        vslot = self._selected_virtual_slot()
        if vslot is None:
            return
        initial = runtime.card.root if runtime.card else self.default_sd
        path = filedialog.askopenfilename(initialdir=initial)
        if not path:
            return
        try:
            runtime.card.mount_virtual(vslot, runtime.card.find_file(path))
            self._activity('SDACT')
            self._log('V%d: zamontowano %s' % (vslot, path))
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad montowania V', str(exc))
            return
        self._refresh_drives()

    def _mount_virtual_empty(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        vslot = self._selected_virtual_slot()
        if vslot is None:
            return
        try:
            runtime.card.mount_empty_virtual(vslot)
            self._activity('SDACT')
            self._log('V%d: podpieto pusty dysk' % vslot)
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad pustego V', str(exc))
            return
        self._refresh_drives()

    def _create_atr_virtual(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        vslot = self._selected_virtual_slot()
        if vslot is None:
            return
        fmt = self._choose_atr_format()
        if fmt is None:
            return
        try:
            path = runtime.card.create_empty_atr(
                total_sectors=fmt['total_sectors'],
                sector_size=fmt['sector_size'],
                filesystem=fmt['filesystem'],
                volume_label=fmt.get('volume_label'))
            runtime.card.mount_virtual(vslot, path)
            self._activity('SDACT')
            self._log('V%d: utworzono i zamontowano %s' %
                      (vslot, os.path.basename(path)))
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad tworzenia ATR', str(exc))
            return
        self._refresh_files()
        self._refresh_drives()

    def _unmount_virtual(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        vslot = self._selected_virtual_slot()
        if vslot is None:
            return
        try:
            runtime.card.umount_virtual(vslot)
            self._activity('SDACT')
            self._log('V%d: odmontowano' % vslot)
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad odmontowania V', str(exc))
            return
        self._refresh_drives()


    def _on_close(self):
        self._save_settings()
        if self.runtime is not None:
            try:
                self.runtime.stop()
            except Exception:
                pass
        self.destroy()


