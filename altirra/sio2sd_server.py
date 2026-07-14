#!/usr/bin/env python3
"""
sio2sd_server.py - serwer emulacji SIO2SD (firmware 3.3) dla Altirry.

Udostepnia wskazany katalog dysku jako "karte SD" urzadzenia SIO2SD.
Wspolpracuje z sio2sd.atdevice (Altirra Custom Device Server, port 9977).

Uzycie:
    python sio2sd_server.py KATALOG [--id 0-3] [--read-only] [--port 9977] [-v]

API wg http://www.sio2sd.org/commands/ (komendy $00-$27).
"""
import os
import sys
import argparse
import socketserver
import threading
from types import SimpleNamespace

try:
    from deviceserver import DeviceTCPHandler, run_deviceserver
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from deviceserver import DeviceTCPHandler, run_deviceserver

ACK, NAK = 0x41, 0x4E
COMPLETE, ERROR = 0x43, 0x45
FIRMWARE = 0x33          # "3.3"

VALID = set(range(32, 127)) - set(map(ord, '\\/:*?"<>|'))


def clean_name(raw):
    """Nazwa z bufora 39B: zera/spacje z prawej, znaki niepoprawne usuwane."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw[:39]
        raw = raw.split(b'\0')[0]
        s = ''.join(chr(b) for b in raw if b in VALID)
    else:
        s = ''.join(c for c in raw if ord(c) in VALID)
    return s.rstrip(' ')


def mask_match(mask, name):
    """Dopasowanie maski SIO2SD: tylko '*' (reszta doslownie, bez wielkosci liter)."""
    import re
    rx = ''.join('.*' if c == '*' else re.escape(c) for c in mask)
    return re.fullmatch(rx, name, re.IGNORECASE) is not None


class VirtualDisk:
    """Wspolna baza wirtualnych napedow D1-D15."""
    read_only = False
    sector_size = 128

    def total_sectors(self):
        return 720

    def sec_size(self, n):
        return 128 if n <= 3 else self.sector_size

    def read_sector(self, n):
        raise NotImplementedError

    def write_sector(self, n, data):
        return False

    def status(self):
        b0 = 0x10
        if self.sector_size == 256:
            b0 |= 0x20
        if self.read_only:
            b0 |= 0x08
        # bajt 2 = timeout formatowania: $FE jak w XF551 (emulujemy jego
        # protokol high-speed), zamiast $E0 z 1050
        return bytes([b0, 0xFF, 0xFE, 0x00])


class AtrDisk(VirtualDisk):
    """Naped na pliku ATR (odczyt i zapis)."""

    def __init__(self, path, read_only=False):
        self.path = path
        self.read_only = read_only
        f = open(path, 'rb')
        hdr = f.read(16)
        f.close()
        if len(hdr) < 16 or hdr[0] | (hdr[1] << 8) != 0x0296:
            raise ValueError('to nie jest plik ATR')
        self.sector_size = hdr[4] | (hdr[5] << 8)
        if self.sector_size not in (128, 256):
            raise ValueError('nieobslugiwany rozmiar sektora ATR')
        paras = hdr[2] | (hdr[3] << 8) | (hdr[6] << 16)
        data_len = paras * 16
        if self.sector_size == 128:
            self._total = data_len // 128
        else:
            self._total = 3 + max(0, (data_len - 384)) // 256

    def total_sectors(self):
        return self._total

    def _offset(self, n):
        if self.sector_size == 128 or n <= 3:
            return 16 + (n - 1) * 128
        return 16 + 384 + (n - 4) * 256

    def read_sector(self, n):
        if n < 1 or n > self._total:
            return None
        with open(self.path, 'rb') as f:
            f.seek(self._offset(n))
            d = f.read(self.sec_size(n))
        return d.ljust(self.sec_size(n), b'\0')

    def write_sector(self, n, data):
        if self.read_only or n < 1 or n > self._total:
            return False
        with open(self.path, 'r+b') as f:
            f.seek(self._offset(n))
            f.write(data[:self.sec_size(n)])
        return True


def atr_header_write_protected(path):
    try:
        with open(path, 'rb') as f:
            hdr = f.read(8)
    except OSError:
        return False
    return len(hdr) >= 8 and bool(hdr[7] & 1)


class XexDisk(VirtualDisk):
    """Naped rozruchowy z plikiem XEX + bootloaderem xexboot.bin."""
    read_only = True

    def __init__(self, path, loader):
        with open(path, 'rb') as f:
            self.data = f.read()
        if len(loader) != 384:
            raise ValueError('zly xexboot.bin (%d bajtow, oczekiwano 384)' %
                             len(loader))
        boot = bytearray(loader)
        boot[9:12] = min(len(self.data), 0xFFFFFF).to_bytes(3, 'little')
        self.boot = bytes(boot)

    def total_sectors(self):
        return 3 + (len(self.data) + 127) // 128

    def read_sector(self, n):
        if n < 1 or n > self.total_sectors():
            return None
        if n <= 3:
            return self.boot[(n - 1) * 128:n * 128]
        off = (n - 4) * 128
        return self.data[off:off + 128].ljust(128, b'\0')


class RawDisk(VirtualDisk):
    """Zwykly plik jako surowy zrzut sektorow 128B (jak "SD disk")."""

    def __init__(self, path, read_only=False):
        self.path = path
        self.read_only = read_only
        self._total = max(1, (os.path.getsize(path) + 127) // 128)

    def total_sectors(self):
        return self._total

    def read_sector(self, n):
        if n < 1 or n > self._total:
            return None
        with open(self.path, 'rb') as f:
            f.seek((n - 1) * 128)
            return f.read(128).ljust(128, b'\0')

    def write_sector(self, n, data):
        if self.read_only or n < 1 or n > self._total:
            return False
        with open(self.path, 'r+b') as f:
            f.seek((n - 1) * 128)
            f.write(data[:128])
        return True


class EmptyDisk(VirtualDisk):
    """Pusty dysk w pamieci (720 sektorow SD)."""

    def __init__(self):
        self.mem = {}

    def read_sector(self, n):
        if n < 1 or n > 720:
            return None
        return self.mem.get(n, bytes(128))

    def write_sector(self, n, data):
        if n < 1 or n > 720:
            return False
        self.mem[n] = bytes(data[:128]).ljust(128, b'\0')
        return True


def atr_data_length(total_sectors=720, sector_size=128):
    total_sectors = int(total_sectors)
    sector_size = int(sector_size)
    if total_sectors <= 0:
        raise ValueError('liczba sektorow musi byc dodatnia')
    if sector_size == 128:
        return total_sectors * 128
    if sector_size == 256:
        if total_sectors < 3:
            raise ValueError('ATR 256B musi miec co najmniej 3 sektory')
        return 384 + (total_sectors - 3) * 256
    raise ValueError('obslugiwane sa sektory 128 albo 256 bajtow')


def _empty_atr_image(total_sectors=720, sector_size=128):
    data_len = atr_data_length(total_sectors, sector_size)
    paras = data_len // 16
    data = bytearray(16 + data_len)
    data[0:2] = (0x0296).to_bytes(2, 'little')
    data[2:4] = (paras & 0xFFFF).to_bytes(2, 'little')
    data[4:6] = int(sector_size).to_bytes(2, 'little')
    data[6] = (paras >> 16) & 0xFF
    return data


def _atr_sector_size(sector, sector_size):
    return 128 if int(sector) <= 3 else int(sector_size)


def _atr_sector_offset(sector, sector_size):
    sector = int(sector)
    sector_size = int(sector_size)
    if sector_size == 128 or sector <= 3:
        return 16 + (sector - 1) * 128
    return 16 + 384 + (sector - 4) * sector_size


def _write_atr_sector(image, sector, payload, sector_size):
    off = _atr_sector_offset(sector, sector_size)
    size = _atr_sector_size(sector, sector_size)
    image[off:off + size] = bytes(payload[:size]).ljust(size, b'\0')


def write_empty_atr(path, total_sectors=720, sector_size=128):
    image = _empty_atr_image(total_sectors, sector_size)
    with open(path, 'xb') as f:
        f.write(image)


def _mark_bitmap_sector(bitmap, sector, free, offset=0):
    idx = int(sector) - 1
    byte = int(offset) + idx // 8
    bit = 7 - (idx % 8)
    if byte >= len(bitmap):
        return
    if free:
        bitmap[byte] |= 1 << bit
    else:
        bitmap[byte] &= ~(1 << bit)


def _valid_volume_label(label):
    label = (label or '').upper().strip()
    return ''.join(c for c in label if c.isalnum() or c == '_')[:8]


def _write_dos_bitmap(vtoc, bitmap_offset, total_sectors, reserved):
    for sector in range(1, total_sectors + 1):
        _mark_bitmap_sector(vtoc, sector, sector not in reserved,
                            offset=bitmap_offset)


def write_dos2_atr(path, total_sectors=720, sector_size=128):
    total_sectors = int(total_sectors)
    sector_size = int(sector_size)
    if sector_size != 128 or total_sectors != 720:
        raise ValueError('DOS 2.x: obslugiwany jest format SD 90 KB (720 x 128)')
    image = _empty_atr_image(total_sectors, sector_size)
    reserved = set(range(1, 4)) | set(range(360, 369)) | {720}
    free = total_sectors - len([s for s in reserved if s <= total_sectors])
    vtoc = bytearray(128)
    vtoc[0] = 2
    vtoc[1:3] = free.to_bytes(2, 'little')
    _write_dos_bitmap(vtoc, 10, total_sectors, reserved)
    _write_atr_sector(image, 360, vtoc, sector_size)
    with open(path, 'xb') as f:
        f.write(image)


def write_mydos_atr(path, total_sectors=720, sector_size=128):
    total_sectors = int(total_sectors)
    sector_size = int(sector_size)
    if sector_size == 128 and total_sectors != 720:
        raise ValueError('MyDOS 128B: uzyj SD 90 KB albo czystego ATR/SDX')
    if sector_size == 256 and total_sectors > 1792:
        raise ValueError('MyDOS: ta geometria wymaga rozszerzonego VTOC')
    image = _empty_atr_image(total_sectors, sector_size)
    reserved = set(range(1, 4)) | set(range(360, 369))
    free = total_sectors - len([s for s in reserved if s <= total_sectors])
    vtoc_size = _atr_sector_size(360, sector_size)
    vtoc = bytearray(vtoc_size)
    vtoc[0] = 3 if total_sectors > 720 or sector_size == 256 else 2
    vtoc[1:3] = free.to_bytes(2, 'little')
    bitmap_offset = 32 if sector_size == 256 else 10
    _write_dos_bitmap(vtoc, bitmap_offset, total_sectors, reserved)
    _write_atr_sector(image, 360, vtoc, sector_size)
    with open(path, 'xb') as f:
        f.write(image)


def _sdx_template_candidates(total_sectors, sector_size):
    if sector_size != 128:
        return []
    template_name = None
    if total_sectors == 720:
        template_name = 'NEW0001.ATR'
    elif total_sectors == 1040:
        template_name = 'NEW0002.ATR'
    if template_name is None:
        return []
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(project_root, 'dist', 'sd', 'Atari', template_name),
        os.path.join(project_root, 'sd', 'atari', template_name),
        os.path.join(project_root, 'sd', 'Atari', template_name),
    ]
    exe_root = os.path.dirname(os.path.abspath(sys.executable))
    candidates += [
        os.path.join(exe_root, 'sd', 'Atari', template_name),
        os.path.join(exe_root, 'sd', 'atari', template_name),
    ]
    bundle_root = getattr(sys, '_MEIPASS', None)
    if bundle_root:
        candidates += [
            os.path.join(bundle_root, 'sd', 'Atari', template_name),
            os.path.join(bundle_root, 'sd', 'atari', template_name),
        ]
    return candidates


def _apply_sdx_volume_label(image, volume_label):
    label = _valid_volume_label(volume_label)
    if not label:
        return
    image[16 + 22:16 + 30] = label.encode('ascii').ljust(8, b' ')


def _write_sdx_generated_atr(path, total_sectors, sector_size, volume_label=None):
    total_sectors = int(total_sectors)
    sector_size = int(sector_size)
    if sector_size != 128:
        raise ValueError('SDX: generator obsluguje teraz sektory 128B')
    image = _empty_atr_image(total_sectors, sector_size)
    boot = None
    for template in _sdx_template_candidates(total_sectors, sector_size):
        if os.path.isfile(template):
            with open(template, 'rb') as f:
                boot = f.read(16 + 3 * 128)[16:]
            break
    if boot is None:
        for template in _sdx_template_candidates(1040, 128):
            if os.path.isfile(template):
                with open(template, 'rb') as f:
                    boot = f.read(16 + 3 * 128)[16:]
                break
    if boot is None:
        raise ValueError('brak szablonu boot SDX')
    image[16:16 + len(boot)] = boot
    bitmap_sectors = (total_sectors + 511) // 512
    root_sector = 4 + bitmap_sectors
    reserved = set(range(1, 4))
    reserved.update(range(4, 4 + bitmap_sectors))
    reserved.add(root_sector)
    reserved.add(root_sector + 1)
    bitmap = bytearray(bitmap_sectors * 128)
    for sector in range(1, total_sectors + 1):
        _mark_bitmap_sector(bitmap, sector, sector not in reserved)
    for i in range(bitmap_sectors):
        _write_atr_sector(image, 4 + i, bitmap[i * 128:(i + 1) * 128],
                          sector_size)
    root = bytearray(128)
    root[0] = 0x28
    root[3] = 0x17
    root[6:14] = b'MAIN    '
    _write_atr_sector(image, root_sector, root, sector_size)
    s1_offset = 16
    image[s1_offset + 9] = (root_sector - 1) & 0xFF
    image[s1_offset + 11:s1_offset + 13] = total_sectors.to_bytes(2, 'little')
    free = total_sectors - len([s for s in reserved if s <= total_sectors])
    image[s1_offset + 13:s1_offset + 15] = max(0, free).to_bytes(2, 'little')
    image[s1_offset + 20:s1_offset + 22] = (
        root_sector + 1).to_bytes(2, 'little')
    _apply_sdx_volume_label(image, volume_label)
    with open(path, 'xb') as f:
        f.write(image)


def write_sdx_atr(path, total_sectors=720, sector_size=128, volume_label=None):
    total_sectors = int(total_sectors)
    sector_size = int(sector_size)
    for template in _sdx_template_candidates(total_sectors, sector_size):
        if os.path.isfile(template):
            with open(template, 'rb') as src:
                image = bytearray(src.read())
            _apply_sdx_volume_label(image, volume_label)
            with open(path, 'xb') as dst:
                dst.write(image)
            return
    _write_sdx_generated_atr(path, total_sectors, sector_size,
                             volume_label=volume_label)


def make_disk(path, loader, read_only=False, honor_atr_write_protect=False):
    """Dobierz typ napedu po zawartosci/rozszerzeniu pliku."""
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, 'rb') as f:
            hdr = f.read(2)
    except OSError:
        hdr = b''
    if ext == '.atr' or hdr == b'\x96\x02':
        if honor_atr_write_protect and atr_header_write_protected(path):
            read_only = True
        return AtrDisk(path, read_only)
    if ext in ('.xex', '.com', '.exe'):
        return XexDisk(path, loader)
    if os.path.getsize(path) <= 92160:
        return RawDisk(path, read_only)
    raise ValueError('nie umiem zamontowac: ' + path)


def runtime_file_candidates(name):
    """Mozliwe lokalizacje plikow pomocniczych w zrodlach i w EXE."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, name),
        os.path.join(here, 'altirra', name),
    ]
    bundle_root = getattr(sys, '_MEIPASS', None)
    if bundle_root:
        candidates.extend([
            os.path.join(bundle_root, 'altirra', name),
            os.path.join(bundle_root, name),
        ])
    if getattr(sys, 'frozen', False):
        exe_root = os.path.dirname(os.path.abspath(sys.executable))
        candidates.extend([
            os.path.join(exe_root, 'altirra', name),
            os.path.join(exe_root, name),
        ])
    cwd = os.getcwd()
    candidates.extend([
        os.path.join(cwd, 'altirra', name),
        os.path.join(cwd, name),
    ])

    out = []
    seen = set()
    for path in candidates:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        out.append(path)
    return out


def load_xex_loader():
    """Wczytaj poprawny xexboot.bin, omijaj puste/bledne kopie."""
    first_bad = None
    for path in runtime_file_candidates('xexboot.bin'):
        if not os.path.exists(path):
            continue
        try:
            data = open(path, 'rb').read()
        except OSError:
            continue
        if len(data) == 384:
            return data, path
        if first_bad is None:
            first_bad = (path, len(data))
    if first_bad:
        return b'', '%s (%d bajtow)' % first_bad
    return b'', None


class SIO2SDCard:
    """Emulacja karty SD urzadzenia SIO2SD na prawdziwym katalogu."""

    # Katalog bazowy karty to podkatalog 'Atari' udostepnianego katalogu -
    # tak zachowuje sie oryginalne SIO2SD (natywne API plikowe operuje w /Atari;
    # z SDX 'SDC1:' + DIR od razu pokazuje jego zawartosc). Tworzony gdy brak.
    BASEDIR = 'Atari'
    CFG_NAME = 'SIO2SD.CFG'
    SELECTOR_NAME = 'SIO2SD.XEX'
    SELECTOR_ATR = 'Sio2SDBootLoaderCfgTools.atr'
    CFG_SIZE = 0x1D00
    CFG_ENTRY_OFFSET = 0x40
    CFG_ENTRY_SIZE = 0x40
    CFG_DRIVE_SLOTS = 15
    CFG_VIRTUAL_SLOTS = 99
    CFG_SLOT_COUNT = CFG_DRIVE_SLOTS + CFG_VIRTUAL_SLOTS

    def __init__(self, root, devid=0, read_only=False, log=print,
                 cfg_selector=False, config=None, device_enabled=True,
                 topdrive_turbo=True):
        mount = os.path.realpath(root)
        if not os.path.isdir(mount):
            raise ValueError('brak katalogu: ' + root)
        self.mount_root = mount
        self.root = os.path.realpath(os.path.join(mount, self.BASEDIR))
        if not os.path.isdir(self.root):
            os.makedirs(self.root, exist_ok=True)
            log('utworzono katalog bazowy karty: ' + self.root)
        self.read_only = read_only
        self.log = log
        self.device_enabled = bool(device_enabled)
        self.topdrive_turbo = bool(topdrive_turbo)
        self.cfg_selector = bool(cfg_selector)
        self._cfg_selector_saved_drives = None
        self._cfg_selector_saved_vmap = None
        self._mapping_fallback_warned = set()
        self.ids = {}
        self.paths = {}
        self.next_id = 1
        self.oid(self.root)
        # domyslna konfiguracja (por. dokumentacja $12/$13)
        self.cfg = bytearray(16)
        self.cfg[0] = 6          # hsindex
        self.cfg[1] = 40         # hsindex turbo 7-bit
        self.cfg[4] = devid
        self.cfg[5] = 1          # ochrona zapisu wg flagi ATR
        if config is not None:
            self.set_config(config)
        self.vmap = bytearray(range(15))
        self.changed = 0         # 2/3/4 - flagi "cos sie zmienilo"
        self.loader, self.loader_path = load_xex_loader()
        if len(self.loader) != 384:
            detail = self.loader_path or 'nie znaleziono pliku'
            self.log('uwaga: brak poprawnego xexboot.bin (%s)' % detail)
        self.drives = {}         # numer napedu (1-15) -> (VirtualDisk, entry54)
        self.vslots = {}         # numer slotu V (1-99) -> (VirtualDisk, entry54)
        self.reset()
        self.cfg_path = self._find_cfg_path()
        self.cfg_blob = self._default_cfg_blob()
        self._load_cfg_file()

    # ------------------------------------------------------------- narzedzia
    def reset(self):
        self.cwd = self.root
        self.mask = '*'
        self.masktypes = 3
        self.enum = []
        self.enumi = 0
        self.enum_back = False
        self.openf = None
        self.openpath = None
        self.pending = None

    def get_config(self):
        return bytes(self.cfg)

    def set_config(self, config):
        self.cfg = bytearray(bytes(config)[:16].ljust(16, b'\0'))
        self._apply_atr_write_protect_config()

    def set_device_enabled(self, enabled):
        self.device_enabled = bool(enabled)
        self.pending = None

    def set_topdrive_turbo(self, enabled):
        self.topdrive_turbo = bool(enabled)
        self.pending = None

    def _honor_atr_write_protect(self):
        return bool(self.cfg[5] & 1)

    def _base_disk_read_only(self, read_only=None):
        return self.read_only if read_only is None else bool(read_only)

    def _disk_read_only(self, path, read_only=None):
        ro = self._base_disk_read_only(read_only)
        if not ro and self._honor_atr_write_protect():
            ro = atr_header_write_protected(path)
        return ro

    def _apply_atr_write_protect_config(self):
        if not hasattr(self, 'drives'):
            return
        for disk, _entry in list(self.drives.values()) + list(self.vslots.values()):
            if isinstance(disk, AtrDisk):
                disk.read_only = self._disk_read_only(
                    disk.path, getattr(disk, '_base_read_only', None))

    def _find_cfg_path(self):
        for name in (self.CFG_NAME, self.CFG_NAME.lower()):
            path = os.path.join(self.mount_root, name)
            if os.path.exists(path):
                return path
        return os.path.join(self.mount_root, self.CFG_NAME)

    def _default_cfg_blob(self):
        data = bytearray(self.CFG_SIZE)
        data[0] = 0xA5
        data[1:16] = bytes(range(15))
        data[16] = 14
        for idx in range((self.CFG_SIZE - self.CFG_ENTRY_OFFSET) //
                         self.CFG_ENTRY_SIZE):
            off = self.CFG_ENTRY_OFFSET + idx * self.CFG_ENTRY_SIZE
            self._write_cfg_slot(data, off, ' - OFF -', 0, None)
        return data

    def _write_cfg_slot(self, data, off, name, typ, ent):
        block = bytearray(self.CFG_ENTRY_SIZE)
        nb = (name or ' - OFF -').encode('ascii', 'replace')[:39]
        block[0:len(nb)] = nb
        for i in range(len(nb), 39):
            block[i] = 32
        block[39] = typ
        if ent:
            block[40:54] = bytes(ent[40:54]).ljust(14, b'\0')[:14]
        data[off:off + self.CFG_ENTRY_SIZE] = block

    def _load_cfg_file(self):
        if not os.path.exists(self.cfg_path):
            return
        try:
            with open(self.cfg_path, 'rb') as f:
                raw = f.read()
        except OSError as exc:
            self.log('SIO2SD.CFG: nie mozna odczytac: %s' % exc)
            return
        if len(raw) < self.CFG_ENTRY_OFFSET + 15 * self.CFG_ENTRY_SIZE:
            self.log('SIO2SD.CFG: plik za krotki, pomijam')
            return
        self.cfg_blob = bytearray(raw[:self.CFG_SIZE].ljust(self.CFG_SIZE,
                                                            b'\0'))
        if self.cfg_blob[0] == 0xA5:
            self.vmap = bytearray(self.cfg_blob[1:16])
        restored = 0
        for slot in range(self.CFG_SLOT_COUNT):
            off = self.CFG_ENTRY_OFFSET + slot * self.CFG_ENTRY_SIZE
            block = self.cfg_blob[off:off + self.CFG_ENTRY_SIZE]
            typ = block[39]
            name = clean_name(block[:39]).strip()
            if typ == 3:
                self._set_slot_empty(slot, persist=False,
                                     reset_mapping=False, quiet=True)
                restored += 1
            elif typ == 2 and name and name != '- OFF -':
                try:
                    path = self._find_cfg_file_name(name)
                    self._set_slot_file(slot, path, bytes(block[:54]),
                                        persist=False, reset_mapping=False,
                                        quiet=True)
                    restored += 1
                except Exception as exc:
                    self.log('SIO2SD.CFG: nie podpieto %s:%s (%s)' %
                             (self._slot_name(slot), name, exc))
        self.changed = 0
        self.log('SIO2SD.CFG: odczytano %s (%d slotow)' %
                 (self.cfg_path, restored))

    def _save_cfg_file(self):
        if self.read_only:
            return
        data = bytearray(self.cfg_blob[:self.CFG_SIZE].ljust(self.CFG_SIZE,
                                                             b'\0'))
        data[0] = 0xA5
        data[1:16] = bytes(self.vmap[:15]).ljust(15, b'\0')
        for slot in range(self.CFG_SLOT_COUNT):
            off = self.CFG_ENTRY_OFFSET + slot * self.CFG_ENTRY_SIZE
            ent = self._slot_entry(slot)
            if ent is None:
                self._write_cfg_slot(data, off, ' - OFF -', 0, None)
                continue
            disk, entry = ent
            if isinstance(disk, EmptyDisk):
                self._write_cfg_slot(data, off, '=EMPTY=', 3, entry)
            else:
                name = clean_name(entry[:39]) or ' - OFF -'
                self._write_cfg_slot(data, off, name, 2, entry)
        try:
            with open(self.cfg_path, 'wb') as f:
                f.write(data)
            self.cfg_blob = data
        except OSError as exc:
            self.log('SIO2SD.CFG: nie mozna zapisac: %s' % exc)

    def _find_cfg_file_name(self, name):
        names = [name]
        if name.startswith('[') and name.endswith(']'):
            names.append(name[1:-1])
        for candidate in names:
            try:
                return self.find_file(candidate)
            except ValueError:
                pass
        return self.find_file(name)

    def _slot_name(self, slot):
        if 0 <= slot < self.CFG_DRIVE_SLOTS:
            return 'D%d' % (slot + 1)
        if slot < self.CFG_SLOT_COUNT:
            return 'V%d' % (slot - self.CFG_DRIVE_SLOTS + 1)
        return '#%d' % slot

    def _slot_entry(self, slot):
        if 0 <= slot < self.CFG_DRIVE_SLOTS:
            return self.drives.get(slot + 1)
        if self.CFG_DRIVE_SLOTS <= slot < self.CFG_SLOT_COUNT:
            return self.vslots.get(slot - self.CFG_DRIVE_SLOTS + 1)
        return None

    def _store_slot_entry(self, slot, entry):
        if 0 <= slot < self.CFG_DRIVE_SLOTS:
            if entry is None:
                self.drives.pop(slot + 1, None)
            else:
                self.drives[slot + 1] = entry
            return True
        if self.CFG_DRIVE_SLOTS <= slot < self.CFG_SLOT_COUNT:
            vslot = slot - self.CFG_DRIVE_SLOTS + 1
            if entry is None:
                self.vslots.pop(vslot, None)
            else:
                self.vslots[vslot] = entry
            return True
        return False

    def _slot_from_api_number(self, number):
        slot = int(number) - 1
        if 0 <= slot < self.CFG_SLOT_COUNT:
            return slot
        return None

    def _slot_for_drive(self, drive):
        slot = self.vmap[drive - 1] if 1 <= drive <= 15 else 0xFF
        if 0 <= slot < self.CFG_SLOT_COUNT:
            return slot
        return drive - 1

    def _entry_for_drive(self, drive):
        slot = self._slot_for_drive(drive)
        ent = self._slot_entry(slot)
        if ent is not None:
            return ent
        physical = drive - 1
        if slot != physical:
            ent = self._slot_entry(physical)
            if ent is not None:
                key = (drive, slot)
                if key not in self._mapping_fallback_warned:
                    self._mapping_fallback_warned.add(key)
                    self.log('D%d: mapowanie -> %s jest puste, uzywam D%d' %
                             (drive, self._slot_name(slot), drive))
                return ent
        return None

    def set_drive_mapping(self, drive, slot, persist=True):
        if not (1 <= drive <= self.CFG_DRIVE_SLOTS):
            raise ValueError('numer napedu D1-D15')
        if not (0 <= slot < self.CFG_SLOT_COUNT):
            raise ValueError('numer slotu poza zakresem')
        self.vmap[drive - 1] = slot
        self._mapping_fallback_warned.discard((drive, slot))
        self.changed = 3
        if persist:
            self._save_cfg_file()
        self.log('D%d: mapowanie -> %s' % (drive, self._slot_name(slot)))

    def reset_drive_mapping(self, drive, persist=True):
        if not (1 <= drive <= self.CFG_DRIVE_SLOTS):
            raise ValueError('numer napedu D1-D15')
        self.set_drive_mapping(drive, drive - 1, persist=persist)

    def map_drive_to_virtual(self, drive, vslot, persist=True):
        if not (1 <= vslot <= self.CFG_VIRTUAL_SLOTS):
            raise ValueError('numer slotu V1-V99')
        self.set_drive_mapping(drive, self.CFG_DRIVE_SLOTS + vslot - 1,
                               persist=persist)

    def swap_slots(self, slot_a, slot_b, persist=True):
        if not (0 <= slot_a < self.CFG_SLOT_COUNT):
            raise ValueError('pierwszy slot poza zakresem')
        if not (0 <= slot_b < self.CFG_SLOT_COUNT):
            raise ValueError('drugi slot poza zakresem')
        if slot_a == slot_b:
            return
        ent_a = self._slot_entry(slot_a)
        ent_b = self._slot_entry(slot_b)
        self._store_slot_entry(slot_a, ent_b)
        self._store_slot_entry(slot_b, ent_a)
        self._mapping_fallback_warned.clear()
        self.changed = 3
        if persist:
            self._save_cfg_file()
        self.log('%s <-> %s: zamieniono sloty' %
                 (self._slot_name(slot_a), self._slot_name(slot_b)))

    def swap_drive_with_virtual(self, drive, vslot, persist=True):
        if not (1 <= drive <= self.CFG_DRIVE_SLOTS):
            raise ValueError('numer napedu D1-D15')
        if not (1 <= vslot <= self.CFG_VIRTUAL_SLOTS):
            raise ValueError('numer slotu V1-V99')
        self.swap_slots(drive - 1, self.CFG_DRIVE_SLOTS + vslot - 1,
                        persist=persist)

    def _set_slot_file(self, slot, path, entry=None, persist=True,
                       reset_mapping=True, quiet=False, read_only=None):
        if not (0 <= slot < self.CFG_SLOT_COUNT):
            raise ValueError('numer slotu poza zakresem')
        base_ro = self._base_disk_read_only(read_only)
        ro = self._disk_read_only(path, read_only)
        disk = make_disk(path, self.loader, ro,
                         honor_atr_write_protect=self._honor_atr_write_protect())
        if isinstance(disk, AtrDisk):
            disk._base_read_only = base_ro
        if entry is None:
            name = os.path.basename(path)[:39]
            if self.inroot(path) and os.path.isfile(path):
                entry = self.entry54(name, 2, path)
            else:
                e = bytearray(54)
                nb = name.encode('ascii', 'replace')[:39]
                e[0:len(nb)] = nb
                e[39] = 2
                entry = bytes(e)
        else:
            entry = bytes(entry[:54]).ljust(54, b'\0')
        self._store_slot_entry(slot, (disk, entry))
        self._mapping_fallback_warned.clear()
        if reset_mapping and slot < self.CFG_DRIVE_SLOTS:
            self.vmap[slot] = slot
        self.changed = 3
        if persist:
            self._save_cfg_file()
        if not quiet:
            name = clean_name(entry[:39]) or os.path.basename(path)[:39]
            self.log('%s: <- %s (%s, %d sektorow%s)' % (
                self._slot_name(slot), name, type(disk).__name__,
                disk.total_sectors(), ', RO' if disk.read_only else ''))
            if slot < self.CFG_DRIVE_SLOTS:
                self.log('   uwaga: slot %s: w Altirze (File > Disk Drives)'
                         ' musi byc w trybie Off - pusty slot R/O tez'
                         ' odpowiada na szynie i wychodza bledy 139/143' %
                         self._slot_name(slot))

    def _set_slot_empty(self, slot, persist=True, reset_mapping=True,
                        quiet=False):
        if not (0 <= slot < self.CFG_SLOT_COUNT):
            raise ValueError('numer slotu poza zakresem')
        e = bytearray(54)
        e[39] = 3
        self._store_slot_entry(slot, (EmptyDisk(), bytes(e)))
        self._mapping_fallback_warned.clear()
        if reset_mapping and slot < self.CFG_DRIVE_SLOTS:
            self.vmap[slot] = slot
        self.changed = 3
        if persist:
            self._save_cfg_file()
        if not quiet:
            self.log('%s: <- pusty dysk' % self._slot_name(slot))

    def _clear_slot(self, slot, persist=True, reset_mapping=True):
        if not (0 <= slot < self.CFG_SLOT_COUNT):
            return
        if self._store_slot_entry(slot, None):
            self._mapping_fallback_warned.clear()
            if reset_mapping and slot < self.CFG_DRIVE_SLOTS:
                self.vmap[slot] = slot
            self.changed = 3
            if persist:
                self._save_cfg_file()
            self.log('%s: odlaczony' % self._slot_name(slot))

    def set_cfg_selector(self, enabled):
        enabled = bool(enabled)
        if self.cfg_selector == enabled:
            return
        self.cfg_selector = enabled
        if not enabled and self._cfg_selector_saved_drives is not None:
            self.drives = self._cfg_selector_saved_drives
            self._cfg_selector_saved_drives = None
            if self._cfg_selector_saved_vmap is not None:
                self.vmap = self._cfg_selector_saved_vmap
                self._cfg_selector_saved_vmap = None
            self.changed = 3
            self.log('CFG MODE: przywrocono mapowanie napedow sprzed wybieraczki')

    def cold_reset(self):
        self.reset()
        if self.cfg_selector:
            self._boot_cfg_selector()

    def _boot_cfg_selector(self):
        path = self._find_selector_file()
        if not path:
            self.log('CFG MODE: brak %s w glownym katalogu karty' %
                     self.SELECTOR_NAME)
            return False
        if self._cfg_selector_saved_drives is None:
            self._cfg_selector_saved_drives = dict(self.drives)
            self._cfg_selector_saved_vmap = bytearray(self.vmap)
        try:
            self.mount(1, path, read_only=True, persist=False, quiet=True)
        except Exception as exc:
            self.log('CFG MODE: nie mozna uruchomic wybieraczki: %s' % exc)
            return False
        self.changed = 3
        self.log('CFG MODE: D1: <- %s' % path)
        return True

    def _find_selector_file(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(self.mount_root, self.SELECTOR_NAME),
            os.path.join(self.root, self.SELECTOR_NAME),
            os.path.join(self.mount_root, self.SELECTOR_ATR),
            os.path.join(project_root, 'Configurator_35', self.SELECTOR_ATR),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    def oid(self, path):
        path = os.path.realpath(path)
        if path not in self.ids:
            self.ids[path] = self.next_id
            self.paths[self.next_id] = path
            self.next_id += 1
        return self.ids[path]

    def inroot(self, path):
        rp = os.path.normcase(os.path.realpath(path))
        root = os.path.normcase(self.root)
        return rp == root or rp.startswith(root + os.sep)

    def listing(self, base=None):
        """Wpisy katalogu: podkatalogi, potem pliki, alfabetycznie."""
        base = base or self.cwd
        try:
            names = os.listdir(base)
        except OSError:
            return []
        out = []
        for n in sorted(names, key=str.lower):
            if clean_name(n) != n or not n or len(n) > 39:
                continue         # nazwy spoza zakresu ASCII 32-126 pomijamy
            p = os.path.join(base, n)
            t = 1 if os.path.isdir(p) else 2
            out.append((n, t, p))
        out.sort(key=lambda e: (e[1] != 1, e[0].lower()))
        return out

    def matching(self, base=None):
        return [e for e in self.listing(base)
                if (e[1] & self.masktypes) and mask_match(self.mask, e[0])]

    def entry54(self, name, typ, path):
        e = bytearray(54)
        nb = name.encode('ascii', 'replace')[:39]
        e[0:len(nb)] = nb
        e[39] = typ
        size = os.path.getsize(path) if typ == 2 else 0
        i = self.oid(path)
        e[40:44] = i.to_bytes(4, 'little')
        e[44:48] = min(size, 0xFFFFFFFF).to_bytes(4, 'little')
        e[48:52] = i.to_bytes(4, 'little')
        return bytes(e)

    def path_from54(self, data):
        i = int.from_bytes(bytes(data[48:52]), 'little')
        p = self.paths.get(i)
        if p and os.path.exists(p) and self.inroot(p):
            return p
        return None

    # ------------------------------------------------------------- napedy
    def find_file(self, name):
        """Znajdz plik do zamontowania: sciezka bezwzgledna, wzgledem
        biezacego katalogu karty, wzgledem korzenia, wzgledem CWD procesu,
        a na koncu szukaj nazwy w calym drzewie karty (bez wielkosci liter)."""
        if os.path.isabs(name):
            return name
        for base in (self.cwd, self.root, self.mount_root, os.getcwd()):
            p = os.path.join(base, name)
            if os.path.isfile(p):
                return p
        want = os.path.basename(name).lower()
        hits = []
        for base, dirs, files in os.walk(self.root):
            dirs.sort()
            hits += [os.path.join(base, f) for f in sorted(files)
                     if f.lower() == want]
        if len(hits) == 1:
            return hits[0]
        if hits:
            raise ValueError('niejednoznaczna nazwa %r:\n  %s' %
                             (name, '\n  '.join(hits)))
        raise ValueError('nie znaleziono pliku %r na karcie (%s)' %
                         (name, self.root))

    def _next_new_atr_name(self):
        for i in range(1, 10000):
            name = 'NEW%04d.ATR' % i
            if not os.path.exists(os.path.join(self.root, name)):
                return name
        raise ValueError('brak wolnej nazwy NEWxxxx.ATR')

    def create_empty_atr(self, name=None, total_sectors=720, sector_size=128,
                         filesystem='blank', volume_label=None):
        if name is None:
            name = self._next_new_atr_name()
        name = os.path.basename(str(name).strip())
        if not name:
            raise ValueError('brak nazwy ATR')
        if os.path.splitext(name)[1] == '':
            name += '.ATR'
        if clean_name(name) != name:
            raise ValueError('nazwa ATR zawiera niedozwolone znaki')
        path = os.path.join(self.root, name)
        fs = (filesystem or 'blank').lower()
        if fs in ('blank', 'raw', 'czysty'):
            write_empty_atr(path, total_sectors=total_sectors,
                            sector_size=sector_size)
        elif fs in ('dos2', 'dos2x'):
            write_dos2_atr(path, total_sectors=total_sectors,
                           sector_size=sector_size)
        elif fs == 'mydos':
            write_mydos_atr(path, total_sectors=total_sectors,
                            sector_size=sector_size)
        elif fs == 'sdx':
            write_sdx_atr(path, total_sectors=total_sectors,
                          sector_size=sector_size,
                          volume_label=volume_label)
        else:
            raise ValueError('nieznany system plikow ATR: %s' % filesystem)
        self.log('utworzono pusty ATR: %s' % name)
        return path

    def mount(self, drive, path, read_only=None, persist=True, quiet=False,
              reset_mapping=True):
        """Zamontuj plik (ATR/XEX/inny) jako Dn:. Zwraca opis albo rzuca."""
        if not (1 <= drive <= 15):
            raise ValueError('numer napedu 1-15')
        name = os.path.basename(path)[:39]
        self._set_slot_file(drive - 1, path, persist=persist, quiet=quiet,
                            read_only=read_only,
                            reset_mapping=reset_mapping)
        return name

    def mount_empty(self, drive, persist=True, reset_mapping=True):
        if not (1 <= drive <= 15):
            raise ValueError('numer napedu 1-15')
        self._set_slot_empty(drive - 1, persist=persist,
                             reset_mapping=reset_mapping)

    def umount(self, drive, persist=True, reset_mapping=True):
        self._clear_slot(drive - 1, persist=persist,
                         reset_mapping=reset_mapping)

    def mount_virtual(self, vslot, path, read_only=None, persist=True,
                      quiet=False):
        if not (1 <= vslot <= self.CFG_VIRTUAL_SLOTS):
            raise ValueError('numer slotu V1-V99')
        name = os.path.basename(path)[:39]
        self._set_slot_file(self.CFG_DRIVE_SLOTS + vslot - 1, path,
                            persist=persist, quiet=quiet,
                            read_only=read_only, reset_mapping=False)
        return name

    def mount_empty_virtual(self, vslot, persist=True):
        if not (1 <= vslot <= self.CFG_VIRTUAL_SLOTS):
            raise ValueError('numer slotu V1-V99')
        self._set_slot_empty(self.CFG_DRIVE_SLOTS + vslot - 1,
                             persist=persist, reset_mapping=False)

    def umount_virtual(self, vslot, persist=True):
        if not (1 <= vslot <= self.CFG_VIRTUAL_SLOTS):
            raise ValueError('numer slotu V1-V99')
        self._clear_slot(self.CFG_DRIVE_SLOTS + vslot - 1,
                         persist=persist, reset_mapping=False)

    def drive_cmd(self, drive, cmd, aux1, aux2, payload=b''):
        """Komendy sektorowe emulowanego napedu. (status, dane)"""
        ent = self._entry_for_drive(drive)
        if not ent:
            return 0, b''            # brak napedu -> cisza na szynie
        disk, _ = ent
        sec = aux1 | (aux2 << 8)
        if cmd == 0x53:
            return 1, disk.status()
        if cmd == 0x52:
            d = disk.read_sector(sec)
            return (1, d) if d is not None else (139, b'')
        if cmd in (0x50, 0x57):
            if disk.read_only:
                return 139, b''
            return (1, b'') if disk.write_sector(sec, payload) else (139, b'')
        if cmd == 0x4E:
            spt = 18 if disk.sector_size == 128 else 18
            total = disk.total_sectors()
            tracks = 40
            percom = bytes([tracks, 1, (total // tracks) >> 8,
                            (total // tracks) & 0xFF, 0,
                            4 if disk.sector_size == 256 else 0,
                            disk.sector_size >> 8, disk.sector_size & 0xFF,
                            0xFF, 0, 0, 0])
            return 1, percom
        return 139, b''              # format itp. -> NAK

    def drive_spec(self, cmd, aux1, aux2, drive):
        """(mode, len) dla komend napedu; None = nieznana."""
        ent = self._entry_for_drive(drive)
        secsize = 128
        if ent:
            sec = aux1 | (aux2 << 8)
            secsize = ent[0].sec_size(sec if sec else 1)
        table = {
            0x53: (1, 4),
            0x52: (1, secsize),
            0x50: (2, secsize),
            0x57: (2, secsize),
            0x4E: (1, 12),
        }
        return table.get(cmd, (None, 0))

    # ---------------------------------------------------------------- API
    def api(self, cmd, aux1, aux2, payload=b''):
        """Wykonaj komende API. Zwraca (status, dane_wyjsciowe).
        status: 1 = OK, 139 = NAK (nieznana komenda / blad)."""
        try:
            return self._api(cmd, aux1, aux2, payload)
        except OSError as e:
            self.log('OSError: %s' % e)
            return 139, b''

    def _api(self, cmd, aux1, aux2, payload):
        if cmd == 0x00:
            st = self.changed if self.changed else 1
            self.changed = 0
            return 1, bytes([st])
        if cmd == 0x11:
            return 1, bytes([FIRMWARE])
        if cmd == 0x09:
            m = clean_name(bytes(payload[:16]).split(b'\0')[0])
            self.mask = m if m else '*'
            self.masktypes = aux1 if aux1 in (1, 2, 3) else 3
            return 1, b''
        if cmd == 0x0A:
            return 1, len(self.matching()).to_bytes(2, 'little')
        if cmd == 0x04:
            n = max(1, min(4, aux1))
            if aux2 & 1:
                self.enum = self.matching()
                self.enum_back = bool(aux2 & 2)
                self.enumi = len(self.enum) - 1 if self.enum_back else 0
            out = b''
            for _ in range(n):
                if 0 <= self.enumi < len(self.enum):
                    name, typ, path = self.enum[self.enumi]
                    out += self.entry54(name, typ, path)
                    self.enumi += -1 if self.enum_back else 1
                else:
                    out += bytes(54)
            return 1, out
        if cmd == 0x05:
            p = self.path_from54(payload)
            if not p or not os.path.isdir(p):
                return 139, b''
            self.cwd = p
            self.changed = 4
            return 1, b''
        if cmd == 0x06:
            if self.cwd != self.root:
                self.cwd = os.path.dirname(self.cwd)
            self.changed = 4
            return 1, b''
        if cmd == 0x07:
            self.cwd = self.root
            self.changed = 4
            return 1, b''
        if cmd == 0x08:
            name = '' if self.cwd == self.root else os.path.basename(self.cwd)
            return 1, self.entry54(name, 1, self.cwd)
        if cmd == 0x0B:
            if self.read_only:
                return 139, b''
            name = clean_name(bytes(payload[:39]))
            if not name:
                return 139, b''
            p = os.path.join(self.cwd, name)
            if os.path.exists(p):
                return 139, b''
            if aux1 == 1:
                os.mkdir(p)
            elif aux1 == 2:
                open(p, 'wb').close()
            else:
                return 139, b''
            self.changed = 4
            return 1, b''
        if cmd == 0x0C:
            if self.read_only:
                return 139, b''
            p = self.path_from54(payload)
            if not p or p == self.root:
                return 139, b''
            if os.path.isdir(p):
                if os.listdir(p):
                    return 139, b''
                os.rmdir(p)
            else:
                if self.openpath == p:
                    self._close()
                os.remove(p)
            self.changed = 4
            return 1, b''
        if cmd == 0x0D:
            if self.read_only:
                return 139, b''
            p = self.path_from54(payload)
            newname = clean_name(bytes(payload[:39]))
            if not p or not newname or p == self.root:
                return 139, b''
            np = os.path.join(os.path.dirname(p), newname)
            if os.path.exists(np):
                return 139, b''
            if self.openpath == p:
                self._close()
            os.rename(p, np)
            # zachowaj identyfikator obiektu
            i = self.ids.pop(os.path.realpath(p))
            self.ids[os.path.realpath(np)] = i
            self.paths[i] = os.path.realpath(np)
            self.changed = 4
            return 1, b''
        if cmd == 0x0E:
            for base, dirs, files in os.walk(self.root):
                for e in self.listing(base):
                    if (e[1] & self.masktypes) and mask_match(self.mask, e[0]):
                        return 1, self.entry54(*e)
            return 139, b''
        if cmd == 0x10:
            txt = clean_name(bytes(payload[:40]))
            self.log('LCD[%d]: %s' % (aux1, txt))
            return 1, b''
        if cmd == 0x12:
            return 1, bytes(self.cfg)
        if cmd == 0x13:
            self.set_config(payload)
            self._save_cfg_file()
            return 1, b''
        if cmd == 0x14:
            return 1, bytes(self.vmap)
        if cmd == 0x15:
            self.vmap = bytearray(
                min(b, self.CFG_SLOT_COUNT - 1)
                for b in payload[:15].ljust(15, b'\0'))
            self._save_cfg_file()
            return 1, b''
        if cmd in (0x1E, 0x1F):
            return 1, bytes([self.cfg[0] if cmd == 0x1E else self.cfg[1]])
        if cmd == 0x01:
            n = max(1, min(4, aux2))
            out = b''
            for i in range(n):
                slot = self._slot_from_api_number(aux1 + i)
                ent = self._slot_entry(slot) if slot is not None else None
                out += ent[1] if ent else bytes(54)
            return 1, out
        if cmd == 0x02:
            n = max(1, min(4, aux2))
            for i in range(n):
                slot = self._slot_from_api_number(aux1 + i)
                e = bytes(payload[i * 54:(i + 1) * 54]).ljust(54, b'\0')
                typ = e[39]
                if slot is None:
                    continue             # specjalne/nieznane sloty: ignoruj
                if typ == 0:
                    self._clear_slot(slot)
                elif typ == 3:
                    self._set_slot_empty(slot)
                elif typ == 2:
                    p = self.path_from54(e)
                    if not p or not os.path.isfile(p):
                        return 139, b''
                    try:
                        self._set_slot_file(slot, p, e)
                    except (ValueError, OSError) as ex:
                        self.log('mount: %s' % ex)
                        return 139, b''
                else:
                    return 139, b''
            self.changed = 3
            return 1, b''
        if cmd == 0x03:
            n = max(1, min(100, aux2))
            for i in range(n):
                slot = self._slot_from_api_number(aux1 + i)
                if slot is not None:
                    self._clear_slot(slot)
            self.changed = 3
            return 1, b''
        # --- operacje plikowe ---
        if cmd == 0x20:
            name = clean_name(bytes(payload[:39]))
            if not name:
                return 139, b''
            base = self.cwd if aux1 & 1 else self.root
            hit = None
            for n, t, p in self.listing(base):
                if t == 2 and n.lower() == name.lower():
                    hit = p
                    break
            if hit is None:
                if (aux1 & 2) or self.read_only:
                    return 139, b''
                hit = os.path.join(base, name)
                open(hit, 'wb').close()
                self.changed = 4
            return self._open(hit)
        if cmd == 0x21:
            p = self.path_from54(payload)
            if not p or not os.path.isfile(p):
                return 139, b''
            return self._open(p)
        if cmd == 0x22:
            if not self.openf:
                return 139, b''
            return 1, self.openf.tell().to_bytes(3, 'little')
        if cmd == 0x23:
            if not self.openf:
                return 139, b''
            self.openf.seek(int.from_bytes(bytes(payload[:3]), 'little'))
            return 1, b''
        if cmd == 0x24:
            if not self.openf:
                return 139, b''
            n = aux1 if aux1 else 256
            data = self.openf.read(n)
            return 1, data + bytes(n - len(data))
        if cmd == 0x25:
            if not self.openf or self.read_only:
                return 139, b''
            pos = self.openf.tell()
            size = os.path.getsize(self.openpath)
            if pos > size:
                self.openf.seek(size)
                self.openf.write(bytes(pos - size))
            self.openf.write(payload)
            self.openf.flush()
            return 1, b''
        if cmd == 0x26:
            if not self.openf:
                return 139, b''
            size = min(os.path.getsize(self.openpath), 0xFFFFFF)
            return 1, size.to_bytes(3, 'little')
        if cmd == 0x27:
            if not self.openf or self.read_only:
                return 139, b''
            n = int.from_bytes(bytes(payload[:3]), 'little')
            self.openf.truncate(n)
            self.openf.flush()
            return 1, b''
        return 139, b''

    def _open(self, path):
        self._close()
        mode = 'rb' if self.read_only else 'r+b'
        self.openf = open(path, mode)
        self.openpath = os.path.realpath(path)
        return 1, b''

    def _close(self):
        if self.openf:
            try:
                self.openf.close()
            except OSError:
                pass
        self.openf = None
        self.openpath = None

    # --------------------------------------------------- warstwa SIO/skrypt
    # dlugosci ramek danych: (kierunek, dlugosc) wg dokumentacji
    def frame_spec(self, cmd, aux1, aux2):
        """Zwraca (mode, len): mode 0=bez danych, 1=odczyt, 2=zapis."""
        R, W, N = 1, 2, 0
        table = {
            0x00: (R, 1), 0x01: (R, 54 * max(1, min(4, aux2))),
            0x02: (W, 54 * max(1, min(4, aux2))), 0x03: (N, 0),
            0x04: (R, 54 * max(1, min(4, aux1))), 0x05: (W, 54),
            0x06: (N, 0), 0x07: (N, 0), 0x08: (R, 54), 0x09: (W, 16),
            0x0A: (R, 2), 0x0B: (W, 39), 0x0C: (W, 54), 0x0D: (W, 54),
            0x0E: (R, 54), 0x10: (W, 40), 0x11: (R, 1), 0x12: (R, 16),
            0x13: (W, 16), 0x14: (R, 15), 0x15: (W, 15), 0x1E: (R, 1),
            0x1F: (R, 1), 0x20: (W, 39), 0x21: (W, 54), 0x22: (R, 3),
            0x23: (W, 3), 0x24: (R, aux1 if aux1 else 256),
            0x25: (W, aux1 if aux1 else 256), 0x26: (R, 3), 0x27: (W, 3),
        }
        return table.get(cmd, (None, 0))

    def sio_command(self, dev, cmd, aux1, aux2, cmd_cpb=0):
        """Ramka komendy. Zwraca (ack, mode, xlen, final, hs, txdata).
        hs=1: dane i COMPLETE w trybie high-speed XF551 (bit 7 komendy)."""
        if not self.device_enabled:
            return 0, 0, 0, 0, 0, b''
        if 0x31 <= dev <= 0x3F:
            drive = dev - 0x30
            if self._entry_for_drive(drive) is None:
                return 0, 0, 0, 0, 0, b''  # cisza: niech odpowie Altirra
            if cmd_cpb and 14 <= cmd_cpb < 85 and not self.topdrive_turbo:
                return 0, 0, 0, 0, 0, b''
            hs = 46 if cmd & 0x80 else 0   # XF551: komenda | $80
            cmd &= 0x7F
            mode, xlen = self.drive_spec(cmd, aux1, aux2, drive)
            if mode is None:
                return NAK, 0, 0, 0, 0, b''
            if mode == 2:
                self.pending = ('DRV', drive, cmd, aux1, aux2, xlen)
                return ACK, 2, xlen, 0, hs, b''
            st, data = self.drive_cmd(drive, cmd, aux1, aux2)
            if st == 0:
                return 0, 0, 0, 0, 0, b''
            final = COMPLETE if st == 1 else ERROR
            data = data.ljust(xlen, b'\0')[:xlen]
            return ACK, mode, xlen, final, hs, data
        if dev != 0x72 + (self.cfg[4] & 3):  # ID 0 -> $72 (sprzet testowy; sio2sd.org: $73)
            return 0, 0, 0, 0, 0, b''    # cisza - nie nasz identyfikator
        hscmd = bool(cmd & 0x80)
        cmd &= 0x7F
        # $9E/$9F negotiate/query high-speed parameters. Their response must
        # still be readable at normal speed; subsequent $80-tagged commands
        # use the negotiated high-speed timing.
        hs = (hsindex_to_cpb(self.cfg[1])
              if hscmd and cmd not in (0x1E, 0x1F) else 0)
        mode, xlen = self.frame_spec(cmd, aux1, aux2)
        if mode is None:
            self.log('nieznana komenda $%02X' % cmd)
            return NAK, 0, 0, 0, 0, b''
        if mode == 2:
            self.pending = (cmd, aux1, aux2, xlen)
            return ACK, 2, xlen, 0, hs, b''
        st, data = self.api(cmd, aux1, aux2)
        if st != 1 and mode == 0:
            return NAK, 0, 0, 0, 0, b''
        final = COMPLETE if st == 1 else ERROR
        data = data.ljust(xlen, b'\0')[:xlen]
        return ACK, mode, xlen, final, hs, data

    def sio_write_payload(self, data):
        """Ramka danych zapisu. Zwraca bajt koncowy."""
        if not self.pending:
            return ERROR
        if self.pending[0] == 'DRV':
            _, drive, cmd, aux1, aux2, xlen = self.pending
            self.pending = None
            st, _ = self.drive_cmd(drive, cmd, aux1, aux2, bytes(data[:xlen]))
            return COMPLETE if st == 1 else ERROR
        cmd, aux1, aux2, xlen = self.pending
        self.pending = None
        st, _ = self.api(cmd, aux1, aux2, data[:xlen])
        return COMPLETE if st == 1 else ERROR


def sio_checksum(data):
    s = 0
    for b in data:
        s += b
        if s > 255:
            s = (s & 255) + 1
    return s


def hsindex_to_cpb(hsindex):
    return max(14, min(84, 2 * ((int(hsindex) & 0xFF) + 7)))


def sio_lcd_command(dev, cmd, aux1, aux2, ack, final, mode, xlen):
    base_cmd = cmd & 0x7F
    turbo = 'H' if cmd & 0x80 else ''
    status = 'NAK' if ack == NAK else ('ERR' if final == ERROR else 'OK')
    if 0x31 <= dev <= 0x3F:
        drive = dev - 0x30
        sector = aux1 | (aux2 << 8)
        names = {
            0x52: 'READ',
            0x50: 'WRITE',
            0x57: 'WRITE',
            0x53: 'STATUS',
            0x4E: 'PERCOM',
        }
        name = names.get(base_cmd, '$%02X' % base_cmd)
        line1 = 'D%d %s%s %s' % (drive, name, turbo, status)
        if base_cmd in (0x50, 0x52, 0x57):
            line2 = 'SEC %05d' % sector
        elif xlen:
            line2 = 'LEN %d' % xlen
        else:
            line2 = 'AUX %02X %02X' % (aux1, aux2)
        return line1[:16], line2[:16]

    names = {
        0x00: 'STATUS',
        0x01: 'DIR',
        0x02: 'MOUNT',
        0x03: 'UMOUNT',
        0x04: 'LIST',
        0x05: 'CHDIR',
        0x06: 'UP',
        0x07: 'ROOT',
        0x08: 'CWD',
        0x09: 'MASK',
        0x0A: 'COUNT',
        0x0B: 'CREATE',
        0x0C: 'DELETE',
        0x0D: 'RENAME',
        0x0E: 'FIND',
        0x10: 'LCD',
        0x11: 'FW',
        0x12: 'GETCFG',
        0x13: 'SETCFG',
        0x14: 'GETMAP',
        0x15: 'SETMAP',
        0x1E: 'HSIDX',
        0x1F: 'HSQRY',
        0x20: 'OPEN',
        0x21: 'OPENID',
        0x22: 'LEN',
        0x23: 'SEEK',
        0x24: 'READ',
        0x25: 'WRITE',
        0x26: 'TELL',
        0x27: 'TRUNC',
    }
    name = names.get(base_cmd, '$%02X' % base_cmd)
    line1 = 'SIO2SD %s%s %s' % (name, turbo, status)
    line2 = 'AUX %02X %02X' % (aux1, aux2)
    if mode and xlen:
        line2 = '%s LEN %d' % ('RD' if mode == 1 else 'WR', xlen)
    return line1[:16], line2[:16]


class SIO2SDHandler(DeviceTCPHandler):
    """Sklejenie SIO2SDCard z protokolem Custom Device Server."""

    def setup(self):
        super().setup()
        cb = getattr(self.server, 'event_log', None)
        if cb:
            cb('Polaczono z emulatorem Altirra')

    def finish(self):
        cb = getattr(self.server, 'event_log', None)
        if cb:
            cb('Rozlaczono emulator Altirra')
        super().finish()

    def wrap_coldreset(self, param1, param2, timestamp) -> int:
        if param2 >= 0x7F000001 and param2 <= 0x7FFFFFFF:
            self.request.sendall(b'\x0C\x02')
            self.wrap_init()
            self.request.sendall(b'\x01\0\0\0\0')
            return
        self.handle_coldreset(timestamp)
        self.request.sendall(b'\x01\0\0\0\0')

    def handle_coldreset(self, timestamp):
        card = self.server.card
        card.set_cfg_selector(getattr(self.server, 'cfg_selector', False))
        card.cold_reset()
        if card.cfg_selector:
            msg = 'Zimny start Atari - CFG MODE / wybieraczka'
        else:
            msg = 'Zimny start Atari - stan karty wyzerowany'
        cb = getattr(self.server, 'event_log', None)
        if cb:
            cb(msg)
        else:
            print(msg)

    def handle_script_post(self, param1, param2, timestamp):
        if param1 == 0xFF:
            if param2:
                self.log('Skrypt sio2sd.atdevice: v%d.%d'
                         % (param2 // 10, param2 % 10))
            else:
                self.log('Skrypt sio2sd.atdevice: v1.4 lub starszy'
                         ' - PODMIEN PLIK I DODAJ URZADZENIE NA NOWO!')
            self.handle_coldreset(timestamp)

    def handle_script_event(self, param1, param2, timestamp) -> int:
        self.verbose = self.server.cmdline_args.verbose
        card = self.server.card
        if param1 == 1:
            frame = self.seg_rxbuffer.read(0, 5)
            dev, cmd, aux1, aux2 = frame[0], frame[1], frame[2], frame[3]
            ack, mode, xlen, final, hs, data = card.sio_command(
                dev, cmd, aux1, aux2, cmd_cpb=param2)
            activity = getattr(self.server, 'activity_log', None)
            if activity and ack:
                activity('SIOCMD',
                         sio_lcd_command(dev, cmd, aux1, aux2, ack, final,
                                         mode, xlen))
                activity('SIOACT')
                if mode or 0x20 <= (cmd & 0x7F) <= 0x27:
                    activity('SDACT')
                if ack == NAK or final == ERROR:
                    activity('ERROR')
            if self.verbose and ack:
                extra = ' HS' if hs else ''
                if param2:
                    baud = 1789773 // (param2 * 10) * 10
                    extra += ' [ramka %d cpb ~%d bd]' % (param2, baud)
                if hs:
                    extra += ' [HS %d cpb]' % hs
                if mode == 1 and ack == ACK:
                    h = data[:16].hex()
                    extra += ' %s len=%d dane=%s%s suma=%02x' % (
                        'OK' if final == COMPLETE else 'ERR', xlen, h,
                        '...' if xlen > 16 else '', sio_checksum(data))
                self.log('SIO2SD: dev=$%02X cmd=$%02X aux=%d,%d -> %s%s' %
                         (dev, cmd, aux1, aux2,
                          'ACK' if ack == ACK else 'NAK', extra))
            if mode == 1 and ack == ACK:
                self.seg_txbuffer.write(0, data + bytes([sio_checksum(data)]))
            if hs:
                self.seg_txbuffer.write(599, bytes([hs & 0xFF]))
                api_hs = (0x72 <= dev <= 0x75) and (cmd & 0x80)
                self.seg_txbuffer.write(598, bytes([1 if api_hs else 0]))
            else:
                self.seg_txbuffer.write(599, b'\0')
                self.seg_txbuffer.write(598, b'\0')
            return (ack | (mode << 8) | (xlen << 10) | (final << 20)
                    | ((1 if hs else 0) << 28))
        if param1 == 2:
            data = self.seg_rxbuffer.read(0, param2)
            final = card.sio_write_payload(data)
            activity = getattr(self.server, 'activity_log', None)
            if activity:
                activity('SIOACT')
                activity('SDACT')
                if final == ERROR:
                    activity('ERROR')
            return final
        return 0


class SIO2SDTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class SIO2SDServerRuntime:
    """Programowe API serwera dla GUI i innych nakladek."""

    def __init__(self, root, devid=0, read_only=False, port=9977,
                 verbose=False, log=print, activity=None,
                 cfg_selector=False, config=None, device_enabled=True,
                 topdrive_turbo=True):
        self.root = root
        self.devid = devid
        self.read_only = read_only
        self.port = port
        self.verbose = verbose
        self.cfg_selector = bool(cfg_selector)
        self.device_enabled = bool(device_enabled)
        self.topdrive_turbo = bool(topdrive_turbo)
        self.config = bytes(config)[:16].ljust(16, b'\0') if config is not None else None
        self.log = log or (lambda *_: None)
        self.activity = activity or (lambda *_: None)
        self.card = None
        self.server = None
        self.thread = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def _log(self, msg):
        self.log(str(msg))

    def start(self):
        if self.running:
            raise RuntimeError('serwer juz dziala')
        if not os.path.isdir(self.root):
            os.makedirs(self.root, exist_ok=True)
        self.card = SIO2SDCard(self.root, devid=self.devid,
                               read_only=self.read_only, log=self._log,
                               cfg_selector=self.cfg_selector,
                               config=self.config,
                               device_enabled=self.device_enabled,
                               topdrive_turbo=self.topdrive_turbo)
        self.server = SIO2SDTCPServer(('localhost', self.port),
                                      SIO2SDHandler)
        self.server.cmdline_args = SimpleNamespace(verbose=self.verbose)
        self.server.card = self.card
        self.server.event_log = self._log
        self.server.activity_log = self.activity
        self.server.cfg_selector = self.cfg_selector
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self._log('Karta SD: %s (ID %d%s)' %
                  (self.card.root, self.devid,
                   ', tylko odczyt' if self.read_only else ''))
        self._log('Serwer nasluchuje na localhost:%d' % self.port)
        return self.card

    def set_device_enabled(self, enabled):
        self.device_enabled = bool(enabled)
        if self.card is not None:
            self.card.set_device_enabled(self.device_enabled)
        self._log('SIO2SD dla Atari: %s' %
                  ('widoczny' if self.device_enabled else 'niewidoczny'))

    def set_topdrive_turbo(self, enabled):
        self.topdrive_turbo = bool(enabled)
        if self.card is not None:
            self.card.set_topdrive_turbo(self.topdrive_turbo)
        self._log('TopDrive turbo: %s' %
                  ('wlaczone' if self.topdrive_turbo else 'wylaczone'))

    def get_config(self):
        if self.card is not None:
            return self.card.get_config()
        if self.config is not None:
            return self.config
        cfg = bytearray(16)
        cfg[0] = 6
        cfg[1] = 40
        cfg[4] = self.devid
        cfg[5] = 1
        return bytes(cfg)

    def set_config(self, config):
        self.config = bytes(config)[:16].ljust(16, b'\0')
        self.devid = self.config[4] & 3
        if self.card is not None:
            self.card.set_config(self.config)
        self._log('Konfiguracja SIO2SD: zapisano znane pola')

    def set_cfg_selector(self, enabled):
        self.cfg_selector = bool(enabled)
        if self.server is not None:
            self.server.cfg_selector = self.cfg_selector
        if self.card is not None:
            self.card.set_cfg_selector(self.cfg_selector)
        self._log('CFG MODE / wybieraczka: %s' %
                  ('wlaczona' if self.cfg_selector else 'wylaczona'))

    def set_verbose(self, enabled):
        self.verbose = bool(enabled)
        if self.server is not None:
            self.server.cmdline_args.verbose = self.verbose
        self._log('Log SIO: %s' %
                  ('wlaczony' if self.verbose else 'wylaczony'))

    def stop(self):
        if self.server is not None:
            self._log('Zatrzymywanie serwera')
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        self.server = None
        self.thread = None
        self.card = None
        self._log('Serwer zatrzymany')


def main():
    ap = argparse.ArgumentParser(
        description='Serwer emulacji SIO2SD (fw 3.3) dla Altirry - '
                    'udostepnia katalog jako karte SD.')
    ap.add_argument('katalog', help='katalog udostepniany jako karta SD')
    ap.add_argument('--id', type=int, default=0, choices=range(4),
                    help='identyfikator urzadzenia SIO2SD (0-3, domyslnie 0)')
    ap.add_argument('--read-only', action='store_true',
                    help='karta tylko do odczytu')
    ap.add_argument('--mount', action='append', default=[],
                    metavar='N=PLIK',
                    help='zamontuj plik jako naped Dn (np. --mount 1=gra.atr)')
    ap.add_argument('--cfg-selector', action='store_true',
                    help='CFG MODE: na zimnym starcie podepnij SIO2SD.XEX jako D1')
    ap.add_argument('--no-topdrive-turbo', action='store_true',
                    help='wylacz odpowiedzi na szybkie ramki komend TopDrive')

    state = {}

    def post_args(args):
        card = SIO2SDCard(args.katalog, devid=args.id,
                          read_only=args.read_only,
                          cfg_selector=args.cfg_selector,
                          topdrive_turbo=not args.no_topdrive_turbo)
        state['card'] = card
        state['cfg_selector'] = args.cfg_selector
        print('Karta SD: %s (ID %d%s)' %
              (card.root, args.id,
               ', tylko odczyt' if args.read_only else ''))
        for m in args.mount:
            n, _, p = m.partition('=')
            card.mount(int(n), card.find_file(p))
        print('Konsola: mount N PLIK | umount N | list | quit')

    def console(card):
        import shlex
        while True:
            try:
                line = input()
            except EOFError:
                return
            try:
                parts = shlex.split(line)
                if not parts:
                    continue
                c = parts[0].lower()
                if c == 'mount' and len(parts) >= 3:
                    card.mount(int(parts[1]),
                               card.find_file(' '.join(parts[2:])))
                elif c == 'umount' and len(parts) >= 2:
                    card.umount(int(parts[1]))
                elif c == 'list':
                    if not card.drives:
                        print('brak zamontowanych napedow')
                    for d in sorted(card.drives):
                        disk, ent = card.drives[d]
                        print('D%d: %s (%s)' %
                              (d, clean_name(ent[0:39]) or '(pusty)',
                               type(disk).__name__))
                elif c in ('quit', 'exit'):
                    os._exit(0)
                else:
                    print('komendy: mount N PLIK | umount N | list | quit')
            except (ValueError, OSError) as ex:
                print('blad: %s' % ex)

    def attach(server):
        import threading
        server.card = state['card']
        server.cfg_selector = state.get('cfg_selector', False)
        t = threading.Thread(target=console, args=(state['card'],),
                             daemon=True)
        t.start()
        server.serve_forever()

    run_deviceserver(SIO2SDHandler, port=9977, arg_parser=ap,
                     post_argparse_handler=post_args, run_handler=attach)


if __name__ == '__main__':
    main()
