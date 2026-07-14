#!/usr/bin/env python3
"""
simtest3.py - test integracyjny: sterownik SDCDEV.SYS (symulacja 6502)
+ PRAWDZIWA logika serwera emulacji SIO2SD (altirra/sio2sd_server.py)
na tymczasowym katalogu. Weryfikuje pelna zgodnosc sterownika z emulacja
karty dla Altirry. Uzycie: python3 tools/simtest3.py SDCDEV.ASM
"""
import os, sys, re, importlib.util
from py65.devices.mpu6502 import MPU
from py65.disassembler import Disassembler

spec = importlib.util.spec_from_file_location('sdxasm', 'tools/sdxasm.py')
sdxasm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdxasm)

SRC = sys.argv[1]
lines = open(SRC, encoding='utf-8').readlines()
A = sdxasm.Asm()
assert A.assemble(lines), A.errors
A.write('SDCDEV.SYS')

MEMLO = 0x2000
SYMS = {'INSTALL': 0x0CF0, 'DEVNAME': 0x0C00, 'DEVSPEC': 0x0C30,
        'COMTAB2': 0x0C60, 'EXTENDED': 0x0CE0}
mem_img, blocks, entry = sdxasm.load_image('SDCDEV.SYS', MEMLO, SYMS)
RB = blocks[1]
XB = blocks.get(2, RB)

def lab(name):
    kind, off = A.labels[name.lower()]
    if kind == 'R': return RB + off
    if kind == 'X': return XB + off
    return off

SIOV, CIOV, VSET, VPOP, RET = 0xE459, 0xE456, 0x07F1, 0x07F4, 0xAA00
DCB = 0x300
K_FID, K_DEV, K_NAME, K_XNAME = 0x760, 0x761, 0x762, 0x76D
K_MODE, K_SCAN, K_ATTR = 0x778, 0x779, 0x77A
K_ADDPOS, K_BYTBUF, K_MEMREIX, K_DENTRY, K_PATH = 0x782, 0x785, 0x787, 0x789, 0x7A0
DEVIDX = 0x740

import tempfile, shutil, atexit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'altirra'))
sys.path.insert(0, 'altirra')
from sio2sd_server import SIO2SDCard, sio_checksum

_tmproot = tempfile.mkdtemp(prefix='sio2sd_test_')
atexit.register(shutil.rmtree, _tmproot, True)


class FSObj:
    def __init__(self, path):
        self.path = path

    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def typ(self):
        return 1 if os.path.isdir(self.path) else 2

    @property
    def data(self):
        with open(self.path, 'rb') as f:
            return f.read()

    @property
    def children(self):
        return [FSObj(os.path.join(self.path, n))
                for n in os.listdir(self.path)]


class FSAdapter:
    """Adapter: interfejs FakeSD nad prawdziwa logika serwera."""

    def __init__(self, root):
        self.card = SIO2SDCard(root, devid=0, log=lambda *a: None)
        self.root = FSObj(self.card.root)

    def add(self, parent, name, typ, data=b''):
        p = os.path.join(parent.path, name)
        if typ == 1:
            os.mkdir(p)
        else:
            with open(p, 'wb') as f:
                f.write(data)
        self.card.changed = 4
        return FSObj(p)

    def find(self, base, name):
        for n in os.listdir(base.path):
            if n.lower() == name.lower():
                return FSObj(os.path.join(base.path, n))
        return None

    @property
    def cwd(self):
        return FSObj(self.card.cwd)

    @cwd.setter
    def cwd(self, obj):
        self.card.cwd = obj.path
        self.card.changed = 4

    @property
    def chg(self):
        return self.card.changed

    @chg.setter
    def chg(self, v):
        self.card.changed = v

    def cmd(self, c, aux1, aux2, data):
        return self.card.api(c, aux1, aux2, bytes(data))


mpu = MPU()
mem = mpu.memory
for a, b in mem_img.items(): mem[a] = b

sd = FSAdapter(_tmproot)
printed = []

def sio_call():
    dev = mem[DCB]; cmd = mem[DCB+2]; st = mem[DCB+3]
    buf = mem[DCB+4] | (mem[DCB+5] << 8)
    ln = mem[DCB+8] | (mem[DCB+9] << 8)
    aux1, aux2 = mem[DCB+10], mem[DCB+11]
    if dev != 0x72:
        status = 138
    else:
        data = bytes(mem[buf:buf+ln]) if st == 0x80 else b''
        status, out = sd.cmd(cmd, aux1, aux2, data)
        if st == 0x40 and status < 128:
            out = (out + bytes(ln))[:ln]
            for i, b in enumerate(out): mem[buf+i] = b
    mem[DCB+3] = status
    mpu.y = status
    do_rts()

def cio_call():
    ba = mem[0x344] | (mem[0x345] << 8)
    s = ''
    while mem[ba] != 0x9B and len(s) < 120:
        s += chr(mem[ba]); ba += 1
    printed.append(s)
    mpu.y = 1
    do_rts()

def do_rts():
    lo = mem[0x100 + ((mpu.sp + 1) & 0xFF)]
    hi = mem[0x100 + ((mpu.sp + 2) & 0xFF)]
    mpu.sp = (mpu.sp + 2) & 0xFF
    mpu.pc = ((hi << 8) | lo) + 1

def call(addr, a=0, x=0, y=0, maxstep=8_000_000):
    mpu.a, mpu.x, mpu.y = a, x, y
    mpu.sp = 0xFD
    mem[0x1FE] = (RET - 1) & 0xFF
    mem[0x1FF] = (RET - 1) >> 8
    mpu.pc = addr
    steps = 0
    while mpu.pc != RET:
        if mpu.pc == 0xCFED:
            assert HISIO, 'wywolano $CFED bez patcha HISIO'
            assert mpu.a == 0x28, f'zly dzielnik POKEY: {mpu.a:02X}'
            sio_call(); continue
        if mpu.pc == SIOV:
            assert not HISIO, 'wywolano SIOV mimo patcha HISIO'
            sio_call(); continue
        if mpu.pc == CIOV: cio_call(); continue
        if mpu.pc in (VSET, VPOP): do_rts(); continue
        mpu.step(); steps += 1
        assert steps < maxstep, f'petla nieskonczona @ {mpu.pc:04X}'
    return mpu.a

def iname(s):
    if '.' in s: b, e = s.split('.', 1)
    else: b, e = s, ''
    b = b.replace('*', '?' * 8)[:8]
    e = e.replace('*', '?' * 3)[:3]
    return (b.ljust(8) + e.ljust(3)).upper()

def setname(s, at=K_NAME):
    for i, ch in enumerate(iname(s)):
        mem[at+i] = ord(ch)

def setpath(s):
    for i, ch in enumerate(s): mem[K_PATH+i] = ord(ch)
    mem[K_PATH+len(s)] = 0

def kcall(fn, unit=1, name=None, xname=None, path=None, mode=None,
          scan=0xA0, fid=None, addpos=None, bytbuf=None):
    mem[K_DEV] = 0x30 | unit
    if name is not None: setname(name)
    if xname is not None: setname(xname, K_XNAME)
    if path is not None: setpath(path)
    if mode is not None: mem[K_MODE] = mode
    mem[K_SCAN] = scan
    mem[K_ATTR] = 0
    if fid is not None: mem[K_FID] = fid
    if addpos is not None:
        mem[K_ADDPOS] = addpos & 0xFF
        mem[K_ADDPOS+1] = (addpos >> 8) & 0xFF
        mem[K_ADDPOS+2] = (addpos >> 16) & 0xFF
    if bytbuf is not None:
        mem[K_BYTBUF] = bytbuf & 0xFF
        mem[K_BYTBUF+1] = bytbuf >> 8
    mem[K_MEMREIX] = 0
    st = call(lab('devmain'), y=fn)
    return st if st < 128 else st - 256

def kopen(name, mode, unit=1, path='', scan=0xA0):
    st = kcall(9, unit=unit, name=name, path=path, mode=mode, scan=scan)
    if st < 0: return st, None
    fid = mem[K_FID]
    mem[DEVIDX + fid] = 0x42
    return st, fid

def kclose(fid):
    st = kcall(7, fid=fid)
    mem[DEVIDX + (fid & 15)] = 0xFF
    return st

def kwrite(fid, data, at=0x9000):
    for i, b in enumerate(data): mem[at+i] = b
    return kcall(1, fid=fid, addpos=at, bytbuf=len(data))

def kread(fid, n, at=0x9800):
    st = kcall(0, fid=fid, addpos=at, bytbuf=n)
    got = mem[K_BYTBUF] | (mem[K_BYTBUF+1] << 8)
    return st, bytes(mem[at:at+got])

def dentry():
    return bytes(mem[K_DENTRY:K_DENTRY+23])

def dename(e):
    return e[6:14].decode('latin1') + '.' + e[14:17].decode('latin1')

fails = 0
def check(cond, what):
    global fails
    print(('  OK ' if cond else '  BLAD ') + what)
    if not cond: fails += 1

print('--- weryfikacja dekodowania (py65) ---')
dis = Disassembler(mpu)
records = []
class TR(sdxasm.Asm):
    def stmt(self, body, ln, pass2):
        start = (self.cur.kind, len(self.cur.out) if self.cur.kind in ('R','X') else self.pc)
        super().stmt(body, ln, pass2)
        if pass2:
            op = body.split(None, 1)[0].lower()
            if op != 'dta':
                end = len(self.cur.out) if self.cur.kind in ('R','X') else self.pc
                records.append((start, op, end - start[1]))
t = TR()
assert t.assemble(open(SRC, encoding='utf-8').readlines())
bad = 0
for (kind, off), op, size in records:
    addr = RB + off if kind == 'R' else (XB + off if kind == 'X' else off)
    length, text = dis.instruction_at(addr)
    mnem = text.split()[0].lower()
    if mnem != op or length != size:
        bad += 1
        if bad < 5: print(f'  ROZNICA @{addr:04X}: {op}/{size} vs {text!r}/{length}')
check(bad == 0, f'{len(records)} instrukcji zdekodowanych zgodnie')

HISIO = os.environ.get('HISIO') == '1'
if HISIO:
    for i, ch in enumerate('Hias 1.33 230101'):
        mem[0xCFF0 + i] = ord(ch)
    print('(tryb HISIO: sygnatura Hias 1.33, wejscie $CFED)')

print('--- instalacja ---')
mem[SYMS['INSTALL']] = 0
for i in range(32): mem[SYMS['DEVNAME'] + i] = 0x20
mem[SYMS['DEVSPEC'] - 1] = 8
for i in range(8): mem[SYMS['DEVSPEC'] + i] = 0
mem[SYMS['COMTAB2'] - 1] = 0x3F
mem[SYMS['EXTENDED'] + 1] = 1
mem[SYMS['EXTENDED'] + 3] = 2
for i in range(16): mem[DEVIDX + i] = 0xFF
call(entry)
dn = bytes(mem[SYMS['DEVNAME']:SYMS['DEVNAME']+32]).decode('latin1')
check('SDC' in dn, f'DEVNAME zawiera SDC: {dn!r}')
dix = dn.index('SDC') // 4
vec = mem[0x750 + dix*2] | (mem[0x751 + dix*2] << 8)
check(vec == lab('devmain'), f'dev_vector -> devmain ({vec:04X})')
check(mem[SYMS['COMTAB2'] - 1] == 0x3F | (1 << dix), 'mikrobufory wlaczone')
check(mem[SYMS['DEVSPEC'] + dix] == 0, 'DEVSPEC = 0')
check(mem[SYMS['INSTALL']] == 0xFF, 'dec INSTALL wykonany')
check(any('fw 3.3' in s for s in printed), f'komunikaty (z wersja fw): {printed}')
mem[lab('nslots')] = 4   # komplet slotow na testy funkcjonalne (domyslnie /M1)

print('--- mkdir / chdir / cwd ---')
check(kcall(14, name='GRY', path='') == 1, 'MKDIR GRY')
check(sd.find(sd.root, 'GRY') is not None, 'katalog na karcie')
check(kcall(14, name='GRY', path='') == -105, 'MKDIR GRY ponownie -> 151')
check(kcall(16, path='GRY') == 1, 'CHDIR GRY')
check(kcall(17) == 1, 'GETCWD')
cwd = ''
i = K_PATH
while mem[i]: cwd += chr(mem[i]); i += 1
check(cwd == 'GRY', f'cwd = GRY: {cwd!r}')

print('--- zapis i odczyt pliku (w GRY) ---')
st, fid = kopen('TEST.TXT', 8)
check(st == 1, f'open 8: {st}')
payload = bytes((i * 3 + 7) & 0xFF for i in range(300))
check(kwrite(fid, payload) == 1, 'write 300B')
check(kclose(fid) == 1, 'close')
gry = sd.find(sd.root, 'GRY')
f = sd.find(gry, 'TEST.TXT')
check(f is not None and bytes(f.data) == payload, 'zawartosc na karcie')
st, fid = kopen('TEST.TXT', 4)
check(st == 1, 'open 4')
check(kcall(4, fid=fid) == 1 and (mem[K_ADDPOS] | (mem[K_ADDPOS+1]<<8)) == 300,
      'kd_gtlen = 300')
st, d1 = kread(fid, 100)
st2, d2 = kread(fid, 100)
st3, d3 = kread(fid, 200)
check(st == 1 and st2 == 1 and st3 == 3 and d1+d2+d3 == payload,
      f'odczyt 100+100+200(=100) = 1:1, koniec ze statusem 3 ({st3})')
st, _ = kread(fid, 10)
check(st == -120, f'EOF -> 136: {st}')
check(kclose(fid) == 1, 'close')

print('--- dwa pliki naraz (scenariusz COPY) ---')
st, fsrc = kopen('TEST.TXT', 4)
st2, fdst = kopen('KOPIA.TXT', 8)
check(st == 1 and st2 == 1 and fsrc != fdst, f'dwa uchwyty: {fsrc},{fdst}')
while True:
    st, chunk = kread(fsrc, 64)
    if st < 0: break
    st2 = kwrite(fdst, chunk, at=0x9400)
    assert st2 == 1, st2
check(kclose(fsrc) == 1 and kclose(fdst) == 1, 'zamkniecie obu')
k = sd.find(gry, 'KOPIA.TXT')
check(k is not None and bytes(k.data) == payload, 'kopia 1:1 przez dwa uchwyty')

print('--- pozycjonowanie ---')
st, fid = kopen('TEST.TXT', 12)
check(st == 1, 'open 12')
check(kcall(2, fid=fid, addpos=100) == 1, 'kd_pos 100')
check(kwrite(fid, b'\xEE') == 1, 'zapis 1B')
check(kcall(3, fid=fid) == 1 and mem[K_ADDPOS] == 101, 'kd_gtpos = 101')
check(kclose(fid) == 1, 'close')
check(f.data[100] == 0xEE, 'bajt po seeku')
st, fid = kopen('TEST.TXT', 4)
check(kcall(2, fid=fid, addpos=301) == -90, 'kd_pos za koncem (odczyt) -> 166')
kclose(fid)

print('--- strumien katalogu (DIR) ---')
sd.add(gry, 'PODKAT', 1)
st, fid = kopen('*.*', 0x14, path='>', scan=0)
check(st == 1, f'open $14 korzen: {st}')
hdr = dentry()
check(hdr[0] == 0x28 and hdr[6:14] == b'SIO2SD  ', f'naglowek: {hdr[6:14]!r}')
st, blob = kread(fid, 23 * 8)
n = len(blob) // 23
ents = [blob[i*23:(i+1)*23] for i in range(n)]
names = [dename(e) for e in ents]
check(any('GRY' in x for x in names), f'wpis GRY: {names}')
check(ents[0][0] & 0x20 and ents[0][6:9] == b'GRY', 'GRY jako podkatalog')
st2, _ = kread(fid, 23)
check(st2 == -120, f'EOF strumienia: {st2}')
check(kclose(fid) == 1, 'close')

print('--- kd_first / kd_next z maska ---')
st = kcall(10, name='BRAK.XXX', path='>GRY', scan=0xA0)
mem[DEVIDX + mem[K_FID]] = 0x42
check(st == -86, f'kd_first bez dopasowania -> 170: {st}')
check(kcall(6, fid=mem[K_FID]) == -120, 'kd_next po pustym -> 136')
kclose(mem[K_FID])
st = kcall(10, name='*.TXT', path='>GRY', scan=0xA0)
fid = mem[K_FID]
mem[DEVIDX+fid] = 0x42
check(st == 1, f'kd_first: {st}')
found = [dename(dentry())]
while True:
    st = kcall(6, fid=fid)
    if st != 1:
        break
    found.append(dename(dentry()))
check(st == -120, f'koniec enumeracji = 136: {st}')
check(sorted(x for x in found) == ['KOPIA   .TXT', 'TEST    .TXT'],
      f'maska *.TXT: {found}')
check(kclose(fid) == 1, 'close')

print('--- dlugie nazwy (~NNN) ---')
lf = sd.add(sd.root, 'Very Long File Name 2024.atr', 2, b'ATARI!' * 10)
st = kcall(10, name='*.*', path='>', scan=0xA0)
fid = mem[K_FID]; mem[DEVIDX+fid] = 0x42
mapped = [dename(dentry())]
while kcall(6, fid=fid) == 1:
    mapped.append(dename(dentry()))
kclose(fid)
tn = [x for x in mapped if '_00' in x]
check(len(tn) == 1, f'jedna nazwa z _NNN: {mapped}')
short = tn[0].replace(' ', '')
st, fid = kopen(short, 4, path='>')
check(st == 1, f'otwarcie {short}: {st}')
st, data = kread(fid, 100)
check(data == b'ATARI!' * 10, 'odczyt pliku o dlugiej nazwie')
kclose(fid)

print('--- rename / delete ---')
check(kcall(11, name='KOPIA.TXT', xname='ARCH.BAK', path='>GRY') == 1, 'RENAME')
check(sd.find(gry, 'ARCH.BAK') is not None, 'nowa nazwa na karcie')
check(kcall(11, name='KOPIA.TXT', xname='X.Y', path='>GRY') == -86, 'RENAME brak -> 170')
sd.add(gry, 'A1.TMP', 2, b'x')
sd.add(gry, 'A2.TMP', 2, b'y')
check(kcall(12, name='*.TMP', path='>GRY') == 1, 'DELETE *.TMP')
check(not any(c.name.endswith('.TMP') for c in gry.children), 'skasowane')
check(kcall(12, name='*.TMP', path='>GRY') == -86, 'DELETE znowu -> 170')

print('--- rmdir / sciezki ---')
check(kcall(15, name='GRY', path='>') == -89, 'RMDIR niepusty -> 167')
check(kcall(15, name='PODKAT', path='>GRY') == 1, 'RMDIR GRY>PODKAT')
check(sd.find(gry, 'PODKAT') is None, 'podkatalog usuniety')
check(kcall(16, path='>') == 1, 'CHDIR > (korzen)')
kcall(17)
check(mem[K_PATH] == 0, 'cwd = korzen')
check(kcall(16, path='GRY') == 1, 'CHDIR GRY')
check(kcall(16, path='..') == 1, 'CHDIR ..')
kcall(17)
check(mem[K_PATH] == 0, 'cwd = korzen po ..')
check(kcall(16, path='BRAK') == -106, 'CHDIR do nieistniejacego -> 150')

print('--- kd_check / bledy ---')
check(kcall(19) == 1 and mem[K_PATH] == 0x21 and mem[K_PATH+5] == 0xFF
      and bytes(mem[K_PATH+14:K_PATH+22]) == b'SIO2SD  ',
      'kd_check: format jadra (wersja $21, wolne, etykieta)')
check(kcall(9, unit=5, name='X.Y', path='', mode=4) == -96, 'unit 5 -> 160')
st, fid = kopen('BRAK.PLK', 4, path='>')
check(st == -86, f'open nieistniejacego -> 170: {st}')
st, fid = kopen('TEST.TXT', 4, path='>GRY')
st2, f2 = kopen('ARCH.BAK', 4, path='>GRY')
st3, f3 = kopen('SIO2SD.SYS', 8, path='>')
st4, f4 = kopen('CZWARTY.PLK', 8, path='>')
st5, f5 = kopen('PIATY.PLK', 8, path='>')
check(st5 == -95, f'5. uchwyt -> 161: {st5}')
for x in (fid, f2, f3, f4):
    kclose(x)
kcall(12, name='SIO2SD.SYS', path='>')
kcall(12, name='CZWARTY.PLK', path='>')

print('--- zmiana katalogu z panelu SIO2SD ---')
st, fid = kopen('TEST.TXT', 4, path='>GRY')
sd.cwd = sd.root
sd.chg = 4
st, data = kread(fid, 50)
check(st == 1 and data == payload[:50], 'odczyt mimo zmiany katalogu z panelu')
kclose(fid)

print()
if fails:
    print(f'NIEPOWODZENIA: {fails}')
    sys.exit(1)
print('WSZYSTKIE TESTY SYMULACYJNE ZALICZONE')
