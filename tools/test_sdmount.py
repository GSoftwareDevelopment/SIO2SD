#!/usr/bin/env python3
"""
test_sdmount.py - test SDMOUNT.COM pod py65 przeciwko logice serwera.
Uzycie: python3 tools/test_sdmount.py
"""
import os, sys, tempfile, shutil, atexit, importlib.util
from py65.devices.mpu6502 import MPU

spec = importlib.util.spec_from_file_location('sdxasm', 'tools/sdxasm.py')
sdxasm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdxasm)
sys.path.insert(0, 'altirra')
from sio2sd_server import SIO2SDCard, AtrDisk, EmptyDisk

A = sdxasm.Asm()
assert A.assemble(open('SDMOUNT.ASM', encoding='utf-8').readlines()), A.errors
A.write('SDMOUNT.COM')

tmp = tempfile.mkdtemp(prefix='sdmount_')
atexit.register(shutil.rmtree, tmp, True)

def make_atr(path):
    d = bytearray(16 + 720 * 128)
    d[0:2] = (0x0296).to_bytes(2, 'little')
    paras = (720 * 128) // 16
    d[2:4] = (paras & 0xFFFF).to_bytes(2, 'little')
    d[4:6] = (128).to_bytes(2, 'little')
    d[6] = paras >> 16
    open(path, 'wb').write(d)

# baza karty to <tmp>/Atari (jak w oryginalnym SIO2SD) - fikstura i montowanie tam
_atari = os.path.join(tmp, 'Atari')
os.makedirs(_atari)
make_atr(os.path.join(_atari, 'GRA.ATR'))
make_atr(os.path.join(_atari, 'Long Name File.atr'))
open(os.path.join(_atari, 'APP.XEX'), 'wb').write(b'\xFF\xFF\x00\x20\x01\x20AB')
os.makedirs(os.path.join(_atari, 'GRY', 'RPG'))
make_atr(os.path.join(_atari, 'GRY', 'RPG', 'QUEST.ATR'))

card = SIO2SDCard(tmp, devid=0, log=lambda *a: None)

SIOV, CIOV, RET = 0xE459, 0xE456, 0xAA00
DCB = 0x300
COMTAB = 0x0B00

fails = 0
def check(cond, what):
    global fails
    print(('  OK ' if cond else '  BLAD ') + what)
    if not cond: fails += 1

def run(args, forbid_getcwd=False):
    mem_img, blocks, entry = sdxasm.load_image('SDMOUNT.COM', 0x2000, {})
    mpu = MPU()
    mem = mpu.memory
    for a, b in mem_img.items(): mem[a] = b
    mem[0x0A] = COMTAB & 0xFF
    mem[0x0B] = COMTAB >> 8
    mem[COMTAB + 10] = 0
    for i, ch in enumerate(args + chr(0x9B)):
        mem[COMTAB + 63 + i] = ord(ch)
    printed = []

    def do_rts():
        lo = mem[0x100 + ((mpu.sp + 1) & 0xFF)]
        hi = mem[0x100 + ((mpu.sp + 2) & 0xFF)]
        mpu.sp = (mpu.sp + 2) & 0xFF
        mpu.pc = ((hi << 8) | lo) + 1

    def sio_call():
        dev = mem[DCB]; cmd = mem[DCB+2]; st = mem[DCB+3]
        buf = mem[DCB+4] | (mem[DCB+5] << 8)
        ln = mem[DCB+8] | (mem[DCB+9] << 8)
        aux1, aux2 = mem[DCB+10], mem[DCB+11]
        if dev != 0x72:
            status = 138
        elif forbid_getcwd and cmd == 0x08:
            raise AssertionError('SDMOUNT nie powinien wolac getcwd ($08)')
        else:
            data = bytes(mem[buf:buf+ln]) if st == 0x80 else b''
            status, out = card.api(cmd, aux1, aux2, data)
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

    mpu.pc = 0x2000
    mpu.sp = 0xFD
    mem[0x1FE] = (RET - 1) & 0xFF
    mem[0x1FF] = (RET - 1) >> 8
    steps = 0
    while mpu.pc != RET:
        if mpu.pc == SIOV: sio_call(); continue
        if mpu.pc == CIOV: cio_call(); continue
        mpu.step(); steps += 1
        assert steps < 8_000_000, f'petla @ {mpu.pc:04X}'
    return printed

print('--- montowanie ATR ---')
out = run('D2: GRA.ATR')
check(any('Zamontowano' in x for x in out), f'komunikat: {out}')
check(2 in card.drives and isinstance(card.drives[2][0], AtrDisk), 'D2 = AtrDisk')

print('--- lista ---')
out = run('')
check(any(x.startswith('D2: GRA.ATR') for x in out), f'lista: {out}')

print('--- XEX i naped dwucyfrowy ---')
out = run('D12: APP.XEX')
check(any('Zamontowano' in x for x in out), f'komunikat: {out}')
check(12 in card.drives, 'D12 zamontowany')
out = run('')
check(any(x.startswith('D12: APP.XEX') for x in out), f'lista z D12: {out}')

print('--- nazwa mangled ---')
ml = [e for e in card.listing() if e[0].startswith('Long')]
idx = card.listing().index(ml[0])
name = f'LONG_{idx:03d}.ATR'
out = run(f'D3: {name}')
check(any('Zamontowano' in x for x in out), f'{name}: {out}')
check(3 in card.drives, 'D3 zamontowany')

print('--- montowanie ze sciezki ---')
out = run('D5: GRY>RPG>QUEST.ATR')
check(any('Zamontowano' in x for x in out), f'sciezka wzgledna: {out}')
check(5 in card.drives and isinstance(card.drives[5][0], AtrDisk), 'D5 = ATR ze sciezki')
check(os.path.realpath(card.cwd) == os.path.realpath(_atari), 'katalog karty przywrocony po sciezce wzglednej')
card.cwd = os.path.join(_atari, 'GRY')
out = run(r'D6: \GRY\RPG\QUEST.ATR')
check(any('Zamontowano' in x for x in out), f'sciezka bezwzgledna: {out}')
check(6 in card.drives and isinstance(card.drives[6][0], AtrDisk), 'D6 = ATR ze sciezki bezwzglednej')
check(os.path.realpath(card.cwd) == os.path.realpath(_atari), 'sciezka bezwzgledna konczy w korzeniu')
card.cwd = _atari
out = run('D7: GRA.ATR', forbid_getcwd=True)
check(any('Zamontowano' in x for x in out), f'zwykla nazwa bez getcwd: {out}')
check(7 in card.drives and isinstance(card.drives[7][0], AtrDisk), 'D7 = ATR bez getcwd')
out = run('D8: /GRA.ATR', forbid_getcwd=True)
check(any('Zamontowano' in x for x in out), f'sciezka / bez getcwd: {out}')
check(8 in card.drives and isinstance(card.drives[8][0], AtrDisk), 'D8 = ATR ze sciezki /')

print('--- pusty dysk / odlaczanie / brak pliku ---')
out = run('D4: /E')
check(any('pusty dysk' in x for x in out), f'{out}')
check(isinstance(card.drives[4][0], EmptyDisk), 'D4 = EmptyDisk')
out = run('')
check(any('(pusty dysk)' in x for x in out), 'pusty na liscie')
out = run('D2: /D')
check(2 not in card.drives, 'D2 odlaczony')
out = run('D1: BRAK.ATR')
check(any('Nie znaleziono' in x for x in out), f'{out}')
out = run('/1 D5: GRA.ATR')
check(any('nie odpowiada' in x for x in out), f'/1 (brak urzadzenia): {out}')

print()
if fails:
    print(f'NIEPOWODZENIA: {fails}')
    sys.exit(1)
print('TEST SDMOUNT ZALICZONY')
