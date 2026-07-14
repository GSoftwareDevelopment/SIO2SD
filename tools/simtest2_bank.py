#!/usr/bin/env python3
"""
simtest2.py - test funkcjonalny SDCDEV.SYS (urzadzenie plikowe jadra SDX).
Symuluje loader SDX, jadro (strona 7, dev_index), SIO2SD pod SIOV,
V_setme/V_popme. Uzycie: python3 simtest2.py SDCDEV.ASM
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

class Obj:
    _id = 1
    def __init__(self, name, typ, parent):
        self.name, self.typ, self.parent = name, typ, parent
        self.data = bytearray()
        self.children = []
        self.oid = Obj._id; Obj._id += 1

class FakeSD:
    def __init__(self):
        self.root = Obj('', 1, None)
        self.cwd = self.root
        self.mask, self.masktypes = '*', 3
        self.enum, self.enumi = [], 0
        self.open = None
        self.iopos = 0
        self.reg = {self.root.oid: self.root}
        self.chg = 0

    def add(self, parent, name, typ, data=b''):
        o = Obj(name, typ, parent)
        o.data = bytearray(data)
        parent.children.append(o)
        self.reg[o.oid] = o
        return o

    def find(self, base, name):
        for c in base.children:
            if c.name.lower() == name.lower(): return c
        return None

    def match(self, name):
        rx = re.escape(self.mask).replace(r'\*', '.*')
        return re.fullmatch(rx, name, re.I) is not None

    def matching(self):
        return [c for c in self.cwd.children
                if self.match(c.name) and (c.typ & self.masktypes)]

    def entry54(self, o):
        e = bytearray(54)
        n = o.name.encode('ascii')[:39]
        e[0:len(n)] = n
        e[39] = o.typ
        e[40:44] = o.oid.to_bytes(4, 'little')
        e[44:48] = len(o.data).to_bytes(4, 'little') if o.typ == 2 else b'\0\0\0\0'
        e[48:52] = o.oid.to_bytes(4, 'little')
        return bytes(e)

    def name39(self, buf):
        return bytes(buf[:39]).split(b'\0')[0].decode('ascii', 'replace').rstrip(' ')

    def cmd(self, c, aux1, aux2, data):
        if c == 0x00:
            st = 1 if not self.chg else self.chg
            self.chg = 0
            return 1, bytes([st])
        if c == 0x11: return 1, bytes([0x33])
        if c == 0x09:
            m = bytes(data).split(b'\0')[0].decode('ascii', 'replace')
            self.mask = m if m else '*'
            self.masktypes = aux1
            return 1, b''
        if c == 0x0A:
            return 1, len(self.matching()).to_bytes(2, 'little')
        if c == 0x04:
            if aux2 & 1:
                self.enum = self.matching(); self.enumi = 0
            if self.enumi >= len(self.enum): return 1, bytes(54)
            e = self.entry54(self.enum[self.enumi]); self.enumi += 1
            return 1, e
        if c == 0x20:
            name = self.name39(data)
            base = self.cwd if (aux1 & 1) else self.root
            f = self.find(base, name)
            if f and f.typ == 2:
                self.open = f; self.iopos = 0
                return 1, b''
            if aux1 & 2: return 139, b''
            if f: return 139, b''
            self.open = self.add(base, name, 2); self.iopos = 0
            return 1, b''
        if c == 0x22: return 1, self.iopos.to_bytes(3, 'little')
        if c == 0x23:
            self.iopos = int.from_bytes(bytes(data[:3]), 'little'); return 1, b''
        if c == 0x24:
            if not self.open: return 139, b''
            out = bytes(self.open.data[self.iopos:self.iopos+aux1])
            out += bytes(aux1 - len(out))
            self.iopos += aux1
            return 1, out
        if c == 0x25:
            if not self.open: return 139, b''
            d = self.open.data
            if len(d) < self.iopos: d.extend(bytes(self.iopos - len(d)))
            d[self.iopos:self.iopos+len(data)] = data
            self.iopos += len(data)
            return 1, b''
        if c == 0x26:
            if not self.open: return 139, b''
            return 1, len(self.open.data).to_bytes(3, 'little')
        if c == 0x27:
            if not self.open: return 139, b''
            n = int.from_bytes(bytes(data[:3]), 'little')
            d = self.open.data
            if n < len(d): del d[n:]
            else: d.extend(bytes(n - len(d)))
            return 1, b''
        if c == 0x05:
            oid = int.from_bytes(bytes(data[48:52]), 'little')
            o = self.reg.get(oid)
            if not o or o.typ != 1: return 139, b''
            self.cwd = o; self.chg = 4
            return 1, b''
        if c == 0x06:
            if self.cwd.parent: self.cwd = self.cwd.parent
            self.chg = 4
            return 1, b''
        if c == 0x07:
            self.cwd = self.root; self.chg = 4
            return 1, b''
        if c == 0x08:
            return 1, self.entry54(self.cwd)
        if c == 0x0B:
            name = self.name39(data)
            if self.find(self.cwd, name): return 139, b''
            self.add(self.cwd, name, aux1)
            return 1, b''
        if c == 0x0C:
            oid = int.from_bytes(bytes(data[48:52]), 'little')
            o = self.reg.get(oid)
            if not o or o.parent is None: return 139, b''
            if o.typ == 1 and o.children: return 139, b''
            o.parent.children.remove(o); del self.reg[o.oid]
            if self.open is o: self.open = None
            return 1, b''
        if c == 0x0D:
            oid = int.from_bytes(bytes(data[48:52]), 'little')
            o = self.reg.get(oid)
            if not o: return 139, b''
            o.name = self.name39(data)
            return 1, b''
        raise AssertionError(f'nieznana komenda ${c:02X}')

mpu = MPU()

# --- model banku EXTRAM ---
def _blk2len(path):
    d=open(path,'rb').read(); i=0
    while i<len(d):
        sig=d[i]|(d[i+1]<<8)
        if sig==0xFFFA: en=int.from_bytes(d[i+4:i+6],'little');st=int.from_bytes(d[i+2:i+4],'little');i+=6+(en-st+1)
        elif sig==0xFFFE:
            num=d[i+2];ctrl=d[i+3];ln=int.from_bytes(d[i+6:i+8],'little')
            if num==2: return ln
            i+=8+(0 if ctrl&0x80 else ln)
        elif sig in(0xFFFD,0xFFFB):
            off=3 if sig==0xFFFD else 10; bl=int.from_bytes(d[i+off:i+off+2],'little'); i+=off+2+bl
        else: break
    return 0
EXT_IDX=2
EXT_A=XB
EXT_B=XB+_blk2len('SDCDEV.SYS')
class BankMem(list):
    def __init__(s,n): super().__init__([0]*n); s.bank=0; s.viol=[]; s.chk=False
    def __getitem__(s,a):
        if s.chk and isinstance(a,int) and EXT_A<=a<EXT_B and s.bank!=EXT_IDX:
            s.viol.append(('R',a,s.bank))
        return super().__getitem__(a)
    def __setitem__(s,a,v):
        if s.chk and isinstance(a,int) and EXT_A<=a<EXT_B and s.bank!=EXT_IDX:
            s.viol.append(('W',a,s.bank))
        super().__setitem__(a,v)
mem = BankMem(0x10000)
mpu.memory = mem
for a, b in mem_img.items(): mem[a] = b

sd = FakeSD()
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
    mem.chk = True
    steps = 0
    bankstack = []
    while mpu.pc != RET:
        if mem.chk and EXT_A <= mpu.pc < EXT_B and mem.bank != EXT_IDX:
            mem.viol.append(('X', mpu.pc, mem.bank)); break
        if mpu.pc == VSET:
            bankstack.append(mem.bank); mem.bank = mpu.a; do_rts(); continue
        if mpu.pc == VPOP:
            mem.bank = bankstack.pop() if bankstack else 0; do_rts(); continue
        if mpu.pc == 0xCFED:
            assert HISIO, 'wywolano $CFED bez patcha HISIO'
            assert mpu.a == 0x28, f'zly dzielnik POKEY: {mpu.a:02X}'
            sio_call(); continue
        if mpu.pc == SIOV:
            assert not HISIO, 'wywolano SIOV mimo patcha HISIO'
            sio_call(); continue
        if mpu.pc == CIOV: cio_call(); continue
        mpu.step(); steps += 1
        assert steps < maxstep, f'petla nieskonczona @ {mpu.pc:04X}'
    mem.chk = False
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
mem[SYMS['EXTENDED'] + 1] = 1   # liczba blokow ext programu
mem[SYMS['EXTENDED'] + 3] = 2   # indeks naszego bloku -> ext_m
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

print('--- opcja /M: stan domyslny po instalacji (1 slot) ---')
check(mem[lab('nslots')] == 2, f"domyslnie nslots = 2: {mem[lab('nslots')]}")
# na czas testow funkcjonalnych wlacz komplet slotow (nie rusza fixtury)
mem[lab('nslots')] = 4

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

def reinstall(cmdline):
    """Ponowna instalacja ze wskazana linia polecen CP."""
    mem[SYMS['INSTALL']] = 0
    for nm in ('nslots','i_mode','i_id','i_any','i_try'):
        mem[lab(nm)] = 2 if nm == 'nslots' else 0  # swiezy load (domyslnie /M2)
    for i in range(32): mem[SYMS['DEVNAME'] + i] = 0x20
    mem[SYMS['DEVSPEC'] - 1] = 8
    for i in range(8): mem[SYMS['DEVSPEC'] + i] = 0
    for i in range(16): mem[DEVIDX + i] = 0xFF
    COMTAB = 0x0B00
    mem[0x700] = ord('S')
    mem[0x0A] = COMTAB & 0xFF
    mem[0x0B] = COMTAB >> 8
    mem[COMTAB + 10] = 0
    for i, ch in enumerate(cmdline + chr(0x9B)):
        mem[COMTAB + 63 + i] = ord(ch)
    printed.clear()
    call(entry)

def umap():
    a = lab('umap')
    return [mem[a + i] for i in range(4)]

print('--- instalacja z /F (pierwsze znalezione ID) ---')
reinstall('/F')
check(umap() == [0, 255, 255, 255], f'umap po /F: {umap()}')
check(any('SDC1: gotowe (SIO2SD ID 0)' in x for x in printed),
      f'komunikat /F: {printed}')
check(kcall(19, unit=1) == 1, 'kd_check na SDC1: dziala')
check(kcall(19, unit=2) == -96, 'SDC2: wylaczone -> 160')

print('--- instalacja z /1 (wymuszony ID 1) ---')
reinstall('/1')
check(umap() == [1, 255, 255, 255], f'umap po /1: {umap()}')
check(any('ID 1 nie odpowiada' in x for x in printed),
      f'ostrzezenie o braku ID 1: {printed}')
check(not any('fw' in x for x in printed),
      'bez falszywego komunikatu o firmware')
check(any('SDC1: gotowe (SIO2SD ID 1)' in x for x in printed),
      'zainstalowano mimo braku odpowiedzi')
check(kcall(19, unit=1) == -118, 'kd_check na SDC1 (ID 1, brak) -> 138')
check(kcall(19, unit=2) == -96, 'SDC2: wylaczone -> 160')

print('--- opcja /M1 (jeden slot, limit rownoczesnych otwarc) ---')
reinstall('/M1')
check(mem[lab('nslots')] == 1, f'nslots po /M1 = 1: {mem[lab("nslots")]}')
s1, h1 = kopen('C1.TMP', 8, path='>')
s2, h2 = kopen('C2.TMP', 8, path='>')
check(s1 == 1 and s2 == -95, f'/M1: 1 ok, 2. -> 161: {s1},{s2}')
kclose(h1); kcall(12, name='C1.TMP', path='>')

print('--- opcja /M2 (dwa sloty + trym memlo) ---')
reinstall('/M2')
check(mem[lab('nslots')] == 2, f'nslots po /M2 = 2: {mem[lab("nslots")]}')
s1, h1 = kopen('C1.TMP', 8, path='>')
s2, h2 = kopen('C2.TMP', 8, path='>')
s3, h3 = kopen('C3.TMP', 8, path='>')
check(s1 == 1 and s2 == 1 and s3 == -95, f'/M2: 2 ok, 3. -> 161: {s1},{s2},{s3}')
kclose(h1); kclose(h2)
kcall(12, name='C1.TMP', path='>'); kcall(12, name='C2.TMP', path='>')

print('--- opcja /M4 (bez trymu memlo) ---')
reinstall('/M4')
check(mem[lab('nslots')] == 4, f'nslots po /M4 = 4: {mem[lab("nslots")]}')

print('--- opcja /M9 (bledna cyfra -> domyslne 1) ---')
reinstall('/M9')
check(mem[lab('nslots')] == 2, f'nslots po /M9 = 2 (bledne -> domyslne): {mem[lab("nslots")]}')

print()
if fails:
    print(f'NIEPOWODZENIA: {fails}')
    sys.exit(1)
print('WSZYSTKIE TESTY SYMULACYJNE ZALICZONE')

# --- raport banku ---
print()
if mem.viol:
    from collections import Counter
    c=Counter((k, (a>=EXT_A and a<EXT_B)) for k,a,b in mem.viol)
    print(f'NARUSZENIA BANKU: {len(mem.viol)} (rodzaje: {dict(Counter(k for k,a,b in mem.viol))})')
    for k,a,b in mem.viol[:12]:
        print(f'  {k} @ ${a:04X} przy banku {b}')
else:
    print('BANKI OK: brak dostepu do EXTRAM przy zlym banku')
