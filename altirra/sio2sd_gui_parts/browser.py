"""SIO2SDGuiBrowserMixin."""

import os
from tkinter import messagebox

from sio2sd_server import EmptyDisk, clean_name


class SIO2SDGuiBrowserMixin:
    def _require_runtime(self):
        if self.runtime is None or not self.runtime.running or self.runtime.card is None:
            messagebox.showinfo('Serwer', 'Najpierw uruchom serwer.')
            return None
        return self.runtime

    def _selected_drive(self):
        sel = self.drives.selection()
        if not sel:
            messagebox.showinfo('Naped', 'Wybierz naped D1:-D15:.')
            return None
        return int(sel[0])

    def _selected_virtual_slot(self):
        sel = self.virtuals.selection()
        if not sel:
            messagebox.showinfo('Slot V', 'Wybierz slot V1:-V99.')
            return None
        try:
            return int(sel[0][1:])
        except (ValueError, IndexError):
            messagebox.showerror('Slot V', 'Niepoprawny slot wirtualny.')
            return None

    def _drive_selection_changed(self, _event=None):
        sel = self.drives.selection()
        if sel:
            self.mini_drive.set(int(sel[0]))
            self._update_mini_lcd()

    def _disk_info(self, disk):
        typ = type(disk).__name__
        try:
            sectors = str(disk.total_sectors())
        except Exception:
            sectors = ''
        ro = 'tak' if getattr(disk, 'read_only', False) else ''
        return typ, sectors, ro

    def _drive_mapped_slot(self, card, drive):
        if card is None:
            return drive - 1
        try:
            return card._slot_for_drive(drive)
        except AttributeError:
            return drive - 1

    def _slot_label(self, card, slot):
        if card is None:
            return ''
        try:
            return card._slot_name(slot)
        except AttributeError:
            if 0 <= slot < 15:
                return 'D%d' % (slot + 1)
            return 'V%d' % (slot - 14)

    def _mapped_drive_label(self, card, drive):
        slot = self._drive_mapped_slot(card, drive)
        label = self._slot_label(card, slot)
        direct = 'D%d' % drive
        return direct if label == direct else '%s -> %s' % (direct, label)

    def _active_drive_entry(self, card, drive):
        if card is None:
            return None
        try:
            return card._entry_for_drive(drive)
        except AttributeError:
            return card.drives.get(drive)

    def _virtual_entry(self, card, vslot):
        if card is None:
            return None
        try:
            return card.vslots.get(vslot)
        except AttributeError:
            return None

    def _drive_row_values(self, mapping, entry):
        if entry is None:
            return (mapping, 'pusty', '', '', '', '')
        disk, entry = entry
        name = clean_name(entry[0:39]) or '(pusty dysk)'
        typ, sectors, ro = self._disk_info(disk)
        if isinstance(disk, EmptyDisk):
            typ = 'EmptyDisk'
        return (mapping, 'zamontowany', name, typ, sectors, ro)

    def _slot_row_values(self, entry):
        if entry is None:
            return ('pusty', '', '', '', '')
        disk, entry = entry
        name = clean_name(entry[0:39]) or '(pusty dysk)'
        typ, sectors, ro = self._disk_info(disk)
        if isinstance(disk, EmptyDisk):
            typ = 'EmptyDisk'
        return ('zamontowany', name, typ, sectors, ro)

    def _file_kind(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext == '.atr':
            return 'ATR'
        if ext in ('.xex', '.com', '.exe'):
            return 'XEX'
        if os.path.isfile(path):
            try:
                if os.path.getsize(path) <= 92160:
                    return 'RAW'
            except OSError:
                pass
        return 'plik'

    def _file_visible(self, path):
        name = os.path.basename(path)
        text = self.file_search.get().strip().lower()
        if text and text not in name.lower() and text not in path.lower():
            return False
        kind = self._file_kind(path)
        filt = self.file_filter.get()
        if filt == 'Wszystkie':
            return True
        if filt == 'Obrazy i programy':
            return kind in ('ATR', 'XEX')
        if filt == 'ATR':
            return kind == 'ATR'
        if filt == 'XEX/COM/EXE':
            return kind == 'XEX'
        if filt == 'RAW':
            return kind == 'RAW'
        return True

    def _format_size(self, size):
        if size >= 1024 * 1024:
            return '%.1f MB' % (size / (1024 * 1024))
        if size >= 1024:
            return '%.1f KB' % (size / 1024)
        return '%d B' % size

    def _drive_signature(self):
        card = self.runtime.card if self.runtime and self.runtime.card else None
        if card is None:
            return ()
        sig = []
        for drive in range(1, 16):
            mapped = self._mapped_drive_label(card, drive)
            ent = self._active_drive_entry(card, drive)
            if ent is None:
                sig.append((drive, mapped, None))
                continue
            disk, entry = ent
            name = clean_name(entry[0:39]) or '(pusty dysk)'
            typ, sectors, ro = self._disk_info(disk)
            sig.append((drive, mapped, name, typ, sectors, ro))
        for vslot in range(1, 100):
            ent = self._virtual_entry(card, vslot)
            if ent is None:
                sig.append(('V', vslot, None))
                continue
            disk, entry = ent
            name = clean_name(entry[0:39]) or '(pusty dysk)'
            typ, sectors, ro = self._disk_info(disk)
            sig.append(('V', vslot, name, typ, sectors, ro))
        return tuple(sig)

    def _auto_refresh_drives(self):
        sig = self._drive_signature()
        if sig != self._last_drive_signature:
            self._refresh_drives()
        self.after(500, self._auto_refresh_drives)


    def _selected_file_path(self):
        sel = self.files.selection()
        if not sel:
            messagebox.showinfo('Plik', 'Wybierz plik z listy.')
            return None
        return self.file_items.get(sel[0])

    def _browser_drive_number(self):
        txt = self.browser_drive.get().strip().upper()
        if txt.startswith('D') and txt.endswith(':'):
            try:
                n = int(txt[1:-1])
            except ValueError:
                n = 0
            if 1 <= n <= 15:
                return n
        messagebox.showerror('Naped', 'Wybierz naped D1:-D15:.')
        return None


    def _refresh_files(self):
        current = self.files.selection()
        selected_path = self.file_items.get(current[0]) if current else None
        self.files.delete(*self.files.get_children())
        self.file_items = {}
        root = self._card_file_root()
        if not root or not os.path.isdir(root):
            return
        rows = []
        for base, dirs, files in os.walk(root):
            dirs.sort(key=str.lower)
            for name in sorted(files, key=str.lower):
                path = os.path.join(base, name)
                if not self._file_visible(path):
                    continue
                rel = os.path.relpath(path, root)
                rows.append((rel.lower(), name, path, rel))
        for idx, (_key, name, path, rel) in enumerate(rows):
            iid = 'file%d' % idx
            self.file_items[iid] = path
            try:
                size = self._format_size(os.path.getsize(path))
            except OSError:
                size = ''
            self.files.insert('', 'end', iid=iid, text=name,
                              values=(self._file_kind(path), size, rel))
            if selected_path and os.path.normcase(path) == os.path.normcase(selected_path):
                self.files.selection_set(iid)
                self.files.focus(iid)

    def _refresh_drives(self):
        current = self.drives.selection()
        selected = current[0] if current else '1'
        vcurrent = self.virtuals.selection()
        vselected = vcurrent[0] if vcurrent else 'V1'
        self.drives.delete(*self.drives.get_children())
        self.virtuals.delete(*self.virtuals.get_children())
        card = self.runtime.card if self.runtime and self.runtime.card else None
        for drive in range(1, 16):
            mapping = self._mapped_drive_label(card, drive) if card else ''
            values = self._drive_row_values(
                mapping, self._active_drive_entry(card, drive))
            self.drives.insert('', 'end', iid=str(drive), text='D%d:' % drive,
                               values=values)
        for vslot in range(1, 100):
            iid = 'V%d' % vslot
            values = self._slot_row_values(self._virtual_entry(card, vslot))
            self.virtuals.insert('', 'end', iid=iid, text=iid + ':',
                                 values=values)
        if self.drives.exists(selected):
            self.drives.selection_set(selected)
            self.drives.focus(selected)
        if self.virtuals.exists(vselected):
            self.virtuals.selection_set(vselected)
            self.virtuals.focus(vselected)
        self._last_drive_signature = self._drive_signature()
        self._update_mini_lcd()
