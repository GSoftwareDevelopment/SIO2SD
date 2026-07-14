"""SIO2SDGuiLogMixin."""

import queue
import re
import tkinter as tk


class SIO2SDGuiLogMixin:
    def _log(self, text):
        self.log_queue.put(text)

    def _is_hidden_log_message(self, msg):
        return re.match(r'^[0-9A-Fa-f]{16} Script event\(', str(msg)) is not None

    def _log_compact_key(self, msg):
        text = str(msg)
        # Verbose device-server lines start with a changing 16-digit timestamp.
        match = re.match(r'^[0-9A-Fa-f]{16} (.+)$', text)
        if match:
            return 'timestamped:' + match.group(1), True
        if text.startswith('SIO2SD: '):
            return 'sio:' + text, True
        return 'exact:' + text, False

    def _format_log_line(self, msg, count):
        if count > 1:
            return '[x%d] %s' % (count, msg)
        return msg

    def _clear_log(self):
        while True:
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                break
        self._log_compact_entries.clear()
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def _append_log_message(self, msg):
        msg = str(msg)
        key, compactable = self._log_compact_key(msg)
        self.log_text.configure(state='normal')
        if compactable and key in self._log_compact_entries:
            start, count, _last_msg = self._log_compact_entries[key]
            count += 1
            self._log_compact_entries[key] = (start, count, msg)
            self.log_text.delete(start, start + ' lineend')
            self.log_text.insert(start, self._format_log_line(msg, count))
        else:
            if not compactable:
                self._log_compact_entries.clear()
            start = self.log_text.index('end-1c')
            if compactable:
                self._log_compact_entries[key] = (start, 1, msg)
            self.log_text.insert('end', self._format_log_line(msg, 1) + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _drain_log(self):
        activity_seen = False
        while True:
            try:
                item = self.activity_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple):
                name, detail = item
            else:
                name, detail = item, None
            if name == 'SIOCMD':
                self._show_sio_command(detail)
                continue
            activity_seen = True
            self._pulse_mini_led(name, 700 if name == 'ERROR' else 180)
        if activity_seen:
            self._update_mini_lcd()
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if 'Polaczono z emulatorem Altirra' in msg:
                self._set_check_item('connection', self.check_connection, True,
                                     'Altirra: polaczona')
                self._update_mini_lcd()
            elif 'Rozlaczono emulator Altirra' in msg:
                self._set_check_item('connection', self.check_connection, False,
                                     'Altirra: brak polaczenia')
                self._update_mini_lcd()
            elif 'Zimny start Atari' in msg:
                self._refresh_drives()
                self._update_mini_lcd()
            if self._is_hidden_log_message(msg):
                continue
            self._append_log_message(msg)
        self.after(150, self._drain_log)
