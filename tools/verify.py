#!/usr/bin/env python3
"""
verify.py - weryfikacja pliku SDX zbudowanego przez sdxasm.py:
 1) ponowna asemblacja zrodla == plik na dysku,
 2) struktura blokow (FFFA/FFFE/FFFD/FFFB) czytelna dla symulatora loadera,
 3) proba relokacji pod dwa rozne adresy MEMLO - roznice tylko w slowach
    relokowanych i odwolaniach do symboli (osobno dla bloku glownego i EXTRAM),
 4) niezalezna dezasemblacja wszystkich instrukcji dekoderem py65.

Uzycie: python3 tools/verify.py ZRODLO.ASM PLIK.SYS
"""
import sys, importlib.util, tempfile, os
from py65.devices.mpu6502 import MPU
from py65.disassembler import Disassembler

spec = importlib.util.spec_from_file_location('sdxasm', 'tools/sdxasm.py')
sdxasm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdxasm)

src, binpath = sys.argv[1], sys.argv[2]
data = open(binpath, 'rb').read()
lines = open(src, encoding='utf-8').readlines()
A = sdxasm.Asm()
assert A.assemble(lines), A.errors
tmp = tempfile.mktemp(suffix='.sys')
A.write(tmp)
assert open(tmp, 'rb').read() == data, 'plik rozni sie od asemblacji zrodla'
os.remove(tmp)
print('[1] plik zgodny z ponowna asemblacja zrodla')

# dlugosci blokow $FFFE z pliku
def block_lens(d):
    i, lens = 0, {}
    while i < len(d):
        sig = d[i] | (d[i+1] << 8)
        if sig == 0xFFFA:
            st=int.from_bytes(d[i+2:i+4],'little'); en=int.from_bytes(d[i+4:i+6],'little'); i+=6+(en-st+1)
        elif sig == 0xFFFE:
            num,ctrl=d[i+2],d[i+3]; ln=int.from_bytes(d[i+6:i+8],'little'); lens[num]=ln
            i+=8+(0 if ctrl&0x80 else ln)
        elif sig==0xFFFD: bl=int.from_bytes(d[i+3:i+5],'little'); i+=5+bl
        elif sig==0xFFFB: bl=int.from_bytes(d[i+10:i+12],'little'); i+=12+bl
        else: break
    return lens
lens = block_lens(data)

SYMS = {n.strip(): 0xC000 + i*16 for i, n in enumerate(sorted(A.fixS))}
m1, b1, e1 = sdxasm.load_image(binpath, 0x2000, SYMS)
m2, b2, e2 = sdxasm.load_image(binpath, 0x3456, SYMS)
print(f'[2] loader: bloki {[hex(v) for v in b1.values()]}, entry {e1:04X}')

def reloc_offs(num):
    offs = set()
    for base, tgt, p in A.fixups:
        if tgt == num: offs |= {p, p+1}
    for sym, poss in A.fixS.items():
        for tgt, p in poss:
            if tgt == num: offs |= {p, p+1}
    return offs

diff_bad = 0
for num in sorted(lens):
    base1, base2, off_set = b1[num], b2[num], reloc_offs(num)
    for off in range(lens[num]):
        if off in off_set: continue
        if m1.get(base1+off, 0) != m2.get(base2+off, 0): diff_bad += 1
assert diff_bad == 0, f'{diff_bad} bajtow rozni sie poza relokacjami'
print('[3] relokacja pod inny adres: roznice tylko w slowach relokowanych')

mpu = MPU()
for a, b in m1.items(): mpu.memory[a] = b
dis = Disassembler(mpu)
records = []
class TR(sdxasm.Asm):
    def stmt(self, body, ln, pass2):
        start = (self.cur.kind,
                 len(self.cur.out) if self.cur.kind in ('R','X') else self.pc)
        super().stmt(body, ln, pass2)
        if pass2:
            op = body.split(None, 1)[0].lower()
            if op != 'dta':
                end = len(self.cur.out) if self.cur.kind in ('R','X') else self.pc
                records.append((start, op, end - start[1]))
t = TR(); assert t.assemble(lines)
base = {'R': b1.get(1), 'X': b1.get(2)}
bad = 0
for (kind, off), op, sizei in records:
    addr = base[kind] + off if kind in ('R','X') else off
    length, text = dis.instruction_at(addr)
    if text.split()[0].lower() != op or length != sizei:
        print(f'  ROZNICA @{addr:04X}: {op}/{sizei} vs {text!r}/{length}'); bad += 1
assert bad == 0
print(f'[4] py65: {len(records)} instrukcji zdekodowanych identycznie')
print('WERYFIKACJA ZAKONCZONA POMYSLNIE')
