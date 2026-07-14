#!/usr/bin/env python3
"""
test_boot.py - test bootloadera XEX (altirra/xexboot.bin) pod py65.
Symuluje boot z wirtualnego dysku: sektory 1-3 = loader, 4+ = XEX.
Uzycie: python3 tools/test_boot.py
"""
import sys
from py65.devices.mpu6502 import MPU

loader = open('altirra/xexboot.bin', 'rb').read()
assert len(loader) == 384

INIT_ADDR = 0x3100
RUN_ADDR = 0x5000
xex = bytearray()
xex += b'\xFF\xFF'
segA = bytes([0xA9, 0x77, 0x8D, 0x00, 0x60, 0x60])   # lda #$77 sta $6000 rts
xex += (0x3100).to_bytes(2,'little') + (0x3100+len(segA)-1).to_bytes(2,'little') + segA
xex += (0x2E2).to_bytes(2,'little') + (0x2E3).to_bytes(2,'little')
xex += INIT_ADDR.to_bytes(2, 'little')
xex += b'\xFF\xFF'
segB = bytes(300)
xex += (0x5000).to_bytes(2,'little') + (0x5000+len(segB)-1).to_bytes(2,'little') + segB
xex += (0x2E0).to_bytes(2,'little') + (0x2E1).to_bytes(2,'little')
xex += RUN_ADDR.to_bytes(2, 'little')

sectors = {1: loader[0:128], 2: loader[128:256], 3: loader[256:384]}
for i in range(0, len(xex), 128):
    sectors[4 + i//128] = bytes(xex[i:i+128]).ljust(128, b'\0')

mpu = MPU()
mem = mpu.memory
for i in range(384):
    mem[0x700 + i] = loader[i]
mem[0x709:0x70C] = len(xex).to_bytes(3, 'little')

DSKINV = 0xE453
reads = []

def do_rts():
    lo = mem[0x100 + ((mpu.sp + 1) & 0xFF)]
    hi = mem[0x100 + ((mpu.sp + 2) & 0xFF)]
    mpu.sp = (mpu.sp + 2) & 0xFF
    mpu.pc = ((hi << 8) | lo) + 1

def dskinv():
    sec = mem[0x30A] | (mem[0x30B] << 8)
    buf = mem[0x304] | (mem[0x305] << 8)
    assert mem[0x302] == 0x52 and mem[0x300] == 0x31
    data = sectors.get(sec)
    assert data, f'odczyt nieistniejacego sektora {sec}'
    reads.append(sec)
    for i, b in enumerate(data):
        mem[buf + i] = b
    mpu.y = 1
    mpu.p &= ~0x80
    do_rts()

mpu.pc = 0x706
mpu.sp = 0xFD
init_called = []
steps = 0
while mpu.pc != RUN_ADDR:
    if mpu.pc == DSKINV:
        dskinv(); continue
    if mpu.pc == INIT_ADDR:
        init_called.append(True)
    mpu.step(); steps += 1
    assert steps < 3_000_000, f'petla @ {mpu.pc:04X}'

ok = True
def check(cond, what):
    global ok
    print(('  OK ' if cond else '  BLAD ') + what)
    ok = ok and cond

check(mpu.pc == RUN_ADDR, f'skok do RUNAD ${RUN_ADDR:04X}')
check(bool(init_called), 'INIT segmentu wywolany')
check(mem[0x6000] == 0x77, 'kod INIT wykonany (znacznik w $6000)')
check(bytes(mem[0x3100:0x3100+len(segA)]) == bytes(segA), 'segment A zaladowany')
check(all(mem[0x5000+i] == 0 for i in range(300)), 'segment B zaladowany')
check((mem[0x2E0] | (mem[0x2E1] << 8)) == RUN_ADDR, 'RUNAD ustawiony')
check(sorted(set(reads)) == list(range(4, 4 + (len(xex)+127)//128)),
      f'przeczytano sektory danych: {sorted(set(reads))}')
print()
print('TEST BOOTLOADERA ZALICZONY' if ok else 'NIEPOWODZENIA')
sys.exit(0 if ok else 1)
