#!/usr/bin/env python3
"""Buduje altirra/xexboot.bin (256 bajtow) z tools/xexboot.asm."""
import importlib.util
spec = importlib.util.spec_from_file_location('sdxasm', 'tools/sdxasm.py')
sdxasm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdxasm)

A = sdxasm.Asm()
assert A.assemble(open('tools/xexboot.asm', encoding='utf-8').readlines()), A.errors
blk = A.blocks[0]
assert blk.kind == 'S' and blk.org == 0x700
code = bytes(blk.out)
assert len(code) <= 384, f'loader za dlugi: {len(code)}'
assert not A.fixR and not A.fixS, 'loader musi byc samodzielny'
kind, off = A.labels['xexlen']
assert (kind, off) == ('S', 0x709), f'xexlen pod zlym adresem: {kind} {off:04X}'
out = code.ljust(384, b'\0')
open('altirra/xexboot.bin', 'wb').write(out)
print(f'xexboot.bin: {len(code)} bajtow kodu (384 z dopelnieniem), xexlen @ offset 9')
