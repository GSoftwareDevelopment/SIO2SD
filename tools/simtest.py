#!/usr/bin/env python3
"""
simtest.py - test funkcjonalny SIO2SD.SYS pod symulatorem py65.

Emuluje urzadzenie SIO2SD (fw 3.x) pod wektorem SIOV oraz wywoluje
procedury handlera CIO tak, jak robilby to OS. Testuje:
  - instalacje (parsowanie parametrow, autodetekcje, HATABS, MEMLO, DOSINI),
  - zapis pliku (OPEN 8 + PUT + CLOSE),
  - odczyt (OPEN 4 + GET az do bledu 136, status 3 na ostatnim bajcie),
  - dopisywanie (OPEN 9), tryb mieszany (OPEN 12) + POINT/NOTE,
  - listing katalogu (OPEN 6),
  - XIO: RENAME, DELETE (maska), MKDIR, RMDIR, CHDIR, GETCWD,
  - obsluge bledow (161, 170, 136, 131, 135).

Uzycie: python3 simtest.py SIO2SD.ASM
"""
import os, sys, importlib.util, re
from py65.devices.mpu6502 import MPU

spec = importlib.util.spec_from_file_location('sdxasm', 'tools/sdxasm.py')
sdxasm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdxasm)
BASE = sdxasm.RBASE

lines = open(sys.argv[1], encoding='utf-8').readlines()
A = sdxasm.Asm()
assert A.assemble(lines), A.errors
A.write('SIO2SD.SYS')
mem_img, _blocks, _entry = sdxasm.load_image('SIO2SD.SYS', BASE, {})
code = bytes(A.blocks[0].out)
L = {k: BASE + v for k, (kind, v) in A.labels.items()}

SIOV, CIOV, RET = 0xE459, 0xE456, 0xAA00
DCB = 0x300

# ------------------------------------------------------------ fake SIO2SD
class Obj:
    _id = 1
    def __init__(self, name, typ, parent):
        self.name, self.typ, self.parent = name, typ, parent
        self.data = bytearray()
        self.children = []
        self.oid = Obj._id; Obj._id += 1

class FakeSD:
    def __init__(self, devic=0x73):
        self.devic = devic
        self.root = Obj('', 1, None)
        self.cwd = self.root
        self.mask = '*'
        self.masktypes = 3
        self.enum = []
        self.enumi = 0
        self.open = None
        self.iopos = 0
        self.reg = {self.root.oid: self.root}
        self.log = []

    def add(self, parent, name, typ, data=b''):
        o = Obj(name, typ, parent)
        o.data = bytearray(data)
        parent.children.append(o)
        self.reg[o.oid] = o
        return o

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

    def obj_from54(self, e):
        oid = int.from_bytes(e[48:52], 'little')
        return self.reg.get(oid)

    def name39(self, buf):
        s = bytes(buf[:39]).split(b'\0')[0].decode('ascii', 'replace')
        return s.rstrip(' ')

    # returns (status, data_out) ; data_in given for write commands
    def cmd(self, c, aux1, aux2, data):
        self.log.append((c, aux1, aux2))
        if c == 0x00: return 1, bytes([1])
        if c == 0x11: return 1, bytes([0x33])
        if c == 0x09:
            m = bytes(data).split(b'\0')[0].decode('ascii', 'replace')
            self.mask = m if m else '*'
            self.masktypes = aux1
            return 1, b''
        if c == 0x0A:
            n = len(self.matching())
            return 1, n.to_bytes(2, 'little')
        if c == 0x04:
            if aux2 & 1:
                self.enum = self.matching(); self.enumi = 0
            if self.enumi >= len(self.enum): return 1, bytes(54)
            e = self.entry54(self.enum[self.enumi]); self.enumi += 1
            return 1, e
        if c == 0x20:
            name = self.name39(data)
            base = self.cwd if (aux1 & 1) else self.root
            for ch in base.children:
                if ch.name.lower() == name.lower() and ch.typ == 2:
                    self.open = ch; self.iopos = 0
                    return 1, b''
            if aux1 & 2: return 139, b''
            self.open = self.add(base, name, 2); self.iopos = 0
            return 1, b''
        if c == 0x22:
            return 1, self.iopos.to_bytes(3, 'little')
        if c == 0x23:
            self.iopos = int.from_bytes(bytes(data[:3]), 'little'); return 1, b''
        if c == 0x24:
            if not self.open: return 139, b''
            n = aux1
            out = bytes(self.open.data[self.iopos:self.iopos+n])
            out += bytes(n - len(out))
            self.iopos += n
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
            o = self.obj_from54(data)
            if not o or o.typ != 1: return 139, b''
            self.cwd = o; return 1, b''
        if c == 0x06:
            if self.cwd.parent: self.cwd = self.cwd.parent
            return 1, b''
        if c == 0x07:
            self.cwd = self.root; return 1, b''
        if c == 0x08:
            return 1, self.entry54(self.cwd)
        if c == 0x0B:
            name = self.name39(data)
            for ch in self.cwd.children:
                if ch.name.lower() == name.lower(): return 139, b''
            self.add(self.cwd, name, aux1)
            return 1, b''
        if c == 0x0C:
            o = self.obj_from54(data)
            if not o or o.parent is None: return 139, b''
            if o.typ == 1 and o.children: return 139, b''
            o.parent.children.remove(o); del self.reg[o.oid]
            if self.open is o: self.open = None
            return 1, b''
        if c == 0x0D:
            o = self.obj_from54(data[39:] and bytes(54 * [0])[:0] + bytes(data))
            # data: bytes 0-38 nowa nazwa, 39-53 oryginalne dane obiektu
            o = self.reg.get(int.from_bytes(bytes(data[48:52]), 'little'))
            if not o: return 139, b''
            o.name = self.name39(data)
            return 1, b''
        raise AssertionError(f'nieznana komenda SIO2SD: ${c:02X}')

# ------------------------------------------------------------ maszyna
mpu = MPU()
mem = mpu.memory
for a, b in mem_img.items():
    mem[a] = b

sd = FakeSD(devic=0x73)
printed = []

def sio_call():
    dev = mem[DCB]; unit = mem[DCB+1]; cmd = mem[DCB+2]; st = mem[DCB+3]
    buf = mem[DCB+4] | (mem[DCB+5] << 8)
    ln = mem[DCB+8] | (mem[DCB+9] << 8)
    aux1, aux2 = mem[DCB+10], mem[DCB+11]
    if dev != sd.devic:
        status = 138; out = b''
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
    # przechwyc PUTREC z IOCB0
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

def call(addr, a=0, x=0, y=0, maxstep=2_000_000):
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
        mpu.step(); steps += 1
        assert steps < maxstep, f'petla nieskonczona @ {mpu.pc:04X}'
    return mpu.a, mpu.x, mpu.y

def setname(s, addr=0x8000):
    for i, ch in enumerate(s): mem[addr+i] = ord(ch)
    mem[addr+len(s)] = 0x9B
    mem[0x24] = addr & 0xFF
    mem[0x25] = addr >> 8

def op(mode, name, x=0x10):
    setname(name)
    mem[0x2A] = mode
    a, _, y = call(L['dopen'], x=x)
    return y

def get(x=0x10):
    a, _, y = call(L['dget'], x=x)
    return a, y

def put(b, x=0x10):
    a, _, y = call(L['dput'], a=b, x=x)
    return y

def close(x=0x10):
    a, _, y = call(L['dclose'], x=x)
    return y

def xio(cmd, name, x=0x10):
    setname(name)
    mem[0x22] = cmd
    a, _, y = call(L['dspec'], x=x)
    return y

def read_all(name, expect_err=136):
    y = op(4, name)
    assert y == 1, f'open 4 {name}: {y}'
    out = bytearray()
    while True:
        a, y = get()
        if y == expect_err and y not in (1, 3): break
        assert y in (1, 3), f'get: {y}'
        out.append(a)
        if y == 3:
            a, y = get()
            assert y == 136, f'po ostatnim bajcie: {y}'
            break
    assert close() == 1
    return bytes(out)

fails = 0
def check(cond, what):
    global fails
    print(('  OK ' if cond else '  BLAD ') + what)
    if not cond: fails += 1

# ================================================================= testy
HISIO = os.environ.get('HISIO') == '1'
if HISIO:
    for i, ch in enumerate('Hias 1.33 230101'):
        mem[0xCFF0 + i] = ord(ch)
    print('(tryb HISIO: sygnatura Hias 1.33, wejscie $CFED)')

print('--- instalacja ---')
# srodowisko: SpartaDOS, linia polecen: "G /1"
mem[0x700] = ord('S')
COMTAB = 0x700  # DOSVEC -> $0700 (BUFOFF=+10, LBUF=+63)
mem[0x0A] = COMTAB & 0xFF; mem[0x0B] = COMTAB >> 8
mem[COMTAB + 10] = 0
cmdline = 'G /1\x9b'
for i, ch in enumerate(cmdline): mem[COMTAB + 63 + i] = ord(ch)
mem[0x0C] = 0x11; mem[0x0D] = 0x22      # stary DOSINI
for i in range(0x31A, 0x340): mem[i] = 0
mem[0x31A] = ord('E')                    # zajety wpis E:
call(L['install'])
check(printed and 'SIO2SD' in printed[0], f'baner: {printed[:1]}')
check(any('firmware 3.3' in s for s in printed), f'komunikat fw: {printed}')
check(mem[L['devid']] == 0x73, f'devid=$73 (ID 1 z /1): {mem[L["devid"]]:02X}')
check(mem[L['devltr']] == ord('G'), 'litera G z parametru')
hat = None
for i in range(0x31A, 0x33E, 3):
    if mem[i] == ord('G'): hat = mem[i+1] | (mem[i+2] << 8)
check(hat == L['htab'], f'HATABS -> htab ({hat and hex(hat)})')
check(mem[0x2E7] | (mem[0x2E8] << 8) == L['resend'], 'MEMLO = resend')
check(mem[0x0C] | (mem[0x0D] << 8) == L['reshook'], 'DOSINI = reshook')
check(mem[L['reshook']+1] == 0x11 and mem[L['reshook']+2] == 0x22, 'stary DOSINI podpiety')

print('--- zapis pliku ---')
y = op(8, 'G:TEST.TXT')
check(y == 1, f'open 8: {y}')
payload = bytes((i * 7 + 3) & 0xFF for i in range(300))
okp = all(put(b) == 1 for b in payload)
check(okp, 'put 300 bajtow')
check(close() == 1, 'close')
f = [c for c in sd.root.children if c.name == 'TEST.TXT']
check(len(f) == 1 and bytes(f[0].data) == payload, 'zawartosc pliku na karcie')

print('--- odczyt pliku ---')
data = read_all('G:TEST.TXT')
check(data == payload, f'odczyt 1:1 ({len(data)} bajtow)')

print('--- dopisywanie ---')
y = op(9, 'G:TEST.TXT')
check(y == 1, f'open 9: {y}')
for b in b'ABC': put(b)
check(close() == 1, 'close append')
check(bytes(f[0].data) == payload + b'ABC', 'dopisane 3 bajty')

print('--- tryb 12 + POINT/NOTE ---')
y = op(12, 'G:TEST.TXT')
check(y == 1, f'open 12: {y}')
a, y = get()
check(y == 1 and a == payload[0], 'odczyt 1. bajtu')
mem[0x34C+0x10] = 100; mem[0x34D+0x10] = 0; mem[0x34E+0x10] = 0
check(xio(37, 'G:') == 1, 'POINT 100')
put(0xEE)
mem[0x34C+0x10] = 0; mem[0x34D+0x10] = 0; mem[0x34E+0x10] = 0
check(xio(38, 'G:') == 1, 'NOTE')
check(mem[0x34C+0x10] == 101, f'NOTE=101: {mem[0x34C+0x10]}')
check(xio(39, 'G:') == 1, 'XIO 39 (dlugosc)')
flen = mem[0x34C+0x10] | (mem[0x34D+0x10]<<8) | (mem[0x34E+0x10]<<16)
check(flen == 303, f'dlugosc 303: {flen}')
check(close() == 1, 'close')
check(f[0].data[100] == 0xEE, 'bajt wpisany po POINT')

print('--- bledy ---')
y = op(4, 'G:TEST.TXT')
check(y == 1, 'open 4')
y2 = op(4, 'G:INNY.TXT', x=0x20)
check(y2 == 161, f'drugi open -> 161: {y2}')
a, y2 = call(L['dget'], x=0x20)[0], call(L['dget'], x=0x20)[2]
check(y2 == 133, f'get na cudzym IOCB -> 133: {y2}')
check(put(65) == 135, 'put przy trybie 4 -> 135')
close()
check(op(4, 'G:BRAK.PLK') == 170, 'open nieistniejacego -> 170')
y = op(8, 'G:WO.TXT')
a, y2 = get()
check(y2 == 131, f'get przy trybie 8 -> 131: {y2}')
close()
xio(33, 'G:WO.TXT')

print('--- katalog ---')
sd.add(sd.root, 'GRY', 1)
sd.add(sd.root, 'DEMA', 1)
y = op(6, 'G:*')
check(y == 1, f'open 6: {y}')
listing = bytearray()
while True:
    a, y = get()
    if y == 136: break
    listing.append(a)
    if y == 3: break
close()
txt = listing.decode('latin1')
lines_ = txt.split('\x9b')
check('TEST.TXT 303' in txt, f'linia pliku: {lines_}')
check('GRY <DIR>' in txt, 'linia katalogu')
check('3 WPISOW' in txt, 'stopka')

print('--- XIO: mkdir/chdir/getcwd/rename/delete/rmdir ---')
check(xio(42, 'G:NOWY') == 1, 'MKDIR NOWY')
check(any(c.name == 'NOWY' and c.typ == 1 for c in sd.root.children), 'katalog utworzony')
check(xio(44, 'G:NOWY') == 1, 'CHDIR NOWY')
check(sd.cwd.name == 'NOWY', 'cwd = NOWY')
y = op(8, 'G:W_SRODKU.TXT'); put(0x41); close()
check(any(c.name == 'W_SRODKU.TXT' for c in sd.cwd.children), 'plik w podkatalogu')
check(xio(48, 'G:') == 1, 'GETCWD')
s = ''
i = 0x8000
while mem[i] != 0x9B: s += chr(mem[i]); i += 1
check(s == 'NOWY', f'GETCWD = NOWY: {s!r}')
check(xio(44, 'G:<') == 1, 'CHDIR <')
check(sd.cwd is sd.root, 'cwd = korzen po <')
check(xio(44, 'G:NOWY>..') == 1, 'CHDIR NOWY>..')
check(sd.cwd is sd.root, 'cwd = korzen po ..')
check(xio(32, 'G:TEST.TXT,ZMIENIONY.DAT') == 1, 'RENAME')
check(any(c.name == 'ZMIENIONY.DAT' for c in sd.root.children), 'nowa nazwa jest')
check(not any(c.name == 'TEST.TXT' for c in sd.root.children), 'starej nie ma')
y = op(8, 'G:KASUJ1.TMP'); put(1); close()
y = op(8, 'G:KASUJ2.TMP'); put(2); close()
check(xio(33, 'G:*.TMP') == 1, 'DELETE *.TMP')
check(not any(c.name.endswith('.TMP') for c in sd.root.children), 'pliki skasowane')
check(xio(33, 'G:*.TMP') == 170, 'DELETE ponownie -> 170')
check(xio(44, 'G:NOWY') == 1, 'CHDIR NOWY (2)')
check(xio(33, 'G:W_SRODKU.TXT') == 1, 'DELETE w podkatalogu')
check(xio(44, 'G:') == 1, 'CHDIR "" -> korzen')
check(sd.cwd is sd.root, 'cwd = korzen')
check(xio(43, 'G:NOWY') == 1, 'RMDIR NOWY')
check(not any(c.name == 'NOWY' for c in sd.root.children), 'katalog usuniety')
check(xio(43, 'G:NOWY') == 150, 'RMDIR ponownie -> 150')

print('--- duzy plik (granice buforow) ---')
big = bytes((i ^ (i >> 8)) & 0xFF for i in range(1000))
y = op(8, 'G:DUZY.BIN')
for b in big: put(b)
close()
check(read_all('G:DUZY.BIN') == big, 'zapis/odczyt 1000 bajtow (bufory 128B)')

print('--- reset (DOSINI) ---')
for i in range(0x31A, 0x340): mem[i] = 0
mem[0x2E7] = 0; mem[0x2E8] = 0x07
mem[L['reshook']+1] = L['hi_done'] & 0xFF   # "stary DOSINI" -> rts
mem[L['reshook']+2] = L['hi_done'] >> 8
call(L['reshook'])
hat = None
for i in range(0x31A, 0x33E, 3):
    if mem[i] == ord('G'): hat = mem[i+1] | (mem[i+2] << 8)
check(hat == L['htab'], 'HATABS odtworzone po resecie')
check(mem[0x2E7] | (mem[0x2E8] << 8) == L['resend'], 'MEMLO odtworzone')

print()
if fails:
    print(f'NIEPOWODZENIA: {fails}')
    sys.exit(1)
print('WSZYSTKIE TESTY SYMULACYJNE ZALICZONE')
