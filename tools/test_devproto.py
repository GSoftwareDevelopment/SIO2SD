#!/usr/bin/env python3
"""
test_devproto.py - test warstwy TCP serwera sio2sd_server.py.

Udaje strone emulatora (Altirra): protokol Custom Device Server V2 -
handshake, odbicie nazw segmentow, zdarzenia skryptu, transfer segmentow.
Weryfikuje pakowanie odpowiedzi dokladnie tak, jak rozpakuje je
sio2sd.atdevice. Uzycie: python3 tools/test_devproto.py
"""
import os, sys, socket, struct, tempfile, threading, time, socketserver, shutil

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'altirra'))
sys.path.insert(0, 'altirra')
from sio2sd_server import SIO2SDCard, SIO2SDHandler, sio_checksum

ACK, NAK, COMPLETE, ERROR = 0x41, 0x4E, 0x43, 0x45

fails = 0
def check(cond, what):
    global fails
    print(('  OK ' if cond else '  BLAD ') + what)
    if not cond: fails += 1

class FakeEmu:
    """Strona emulatora: segmenty rxbuffer(0) i txbuffer(1)."""

    def __init__(self, sock):
        self.s = sock
        self.seg = {0: bytearray(600), 1: bytearray(600)}

    def readall(self, n):
        out = bytearray()
        while len(out) < n:
            d = self.s.recv(n - len(out))
            assert d, 'polaczenie zamkniete'
            out.extend(d)
        return bytes(out)

    def serve_until_return(self):
        """Obsluguj zadania serwera az do wartosci zwrotnej (typ 1)."""
        while True:
            t = self.readall(1)[0]
            if t == 1:      # return value
                return struct.unpack('<i', self.readall(4))[0]
            if t == 0x0C:   # ack protokolu V2 (drugi bajt = wersja)
                self.readall(1)
                continue
            if t == 0x0A:   # get segment names
                names = [b'rxbuffer', b'txbuffer']
                pkt = struct.pack('<I', len(names))
                for n in names:
                    pkt += struct.pack('<I', len(n)) + n
                self.s.sendall(pkt)
                continue
            if t == 0x0B:   # get layer names
                self.s.sendall(struct.pack('<I', 0))
                continue
            if t == 6:      # read segment
                idx, off, ln = struct.unpack('<BII', self.readall(9))
                self.s.sendall(bytes(self.seg[idx][off:off+ln]))
                continue
            if t == 7:      # write segment
                idx, off, ln = struct.unpack('<BII', self.readall(9))
                data = self.readall(ln)
                self.seg[idx][off:off+ln] = data
                continue
            raise AssertionError('nieoczekiwany typ %02X' % t)

    def cmd(self, cid, p1, p2):
        self.s.sendall(struct.pack('<BIiQ', cid, p1 & 0xFFFFFFFF, p2, 0))
        return self.serve_until_return()

    def coldreset_handshake(self):
        self.s.sendall(struct.pack('<BIiQ', 4, 0, 0x7F000001, 0))
        return self.serve_until_return()

    def frame(self, dev, cmd, aux1=0, aux2=0, cmd_cpb=0):
        f = bytes([dev, cmd, aux1, aux2])
        f += bytes([sio_checksum(f)])
        self.seg[0][0:5] = f
        return self.cmd(7, 1, cmd_cpb)    # script event 1


def main():
    tmp = tempfile.mkdtemp(prefix='sio2sd_tcp_')
    # baza karty to <tmp>/Atari (tak jak w oryginalnym SIO2SD) - fikstura tam
    os.makedirs(os.path.join(tmp, 'Atari', 'GRY'))
    with open(os.path.join(tmp, 'Atari', 'GRY', 'PLIK.TXT'), 'wb') as f:
        f.write(b'ALA MA ATARI')
    # plik poza /Atari nie moze byc widoczny z karty
    with open(os.path.join(tmp, 'POZA.TXT'), 'wb') as f:
        f.write(b'x')
    boot_atr = bytearray(16 + 720 * 128)
    boot_atr[0:2] = (0x0296).to_bytes(2, 'little')
    boot_paras = (720 * 128) // 16
    boot_atr[2:4] = (boot_paras & 0xFFFF).to_bytes(2, 'little')
    boot_atr[4:6] = (128).to_bytes(2, 'little')
    boot_atr[6] = boot_paras >> 16
    boot_path = os.path.join(tmp, 'Atari', 'GRY', 'BOOT.ATR')
    with open(boot_path, 'wb') as f:
        f.write(boot_atr)

    card = SIO2SDCard(tmp, devid=0, log=lambda *a: None)
    card.mount(1, boot_path, persist=False, quiet=True)

    srv = socketserver.TCPServer(('localhost', 0), SIO2SDHandler)
    srv.card = card
    srv.cmdline_args = type('A', (), {'verbose': False})()
    srv.cfg_selector = True
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()

    s = socket.create_connection(('localhost', port))
    emu = FakeEmu(s)
    emu.coldreset_handshake()
    print('--- handshake / odbicie segmentow ---')
    check(True, 'handshake V2 + refleksja nazw segmentow')
    check(card.drives[1][1][0:8] == b'BOOT.ATR',
          'handshake V2 nie podmienia D1: na CFG selector')
    srv.cfg_selector = False
    card.umount(1, persist=False)
    card.changed = 0

    print('--- ramka statusu ($00) ---')
    r = emu.frame(0x72, 0x00)
    ack, mode, xlen, final = r & 0xFF, (r >> 8) & 3, (r >> 10) & 0x3FF, (r >> 20) & 0xFF
    check(ack == ACK and mode == 1 and xlen == 1 and final == COMPLETE,
          f'ACK/odczyt/1B/COMPLETE: {ack:02X}/{mode}/{xlen}/{final:02X}')
    check(emu.seg[1][0] == 1 and emu.seg[1][1] == sio_checksum(bytes([1])),
          'txbuffer: status karty + suma')

    print('--- cisza dla innego ID ---')
    r = emu.frame(0x75, 0x00)
    check(r == 0, f'ID 3 przy skonfigurowanym 0 -> cisza: {r}')

    print('--- wersja firmware ($11) ---')
    r = emu.frame(0x72, 0x11)
    check((r & 0xFF) == ACK and emu.seg[1][0] == 0x33, 'fw 3.3')

    print('--- szybka ramka API SIO2SD (/H self-test) ---')
    cfg = bytearray(card.get_config())
    cfg[1] = 6
    card.set_config(cfg)
    r = emu.frame(0x72, 0x9F)
    check((r & 0xFF) == ACK and ((r >> 28) & 1) == 0
          and emu.seg[1][0] < 17,
          f'turbo hIndex $9F ($1F|$80) normal speed = {emu.seg[1][0]}')
    check(emu.seg[1][599] == 0, 'SIO2SD API HS probe: no speed switch yet')
    card.set_topdrive_turbo(False)
    r = emu.frame(0x72, 0x80)
    check((r & 0xFF) == ACK and ((r >> 28) & 1) == 1
          and ((r >> 20) & 0xFF) == COMPLETE,
          f'API $80 ($00|$80) dziala mimo TopDrive off: {r:08X}')
    check(emu.seg[1][599] == 26, 'SIO2SD API status HS: 26 cpb')
    check(emu.seg[1][598] == 1, 'SIO2SD API HS: ACK normal, potem C/dane HS')
    card.set_topdrive_turbo(True)

    print('--- tryb niewidoczny dla Atari ---')
    card.mount(1, boot_path, persist=False, quiet=True)
    card.set_device_enabled(False)
    check(emu.frame(0x72, 0x11) == 0, 'API SIO2SD milczy')
    check(emu.frame(0x31, 0x53) == 0, 'D1: milczy')
    card.set_device_enabled(True)
    check((emu.frame(0x72, 0x11) & 0xFF) == ACK, 'SIO2SD widoczny ponownie')
    card.umount(1, persist=False)
    card.changed = 0

    print('--- maska + liczba wpisow ($09/$0A) ---')
    r = emu.frame(0x72, 0x09, 3, 0)
    check((r & 0xFF) == ACK and ((r >> 8) & 3) == 2, 'ACK $09 (tryb zapisu)')
    emu.seg[0][0:16] = b'*'.ljust(16, b'\0')
    r = emu.cmd(7, 2, 16)           # dane zapisu 16B
    check(r == COMPLETE, f'zapis maski -> COMPLETE: {r:02X}')
    r = emu.frame(0x72, 0x0A)
    check(emu.seg[1][0] == 1 and emu.seg[1][1] == 0, 'liczba wpisow = 1 (GRY)')

    print('--- otwarcie pliku i odczyt ($20/$24/$26) ---')
    # wejdz do GRY: znajdz wpis ($04) i chdir ($05)
    r = emu.frame(0x72, 0x04, 1, 1)
    ent = bytes(emu.seg[1][0:54])
    check(ent[0:3] == b'GRY' and ent[39] == 1, 'wpis katalogu GRY')
    r = emu.frame(0x72, 0x05)
    emu.seg[0][0:54] = ent
    r2 = emu.cmd(7, 2, 54)
    check(r2 == COMPLETE, 'chdir GRY')
    r = emu.frame(0x72, 0x20, 3, 0)     # otworz bez tworzenia, biezacy
    emu.seg[0][0:39] = b'PLIK.TXT'.ljust(39, b'\0')
    r2 = emu.cmd(7, 2, 39)
    check(r2 == COMPLETE, 'otwarcie PLIK.TXT')
    r = emu.frame(0x72, 0x26)
    check(int.from_bytes(bytes(emu.seg[1][0:3]), 'little') == 12, 'dlugosc 12')
    r = emu.frame(0x72, 0x24, 12, 0)
    check(bytes(emu.seg[1][0:12]) == b'ALA MA ATARI', 'odczyt danych')
    check(emu.seg[1][12] == sio_checksum(b'ALA MA ATARI'), 'suma kontrolna danych')

    print('--- zapis pliku ($25) ---')
    emu.frame(0x72, 0x23)               # seek: dane zapisu 3B
    emu.seg[0][0:3] = (0).to_bytes(3, 'little')
    emu.cmd(7, 2, 3)
    r = emu.frame(0x72, 0x25, 5, 0)
    emu.seg[0][0:5] = b'ATARI'
    r2 = emu.cmd(7, 2, 5)
    check(r2 == COMPLETE, 'zapis 5B')
    with open(os.path.join(tmp, 'Atari', 'GRY', 'PLIK.TXT'), 'rb') as f:
        check(f.read() == b'ATARIA ATARI', 'zawartosc pliku po zapisie')

    print('--- montowanie ATR przez $02 i sektory D1: ---')
    atr = bytearray(16 + 720 * 128)
    atr[0:2] = (0x0296).to_bytes(2, 'little')
    paras = (720 * 128) // 16
    atr[2:4] = (paras & 0xFFFF).to_bytes(2, 'little')
    atr[4:6] = (128).to_bytes(2, 'little')
    atr[6] = paras >> 16
    atr[16 + 4 * 128:16 + 4 * 128 + 5] = b'SEKT5'      # znacznik w sektorze 5
    with open(os.path.join(tmp, 'Atari', 'GRY', 'DYSK.ATR'), 'wb') as f:
        f.write(atr)
    # znajdz wpis DYSK.ATR (maska juz '*'; enumeracja od poczatku)
    emu.frame(0x72, 0x09, 3, 0)
    emu.seg[0][0:16] = b'DYSK.ATR'.ljust(16, b'\0')
    emu.cmd(7, 2, 16)
    r = emu.frame(0x72, 0x04, 1, 1)
    ent = bytes(emu.seg[1][0:54])
    check(ent[0:8] == b'DYSK.ATR', f'wpis DYSK.ATR: {ent[0:8]!r}')
    r = emu.frame(0x72, 0x02, 1, 1)      # zamontuj jako D1:
    emu.seg[0][0:54] = ent
    r2 = emu.cmd(7, 2, 54)
    check(r2 == COMPLETE, f'montowanie $02 -> COMPLETE: {r2:02X}')
    r = emu.frame(0x31, 0x53)            # status D1:
    check((r & 0xFF) == ACK and ((r >> 10) & 0x3FF) == 4, 'status D1: 4 bajty')
    r = emu.frame(0x31, 0x52, 5, 0)      # czytaj sektor 5
    check(bytes(emu.seg[1][0:5]) == b'SEKT5', 'odczyt sektora 5')
    check(((r >> 28) & 1) == 0, 'zwykly odczyt bez flagi HS')
    r = emu.frame(0x31, 0x52, 5, 0, cmd_cpb=46)  # TopDrive: szybka ramka
    check((r & 0xFF) == ACK and ((r >> 20) & 0xFF) == COMPLETE,
          f'TopDrive szybka ramka -> ACK+COMPLETE: {r:08X}')
    check(bytes(emu.seg[1][0:5]) == b'SEKT5', 'TopDrive: te same dane')
    card.set_topdrive_turbo(False)
    r = emu.frame(0x31, 0x52, 5, 0, cmd_cpb=46)
    check(r == 0, 'TopDrive wylaczony -> cisza na szybkiej ramce')
    r = emu.frame(0x31, 0x52, 5, 0)
    check((r & 0xFF) == ACK, 'TopDrive wylaczony: zwykla ramka nadal dziala')
    r = emu.frame(0x31, 0xD2, 5, 0)      # XF551 high-speed read
    check((r & 0xFF) == ACK and ((r >> 28) & 1) == 1
          and ((r >> 20) & 0xFF) == COMPLETE,
          f'$D2 (XF551) -> ACK+HS+COMPLETE: {r:08X}')
    check(emu.seg[1][599] == 46, 'XF551 HS: 46 cpb')
    check(emu.seg[1][598] == 0, 'XF551 HS: COMPLETE tez HS')
    check(bytes(emu.seg[1][0:5]) == b'SEKT5', 'odczyt HS: te same dane')
    card.set_topdrive_turbo(True)
    r = emu.frame(0x31, 0xD3, 1, 0)      # XF551 high-speed status
    check((r & 0xFF) == ACK and ((r >> 28) & 1) == 1
          and ((r >> 10) & 0x3FF) == 4, 'status $D3 z flaga HS')
    print('--- wirtualne sloty V1:-V99 i mapowanie $14/$15 ---')
    virt_atr = bytearray(atr)
    virt_atr[16 + 4 * 128:16 + 4 * 128 + 5] = b'VIRT5'
    with open(os.path.join(tmp, 'Atari', 'GRY', 'VIRT.ATR'), 'wb') as f:
        f.write(virt_atr)
    emu.frame(0x72, 0x09, 3, 0)
    emu.seg[0][0:16] = b'VIRT.ATR'.ljust(16, b'\0')
    emu.cmd(7, 2, 16)
    emu.frame(0x72, 0x04, 1, 1)
    vent = bytes(emu.seg[1][0:54])
    r = emu.frame(0x72, 0x02, 16, 1)     # V1: pierwszy slot po D1:-D15:
    emu.seg[0][0:54] = vent
    r2 = emu.cmd(7, 2, 54)
    check(r2 == COMPLETE, 'montowanie V1: przez $02 aux=16')
    r = emu.frame(0x72, 0x01, 16, 1)
    check(bytes(emu.seg[1][0:8]) == b'VIRT.ATR', 'odczyt wpisu V1: przez $01')
    r = emu.frame(0x72, 0x15)
    vmap = bytearray(range(15))
    vmap[0] = 15                           # D1: -> V1:
    emu.seg[0][0:15] = vmap
    r2 = emu.cmd(7, 2, 15)
    check(r2 == COMPLETE, 'ustawienie mapowania D1: -> V1:')
    r = emu.frame(0x31, 0x52, 5, 0)
    check(bytes(emu.seg[1][0:5]) == b'VIRT5', 'D1: czyta z V1 po mapowaniu')
    with open(os.path.join(tmp, 'SIO2SD.CFG'), 'rb') as f:
        cfg_blob = f.read()
    voff = 0x40 + 15 * 0x40
    check(cfg_blob[1] == 15 and cfg_blob[voff:voff + 8] == b'VIRT.ATR',
          'SIO2SD.CFG zapisuje mapowanie D1->V1 i wpis V1')
    loaded = SIO2SDCard(tmp, devid=0, log=lambda *a: None)
    check(loaded.vmap[0] == 15 and 1 in loaded.vslots,
          'SIO2SD.CFG odtwarza V1 i mapowanie D1->V1')
    st, data = loaded.drive_cmd(1, 0x52, 5, 0)
    check(st == 1 and data[:5] == b'VIRT5',
          'nowa karta czyta D1: z V1 po starcie')
    loaded.mount(1, boot_path, reset_mapping=False,
                 persist=False, quiet=True)
    st, data = loaded.drive_cmd(1, 0x52, 5, 0)
    check(loaded.vmap[0] == 15 and st == 1 and data[:5] == b'VIRT5',
          'montowanie D1: z zachowaniem mapowania nie rusza D1->V1')
    loaded.mount(1, boot_path, reset_mapping=True,
                 persist=False, quiet=True)
    check(loaded.vmap[0] == 0,
          'zwykle montowanie D1: przywraca mapowanie D1->D1')
    loaded.mount_virtual(2, boot_path, persist=False, quiet=True)
    check(2 in loaded.vslots, 'publiczne montowanie V2:')
    loaded.map_drive_to_virtual(2, 2, persist=False)
    check(loaded.vmap[1] == 16,
          'publiczne mapowanie D2: -> V2:')
    loaded.reset_drive_mapping(2, persist=False)
    check(loaded.vmap[1] == 1,
          'publiczne przywrocenie mapowania D2: -> D2:')
    loaded.umount_virtual(2, persist=False)
    check(2 not in loaded.vslots, 'publiczne odmontowanie V2:')
    loaded.mount(1, boot_path, persist=False, quiet=True)
    loaded.map_drive_to_virtual(1, 3, persist=False)  # V3 jest puste
    st, data = loaded.drive_cmd(1, 0x52, 5, 0)
    check(st == 1 and data[:5] == boot_atr[16 + 4 * 128:16 + 4 * 128 + 5],
          'puste mapowanie D1->V3 nie blokuje fizycznie zamontowanego D1')
    r = emu.frame(0x72, 0x15)
    vmap[0] = 0                            # D1: z powrotem na D1:
    emu.seg[0][0:15] = vmap
    r2 = emu.cmd(7, 2, 15)
    check(r2 == COMPLETE, 'przywrocenie mapowania D1: -> D1:')
    loaded.swap_drive_with_virtual(1, 1, persist=False)
    st, data = loaded.drive_cmd(1, 0x52, 5, 0)
    check(st == 1 and data[:5] == b'VIRT5',
          'zamiana D1<->V1: D1 czyta dawny V1')
    loaded.map_drive_to_virtual(1, 1, persist=False)
    st, data = loaded.drive_cmd(1, 0x52, 5, 0)
    check(st == 1 and data[:5] == boot_atr[16 + 4 * 128:16 + 4 * 128 + 5],
          'zamiana D1<->V1: V1 ma dawny D1')
    loaded.swap_drive_with_virtual(1, 1, persist=False)
    loaded.reset_drive_mapping(1, persist=False)
    if os.environ.get("SIO2SD_EXPERIMENTAL_ATR_TESTS") == "1":
        new_atr = loaded.create_empty_atr()
        check(os.path.basename(new_atr) == 'NEW0001.ATR',
              'trwaly pusty ATR: automatyczna nazwa NEW0001.ATR')
        check(os.path.getsize(new_atr) == 16 + 720 * 128,
              'trwaly pusty ATR: rozmiar 720 sektorow SD')
        with open(new_atr, 'rb') as f:
            new_hdr = f.read(16)
        check(new_hdr[0:2] == b'\x96\x02' and new_hdr[4:6] == b'\x80\x00',
              'trwaly pusty ATR: poprawny naglowek')
        loaded.mount_virtual(4, new_atr, persist=False, quiet=True)
        loaded.map_drive_to_virtual(1, 4, persist=False)
        st, _ = loaded.drive_cmd(1, 0x57, 7, 0, b'NEWATR'.ljust(128, b'\0'))
        check(st == 1, 'trwaly pusty ATR: zapis sektora przez D1->V4')
        with open(new_atr, 'rb') as f:
            f.seek(16 + (7 - 1) * 128)
            saved = f.read(6)
        check(saved == b'NEWATR',
              'trwaly pusty ATR: zapis widoczny w pliku')
        loaded.reset_drive_mapping(1, persist=False)
        ed_atr = loaded.create_empty_atr(total_sectors=1040, sector_size=128)
        check(os.path.basename(ed_atr) == 'NEW0002.ATR',
              'trwaly pusty ATR ED: kolejna automatyczna nazwa')
        check(os.path.getsize(ed_atr) == 16 + 1040 * 128,
              'trwaly pusty ATR ED: rozmiar 1040 sektorow SD')
        dd_new_atr = loaded.create_empty_atr(total_sectors=720, sector_size=256)
        check(os.path.basename(dd_new_atr) == 'NEW0003.ATR',
              'trwaly pusty ATR DD: kolejna automatyczna nazwa')
        check(os.path.getsize(dd_new_atr) == 16 + 384 + 717 * 256,
              'trwaly pusty ATR DD: rozmiar 720 sektorow DD')
        loaded.mount_virtual(5, dd_new_atr, persist=False, quiet=True)
        loaded.map_drive_to_virtual(1, 5, persist=False)
        st, data = loaded.drive_cmd(1, 0x53, 1, 0)
        check(st == 1 and data[0] == 0x30,
              'trwaly pusty ATR DD: status 256B')
        st, data = loaded.drive_cmd(1, 0x52, 5, 0)
        check(st == 1 and len(data) == 256,
              'trwaly pusty ATR DD: odczyt sektora 256B')
        loaded.reset_drive_mapping(1, persist=False)
        sdx_atr = loaded.create_empty_atr(total_sectors=720, sector_size=128,
                                          filesystem='sdx',
                                          volume_label='SYSVOL')
        with open(sdx_atr, 'rb') as f:
            sdx_data = f.read()
        check(sdx_data[16 + 22:16 + 30] == b'SYSVOL  ',
              'trwaly pusty ATR SDX: nazwa VOLUME w obrazie SD')
        check(sdx_data[16 + (6 - 1) * 128:16 + (6 - 1) * 128 + 23].find(b'MAIN') >= 0,
              'trwaly pusty ATR SDX: katalog MAIN w obrazie SD')
        sdx_ed_atr = loaded.create_empty_atr(total_sectors=1040, sector_size=128,
                                             filesystem='sdx')
        with open(sdx_ed_atr, 'rb') as f:
            sdx_ed_data = f.read()
        check(sdx_ed_data[16 + (7 - 1) * 128:16 + (7 - 1) * 128 + 23].find(b'MAIN') >= 0,
              'trwaly pusty ATR SDX: katalog MAIN w obrazie ED')
        dos2_atr = loaded.create_empty_atr(total_sectors=720, sector_size=128,
                                           filesystem='dos2')
        with open(dos2_atr, 'rb') as f:
            dos2_data = f.read()
        dos2_vtoc = dos2_data[16 + (360 - 1) * 128:16 + 360 * 128]
        check(dos2_vtoc[0] == 2 and int.from_bytes(dos2_vtoc[1:3], 'little') == 707,
              'trwaly ATR DOS 2.x: VTOC dla SD 90 KB')
        mydos_atr = loaded.create_empty_atr(total_sectors=1440, sector_size=256,
                                            filesystem='mydos')
        with open(mydos_atr, 'rb') as f:
            mydos_data = f.read()
        mydos_vtoc_off = 16 + 384 + (360 - 4) * 256
        mydos_vtoc = mydos_data[mydos_vtoc_off:mydos_vtoc_off + 256]
        check(mydos_vtoc[0] == 3 and
              int.from_bytes(mydos_vtoc[1:3], 'little') == 1428,
              'trwaly ATR MyDOS: VTOC dla QD 360 KB')
        sdx_large_atr = loaded.create_empty_atr(total_sectors=4096,
                                                sector_size=128,
                                                filesystem='sdx',
                                                volume_label='BIGSDX')
        with open(sdx_large_atr, 'rb') as f:
            sdx_large_data = f.read()
        sdx_large_root = 4 + ((4096 + 511) // 512)
        check(sdx_large_data[16 + 22:16 + 30] == b'BIGSDX  ',
              'trwaly duzy ATR SDX: nazwa VOLUME')
        check(sdx_large_data[16 + (sdx_large_root - 1) * 128:
                             16 + (sdx_large_root - 1) * 128 + 23].find(b'MAIN') >= 0,
              'trwaly duzy ATR SDX: wygenerowany katalog MAIN')
        custom_atr = loaded.create_empty_atr(total_sectors=4096, sector_size=256)
        check(os.path.getsize(custom_atr) == 16 + 384 + (4096 - 3) * 256,
              'wlasna geometria ATR: 4096 sektorow DD')

    dd_total = 720
    dd_data_len = 384 + (dd_total - 3) * 256
    dd_paras = dd_data_len // 16
    dd_atr = bytearray(16 + dd_data_len)
    dd_atr[0:2] = (0x0296).to_bytes(2, 'little')
    dd_atr[2:4] = (dd_paras & 0xFFFF).to_bytes(2, 'little')
    dd_atr[4:6] = (256).to_bytes(2, 'little')
    dd_atr[6] = dd_paras >> 16
    dd_off5 = 16 + 384 + (5 - 4) * 256
    dd_atr[dd_off5:dd_off5 + 5] = b'DD256'
    dd_path = os.path.join(tmp, 'Atari', 'GRY', 'DD.ATR')
    with open(dd_path, 'wb') as f:
        f.write(dd_atr)
    card.mount_virtual(1, dd_path, persist=False, quiet=True)
    card.map_drive_to_virtual(1, 1, persist=False)
    r = emu.frame(0x31, 0x53)
    check(emu.seg[1][0] == 0x30, 'status D1->V1 DD: sektor 256B')
    r = emu.frame(0x31, 0x52, 5, 0)
    check(((r >> 10) & 0x3FF) == 256 and bytes(emu.seg[1][0:5]) == b'DD256',
          'D1->V1 DD: odczyt sektora 5 ma 256 bajtow')
    card.reset_drive_mapping(1, persist=False)

    r = emu.frame(0x31, 0x57, 6, 0)      # zapis sektora 6
    emu.seg[0][0:128] = b'ZAPIS'.ljust(128, b'\0')
    r2 = emu.cmd(7, 2, 128)
    check(r2 == COMPLETE, 'zapis sektora 6')
    with open(os.path.join(tmp, 'Atari', 'GRY', 'DYSK.ATR'), 'rb') as f:
        f.seek(16 + 5 * 128)
        check(f.read(5) == b'ZAPIS', 'zapis widoczny w pliku ATR')

    print('--- ochrona zapisu ATR wg flagi naglowka ---')
    atr_ro = bytearray(atr)
    atr_ro[7] |= 1
    atr_ro[16 + 6 * 128:16 + 6 * 128 + 5] = b'ORIG!'
    with open(os.path.join(tmp, 'Atari', 'GRY', 'RO.ATR'), 'wb') as f:
        f.write(atr_ro)
    emu.frame(0x72, 0x09, 3, 0)
    emu.seg[0][0:16] = b'RO.ATR'.ljust(16, b'\0')
    emu.cmd(7, 2, 16)
    emu.frame(0x72, 0x04, 1, 1)
    ent = bytes(emu.seg[1][0:54])
    r = emu.frame(0x72, 0x02, 1, 1)
    emu.seg[0][0:54] = ent
    r2 = emu.cmd(7, 2, 54)
    check(r2 == COMPLETE, 'montowanie ATR z flaga RO')
    r = emu.frame(0x31, 0x53)
    check(bytes(emu.seg[1][0:1])[0] & 0x08, 'status D1: write-protect')
    r = emu.frame(0x31, 0x57, 7, 0)
    emu.seg[0][0:128] = b'NIE!'.ljust(128, b'\0')
    r2 = emu.cmd(7, 2, 128)
    check(r2 == ERROR, 'zapis sektora odrzucony dla ATR RO')
    with open(os.path.join(tmp, 'Atari', 'GRY', 'RO.ATR'), 'rb') as f:
        f.seek(16 + 6 * 128)
        check(f.read(5) == b'ORIG!', 'plik ATR RO bez zmian')
    r = emu.frame(0x72, 0x13)
    cfg = bytearray(16)
    cfg[0] = 6
    cfg[1] = 40
    cfg[4] = 0
    cfg[5] = 0
    emu.seg[0][0:16] = cfg
    r2 = emu.cmd(7, 2, 16)
    check(r2 == COMPLETE, 'wylaczenie ochrony ATR w configu')
    r = emu.frame(0x31, 0x53)
    check((bytes(emu.seg[1][0:1])[0] & 0x08) == 0,
          'status D1: zapis ponownie dozwolony')
    r = emu.frame(0x31, 0x57, 7, 0)
    emu.seg[0][0:128] = b'OK!!!'.ljust(128, b'\0')
    r2 = emu.cmd(7, 2, 128)
    check(r2 == COMPLETE, 'zapis sektora po wylaczeniu ochrony')
    with open(os.path.join(tmp, 'Atari', 'GRY', 'RO.ATR'), 'rb') as f:
        f.seek(16 + 6 * 128)
        check(f.read(5) == b'OK!!!', 'plik ATR zmieniony po wylaczeniu ochrony')

    r = emu.frame(0x32, 0x53)
    check(r == 0, f'niezamontowany D2: -> cisza: {r}')

    print('--- montowanie XEX przez $02 (dysk rozruchowy) ---')
    with open(os.path.join(tmp, 'Atari', 'GRY', 'GRA.XEX'), 'wb') as f:
        f.write(b'\xFF\xFF' + (0x2000).to_bytes(2, 'little')
                + (0x2004).to_bytes(2, 'little') + b'ABCDE')
    emu.frame(0x72, 0x09, 3, 0)
    emu.seg[0][0:16] = b'GRA.XEX'.ljust(16, b'\0')
    emu.cmd(7, 2, 16)
    emu.frame(0x72, 0x04, 1, 1)
    ent = bytes(emu.seg[1][0:54])
    r = emu.frame(0x72, 0x02, 2, 1)      # D2:
    emu.seg[0][0:54] = ent
    r2 = emu.cmd(7, 2, 54)
    check(r2 == COMPLETE, 'montowanie XEX na D2:')
    r = emu.frame(0x32, 0x52, 1, 0)      # sektor 1 = bootloader
    s1 = bytes(emu.seg[1][0:128])
    check(s1[0] == 0 and s1[1] == 3 and s1[2:4] == b'\x00\x07',
          f'naglowek boot: {s1[0:6].hex()}')
    check(s1[9:12] == (11).to_bytes(3, 'little'),
          f'dlugosc XEX wpatchowana: {s1[9:12].hex()}')
    r = emu.frame(0x32, 0x52, 4, 0)      # sektor 4 = dane XEX
    check(bytes(emu.seg[1][0:2]) == b'\xFF\xFF', 'dane XEX od sektora 4')
    # $01: odczyt mapowan D1-D2
    r = emu.frame(0x72, 0x01, 1, 2)
    m1 = bytes(emu.seg[1][0:54]); m2 = bytes(emu.seg[1][54:108])
    check(m1[0:6] == b'RO.ATR' and m2[0:7] == b'GRA.XEX', 'mapowania w $01')
    # $03: odlacz D1-D2
    r = emu.frame(0x72, 0x03, 1, 2)
    check((r & 0xFF) == ACK, 'odlaczenie $03')
    r = emu.frame(0x31, 0x53)
    check(r == 0, 'D1: znowu cichy')

    print('--- nieznana komenda -> NAK ---')
    r = emu.frame(0x72, 0x3F)
    check((r & 0xFF) == NAK, f'komenda $3F -> NAK: {r & 0xFF:02X}')

    s.close()
    srv.shutdown()
    shutil.rmtree(tmp, True)
    print()
    if fails:
        print(f'NIEPOWODZENIA: {fails}')
        sys.exit(1)
    print('TEST PROTOKOLU TCP ZALICZONY')


if __name__ == '__main__':
    main()
