"""SIO2SDGuiMiniMixin."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from sio2sd_server import EmptyDisk, clean_name


class SIO2SDGuiMiniMixin:
    def _show_mini(self, hide_main=True):
        if self.mini_window is not None and self.mini_window.winfo_exists():
            self.mini_window.deiconify()
            self._apply_mini_topmost()
            if hide_main:
                self._last_full_geometry = self.geometry()
                self.withdraw()
                self._queue_save_settings()
            return
        win = tk.Toplevel(self)
        self.mini_window = win
        win.title('SIO2SD mini')
        win.resizable(False, False)
        win.configure(bg='#202020')
        self._apply_mini_topmost()
        win.protocol('WM_DELETE_WINDOW', self._hide_mini)

        case = tk.Frame(win, bg='#202020', padx=12, pady=12)
        case.pack(fill='both', expand=True)

        bezel = tk.Frame(case, bg='#111111', bd=2, relief='ridge',
                         padx=8, pady=8)
        bezel.pack(fill='x', pady=(0, 10))
        display = tk.Frame(bezel, bg='#111111')
        display.pack(fill='x')
        lcd = tk.Frame(display, bg='#789461', bd=2, relief='sunken',
                       padx=9, pady=7)
        lcd.pack(side='left')
        self.mini_lcd_canvas = tk.Canvas(
            lcd, width=452, height=92, bg='#9fca7b',
            highlightthickness=0, bd=0)
        self.mini_lcd_canvas.pack()

        leds = tk.Frame(display, bg='#111111', padx=8)
        leds.pack(side='right', fill='y')
        for name, color in (('SIOACT', '#d12a2a'),
                            ('SDACT', '#33c65a'),
                            ('ERROR', '#d12a2a')):
            row = tk.Frame(leds, bg='#111111')
            row.pack(anchor='w', pady=3)
            lamp = tk.Canvas(row, width=18, height=18, bg='#111111',
                             highlightthickness=0, bd=0)
            lamp.pack(side='left')
            tk.Label(row, text=name, fg='#d0d0d0', bg='#111111',
                     font=('Segoe UI', 7, 'bold')).pack(side='left',
                                                        padx=(4, 0))
            self.mini_led_canvases[name] = (lamp, color)
            self._draw_mini_led(name, False)

        nav = tk.Frame(case, bg='#202020')
        nav.pack(fill='x', pady=(0, 8))
        tk.Button(nav, text='<<', width=5, command=lambda: self._mini_step(-1)).pack(
            side='left')
        tk.Button(nav, text='>>', width=5, command=lambda: self._mini_step(1)).pack(
            side='left', padx=(6, 0))
        self.mini_top_button = tk.Button(
            nav, width=8, command=self._toggle_mini_topmost)
        self.mini_top_button.pack(side='right')

        keys = tk.Frame(case, bg='#202020')
        keys.pack(fill='x')
        tk.Button(keys, text='K1 MNT', width=8, command=self._mini_mount).pack(
            side='left')
        tk.Button(keys, text='K2 EMP', width=8, command=self._mini_empty).pack(
            side='left', padx=(6, 0))
        tk.Button(keys, text='K3 EJT', width=8, command=self._mini_eject).pack(
            side='left', padx=(6, 0))
        tk.Button(keys, text='K4 HIDE', width=8, command=self._hide_mini).pack(
            side='left', padx=(6, 0))

        self._update_mini_lcd()
        if hide_main:
            self._last_full_geometry = self.geometry()
            self.withdraw()
        self._apply_mini_topmost()
        self._queue_save_settings()

    def _apply_mini_topmost(self):
        if self.mini_window is None or not self.mini_window.winfo_exists():
            return
        on_top = bool(self.mini_on_top.get())
        self.mini_window.attributes('-topmost', on_top)
        if on_top:
            self.mini_window.lift()
        self._sync_mini_top_button()

    def _sync_mini_top_button(self):
        if self.mini_top_button is None:
            return
        on_top = bool(self.mini_on_top.get())
        self.mini_top_button.configure(
            text='TOP ON' if on_top else 'TOP OFF',
            relief='sunken' if on_top else 'raised')

    def _toggle_mini_topmost(self):
        self.mini_on_top.set(not self.mini_on_top.get())
        self._apply_mini_topmost()

    def _draw_mini_led(self, name, active):
        entry = self.mini_led_canvases.get(name)
        if entry is None:
            return
        canvas, color = entry
        self._draw_led_canvas(canvas, color, name, active)

    def _draw_status_led(self, name, active):
        entry = self.status_led_canvases.get(name)
        if entry is None:
            return
        canvas, color = entry
        self._draw_led_canvas(canvas, color, name, active)

    def _pulse_mini_led(self, name, duration=220):
        self._draw_mini_led(name, True)
        self._draw_status_led(name, True)
        job = self.mini_led_jobs.pop(name, None)
        if job is not None:
            self.after_cancel(job)
        self.mini_led_jobs[name] = self.after(
            duration, lambda n=name: self._clear_mini_led(n))

    def _clear_mini_led(self, name):
        self.mini_led_jobs.pop(name, None)
        self._draw_mini_led(name, False)
        self._draw_status_led(name, False)

    def _activity(self, name, detail=None):
        self.activity_queue.put((name, detail))

    def _show_sio_command(self, detail):
        if not detail:
            return
        try:
            line1, line2 = detail
        except (TypeError, ValueError):
            line1, line2 = str(detail), ''
        self.mini_sio_override = (str(line1)[:16], str(line2)[:16])
        if self.mini_sio_clear_job is not None:
            self.after_cancel(self.mini_sio_clear_job)
        self.mini_sio_clear_job = self.after(5000, self._clear_sio_command)
        self._render_mini_lcd()

    def _clear_sio_command(self):
        self.mini_sio_clear_job = None
        self.mini_sio_override = None
        self._update_mini_lcd()

    def _render_mini_lcd(self):
        canvas = self.mini_lcd_canvas
        if canvas is None:
            return
        dot = 4
        gap = 1
        char_gap = 3
        line_gap = 8
        margin_x = 10
        margin_y = 8
        active = '#1d3f18'
        inactive = '#86aa68'
        canvas.delete('all')
        lines = (
            (self.mini_sio_override[0] if self.mini_sio_override
             else self.mini_line1.get()).upper()[:16].ljust(16),
            (self.mini_sio_override[1] if self.mini_sio_override
             else self.mini_line2.get()).upper()[:16].ljust(16),
        )
        char_w = 5 * (dot + gap) - gap + char_gap
        row_h = 7 * (dot + gap) - gap
        for line_no, text in enumerate(lines):
            y0 = margin_y + line_no * (row_h + line_gap)
            for col, char in enumerate(text):
                pattern = self.DOT_MATRIX_FONT.get(char, self.DOT_MATRIX_FONT['?'])
                x0 = margin_x + col * char_w
                for py, bits in enumerate(pattern):
                    for px, bit in enumerate(bits):
                        x = x0 + px * (dot + gap)
                        y = y0 + py * (dot + gap)
                        canvas.create_rectangle(
                            x, y, x + dot - 1, y + dot - 1,
                            outline='',
                            fill=active if bit == '1' else inactive)

    def _hide_mini(self):
        if self.mini_window is not None and self.mini_window.winfo_exists():
            self.mini_window.withdraw()
        if self.state() == 'withdrawn':
            self._restore_from_mini()
        else:
            self._queue_save_settings()

    def _restore_from_mini(self):
        self.deiconify()
        self.lift()
        self._queue_save_settings()

    def _mini_step(self, delta):
        drive = self.mini_drive.get() + delta
        if drive < 1:
            drive = 15
        elif drive > 15:
            drive = 1
        self.mini_drive.set(drive)
        if self.drives.exists(str(drive)):
            self.drives.selection_set(str(drive))
            self.drives.focus(str(drive))
        self._update_mini_lcd()

    def _mini_mount(self):
        drive = self.mini_drive.get()
        initial = self.runtime.card.root if self.runtime and self.runtime.card else self._card_file_root()
        path = filedialog.askopenfilename(parent=self.mini_window or self,
                                          initialdir=initial)
        if path:
            self._mount_path_to_drive(path, drive)

    def _mini_empty(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        drive = self.mini_drive.get()
        try:
            runtime.card.mount_empty(
                drive, reset_mapping=not self.preserve_drive_mapping.get())
            self._activity('SDACT')
            self._log('D%d: podpieto pusty dysk' % drive)
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad pustego dysku', str(exc),
                                 parent=self.mini_window or self)
        self._refresh_drives()

    def _mini_eject(self):
        runtime = self._require_runtime()
        if runtime is None:
            return
        drive = self.mini_drive.get()
        try:
            runtime.card.umount(
                drive, reset_mapping=not self.preserve_drive_mapping.get())
            self._activity('SDACT')
            self._log('D%d: odmontowano' % drive)
        except Exception as exc:
            self._activity('ERROR')
            messagebox.showerror('Blad odmontowania', str(exc),
                                 parent=self.mini_window or self)
        self._refresh_drives()

    def _update_mini_lcd(self):
        if self.mini_sio_override is not None:
            self._render_mini_lcd()
            return
        drive = self.mini_drive.get()
        card = self.runtime.card if self.runtime and self.runtime.card else None
        if card is None:
            self.mini_line1.set('SIO2SD')
            self.mini_line2.set('SERVER OFF')
            self._render_mini_lcd()
            return
        name = '-OFF-'
        ent = self._active_drive_entry(card, drive)
        if ent is not None:
            disk, entry = ent
            name = '=EMPTY=' if isinstance(disk, EmptyDisk) else (
                clean_name(entry[0:39]) or '=EMPTY=')
        mapped = self._mapped_drive_label(card, drive)
        prefix = (mapped + ':') if ' -> ' in mapped else ('D%d:' % drive)
        self.mini_line1.set((prefix + name)[:16].ljust(16))
        self.mini_line2.set(self._mini_lcd_path(card)[:16].ljust(16))
        self._render_mini_lcd()

    def _mini_lcd_path(self, card):
        try:
            rel = os.path.relpath(card.cwd, card.root)
        except (OSError, ValueError):
            rel = '.'
        if rel == '.':
            path = '/'
        else:
            path = '/' + rel.replace(os.sep, '/')
        if len(path) > 16:
            path = '<' + path[-15:]
        return path
