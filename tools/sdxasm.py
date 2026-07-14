#!/usr/bin/env python3
"""
sdxasm.py - asembler podzbioru skladni MADS generujacy plik SpartaDOS X.

Uzycie: python3 sdxasm.py ZRODLO.ASM WYNIK.SYS [--map]

Obsluguje podzbior uzywany przez SIO2SD.ASM / SDCDEV.ASM:
  - etykiety w kolumnie 1, stale przez '=',
  - 'label smb 'NAZWA''  - symbole SDX (XREF),
  - blk sparta X / blk reloc main / blk update address|symbols / opt / end,
  - dta b/a/c, powtorzenia ':N dta 0',
  - mnemoniki 6502 (tryby: impl, @, #, zp, abs, abs,X, abs,Y, (zp),Y, (abs)).

Format wyjsciowy wg SDX450 Programming Guide, rozdz. 2:
  blok $FFFA (stale adresy), blok $FFFE (relokowalny, asemblowany od 0,
  pole offset=0), fix-upy $FFFD (baza = blok 1/2), symbole $FFFB.

Bloki relokowalne:
  - 'blk reloc main' - blok 1, pamiec glowna (indeks $00),
  - 'blk reloc ext'  - blok 2, pamiec rozszerzona programu (indeks $04).
Fix-upy do bloku glownego maja baze 1, do rozszerzonego baze 2; strumien
wskaznikow przelacza blok docelowy kodem $FE (1=glowny, 2=ext), a slowa
w blokach absolutnych ($FFFA) - kodem $FD (adres bezwzgledny).
"""
import sys, re

OPS = {
 'lda': {'imm':0xA9,'zp':0xA5,'zpx':0xB5,'abs':0xAD,'abx':0xBD,'aby':0xB9,'izx':0xA1,'izy':0xB1},
 'ldx': {'imm':0xA2,'zp':0xA6,'abs':0xAE,'aby':0xBE},
 'ldy': {'imm':0xA0,'zp':0xA4,'abs':0xAC,'abx':0xBC},
 'sta': {'zp':0x85,'zpx':0x95,'abs':0x8D,'abx':0x9D,'aby':0x99,'izx':0x81,'izy':0x91},
 'stx': {'zp':0x86,'abs':0x8E},
 'sty': {'zp':0x84,'abs':0x8C},
 'adc': {'imm':0x69,'zp':0x65,'abs':0x6D,'abx':0x7D,'aby':0x79,'izy':0x71},
 'sbc': {'imm':0xE9,'zp':0xE5,'abs':0xED,'abx':0xFD,'aby':0xF9,'izy':0xF1},
 'cmp': {'imm':0xC9,'zp':0xC5,'abs':0xCD,'abx':0xDD,'aby':0xD9,'izy':0xD1},
 'cpx': {'imm':0xE0,'zp':0xE4,'abs':0xEC},
 'cpy': {'imm':0xC0,'zp':0xC4,'abs':0xCC},
 'and': {'imm':0x29,'zp':0x25,'abs':0x2D,'abx':0x3D,'aby':0x39},
 'ora': {'imm':0x09,'zp':0x05,'abs':0x0D,'abx':0x1D,'aby':0x19},
 'eor': {'imm':0x49,'zp':0x45,'abs':0x4D,'abx':0x5D,'aby':0x59},
 'inc': {'zp':0xE6,'abs':0xEE,'abx':0xFE},
 'dec': {'zp':0xC6,'abs':0xCE,'abx':0xDE},
 'asl': {'acc':0x0A,'zp':0x06,'abs':0x0E},
 'lsr': {'acc':0x4A,'zp':0x46,'abs':0x4E},
 'rol': {'acc':0x2A,'zp':0x26,'abs':0x2E},
 'ror': {'acc':0x6A,'zp':0x66,'abs':0x6E},
 'jmp': {'abs':0x4C,'ind':0x6C},
 'jsr': {'abs':0x20},
 'bit': {'zp':0x24,'abs':0x2C},
}
IMPL = {'rts':0x60,'pha':0x48,'pla':0x68,'php':0x08,'plp':0x28,'inx':0xE8,
 'iny':0xC8,'dex':0xCA,'dey':0x88,'clc':0x18,'sec':0x38,'cli':0x58,'sei':0x78,
 'tax':0xAA,'txa':0x8A,'tay':0xA8,'tya':0x98,'tsx':0xBA,'txs':0x9A,'nop':0xEA,
 'clv':0xB8,'cld':0xD8,'sed':0xF8,'brk':0x00}
BRANCH = {'bpl':0x10,'bmi':0x30,'bvc':0x50,'bvs':0x70,'bcc':0x90,'bcs':0xB0,
 'bne':0xD0,'beq':0xF0}

RBASE = 0x1000   # wewnetrzna baza asemblacji bloku glownego (indeks 0)
XBASE = 0x8000   # wewnetrzna baza asemblacji bloku rozszerzonego (indeks 2)

class Block:
    def __init__(self, kind, org, num=None, ctrl=0):
        self.kind = kind          # 'S' sparta / 'R' reloc main / 'X' reloc ext
        self.org = org
        self.num = num            # numer bloku (1=glowny, 2=ext) dla $FFFE
        self.ctrl = ctrl          # bajt kontrolny: indeks pamieci ($00 / $02)
        self.out = bytearray()

class Asm:
    def __init__(self):
        self.consts = {}
        self.labels = {}          # name -> (kind, value); kind: 'R','S','SMB'
        self.smbname = {}
        self.errors = []

    def err(self, ln, msg):
        self.errors.append(f'linia {ln}: {msg}')

    def term(self, tok):
        tok = tok.strip()
        if not tok: raise ValueError('pusty skladnik')
        if tok.startswith('$'): return int(tok[1:], 16), None
        if tok[0] == "'" and tok.endswith("'") and len(tok) == 3:
            return ord(tok[1]), None
        if tok.isdigit(): return int(tok), None
        key = tok.lower()
        if key in self.consts: return self.consts[key], None
        if key in self.labels:
            kind, val = self.labels[key]
            if kind == 'R':  return RBASE + val, 'R'
            if kind == 'X':  return XBASE + val, 'X'
            if kind == 'S':  return val, None
            return 0, ('SMB', self.smbname[key])
        raise ValueError(f'niezdefiniowany symbol: {tok}')

    def expr(self, s, ln, pass2):
        s = s.strip()
        toks, sign, cur, inq = [], 1, '', False
        for ch in s:
            if ch == "'": inq = not inq; cur += ch
            elif ch in '+-' and not inq and cur:
                toks.append((sign, cur)); sign = 1 if ch == '+' else -1; cur = ''
            else: cur += ch
        toks.append((sign, cur))
        val, tags = 0, []
        for sg, tk in toks:
            try:
                v, t = self.term(tk)
            except ValueError:
                if pass2: raise
                v, t = RBASE, 'R'
            val += sg * v
            if t is not None:
                if sg != 1: raise ValueError(f'ujemna relokacja: {s}')
                tags.append(t)
        if len(tags) > 1: raise ValueError(f'nierelokowalne wyrazenie: {s}')
        return val & 0xFFFF, (tags[0] if tags else None)

    def assemble(self, lines):
        for pass2 in (False, True):
            self.blocks = []
            self.cur = None
            self.fixups = []          # (base_block, target, pos)
            self.fixS = {}            # sym -> [(target, pos)]
            for idx, raw in enumerate(lines, 1):
                try:
                    self.line(raw, idx, pass2)
                except ValueError as e:
                    if pass2: self.err(idx, str(e))
            if self.errors: return False
        return True

    @property
    def pc(self):
        return self.cur.org + len(self.cur.out)

    def line(self, raw, ln, pass2):
        s, inq = '', False
        for ch in raw.rstrip('\n'):
            if ch == "'": inq = not inq
            if ch == ';' and not inq: break
            s += ch
        if not s.strip(): return
        label = None
        if not s[0] in ' \t':
            parts = s.split(None, 1)
            label = parts[0]
            s = parts[1] if len(parts) > 1 else ''
        body = s.strip()

        if body.startswith('=') or body.lower().startswith('equ '):
            rhs = body[1:] if body.startswith('=') else body[4:]
            val, tag = self.expr(rhs, ln, pass2)
            if tag: raise ValueError('stala nie moze byc relokowalna')
            self.consts[label.lower()] = val
            return
        m = re.match(r"^smb\s+'(.+)'$", body, re.I)
        if m:
            name = m.group(1)
            if len(name) > 8: raise ValueError('symbol > 8 znakow')
            self.labels[label.lower()] = ('SMB', 0)
            self.smbname[label.lower()] = name.upper().ljust(8)
            return

        if label:
            key = label.lower()
            if key in self.consts: raise ValueError(f'etykieta {label} juz jest stala')
            if self.cur is None: raise ValueError('etykieta poza blokiem')
            if self.cur.kind == 'R': newv = ('R', len(self.cur.out))
            elif self.cur.kind == 'X': newv = ('X', len(self.cur.out))
            else: newv = ('S', self.pc)
            if pass2 and key in self.labels and self.labels[key] != newv \
               and self.labels[key][0] != 'SMB':
                self.err(ln, f'niestabilna etykieta {label}')
            if not pass2 and key in self.labels and self.labels[key][0] != 'SMB':
                raise ValueError(f'podwojna etykieta: {label}')
            if self.labels.get(key, (None,))[0] != 'SMB':
                self.labels[key] = newv
        if not body: return

        low = body.lower()
        if low.startswith('opt') or low == 'end': return
        if low.startswith('blk'):
            w = low.split()
            if w[1].startswith('s'):
                self.cur = Block('S', self.expr(w[2], ln, pass2)[0])
                self.blocks.append(self.cur)
            elif w[1].startswith('r'):
                if len(w) > 2 and w[2].startswith('e'):
                    self.cur = Block('X', XBASE, num=2, ctrl=0x04)
                else:
                    self.cur = Block('R', RBASE, num=1, ctrl=0x00)
                self.blocks.append(self.cur)
            elif w[1].startswith('u'):
                pass
            else:
                raise ValueError(f'nieobslugiwany blk: {body}')
            return
        if low.startswith(':'):
            m = re.match(r':(\d+)\s+(.*)', body)
            if not m: raise ValueError('zla skladnia :N')
            for _ in range(int(m.group(1))): self.stmt(m.group(2), ln, pass2)
            return
        self.stmt(body, ln, pass2)

    def fixpos(self):
        if self.cur.kind == 'R': return (1, len(self.cur.out))
        if self.cur.kind == 'X': return (2, len(self.cur.out))
        return ('abs', self.pc)

    def emit(self, *bs):
        self.cur.out.extend(bs)

    def emitword(self, val, tag):
        tgt, pos = self.fixpos()
        if tag == 'R':
            self.fixups.append((1, tgt, pos)); val -= RBASE
        elif tag == 'X':
            self.fixups.append((2, tgt, pos)); val -= XBASE
        elif isinstance(tag, tuple):
            self.fixS.setdefault(tag[1], []).append((tgt, pos))
        self.emit(val & 0xFF, (val >> 8) & 0xFF)

    def stmt(self, body, ln, pass2):
        if self.cur is None: raise ValueError('kod poza blokiem')
        parts = body.split(None, 1)
        op = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ''

        if op == 'dta': self.dta(arg, ln, pass2); return
        if op in IMPL:
            if arg: raise ValueError(f'{op} nie przyjmuje argumentu')
            self.emit(IMPL[op]); return
        if op in BRANCH:
            val, tag = self.expr(arg, ln, pass2)
            here = self.pc
            delta = val - (here + 2)
            if pass2 and not (-128 <= delta <= 127):
                self.err(ln, f'skok {op} {arg} poza zasiegiem ({delta})')
            if pass2 and tag in ('R', 'X') and \
               not (tag == 'R' and self.cur.kind == 'R') and \
               not (tag == 'X' and self.cur.kind == 'X'):
                self.err(ln, 'skok wzgledny miedzy blokami')
            self.emit(BRANCH[op], delta & 0xFF); return
        if op not in OPS: raise ValueError(f'nieznany rozkaz: {op}')
        modes = OPS[op]

        if arg == '@': self.emit(modes['acc']); return
        if arg.startswith('#'):
            val, tag = self.expr(arg[1:], ln, pass2)
            if tag: raise ValueError('relokowalna wartosc natychmiastowa')
            if pass2 and not (0 <= val <= 255): raise ValueError(f'poza bajtem: {arg}')
            self.emit(modes['imm'], val & 0xFF); return
        m = re.match(r'^\(([^)]+)\)\s*,\s*[yY]$', arg)
        if m:
            val, tag = self.expr(m.group(1), ln, pass2)
            if tag or val > 0xFF: raise ValueError('(zp),y wymaga strony zerowej')
            self.emit(modes['izy'], val); return
        m = re.match(r'^\(([^)]+)\)$', arg)
        if m:
            val, tag = self.expr(m.group(1), ln, pass2)
            self.emit(modes['ind']); self.emitword(val, tag); return
        idx = None
        m = re.match(r'^(.*),\s*([xyXY])$', arg)
        if m: arg, idx = m.group(1).strip(), m.group(2).lower()
        val, tag = self.expr(arg, ln, pass2)
        if tag is None and val <= 0xFF:
            key = 'zp' if idx is None else ('zpx' if idx == 'x' else 'zpy')
            if key in modes: self.emit(modes[key], val); return
        key = 'abs' if idx is None else ('abx' if idx == 'x' else 'aby')
        if key not in modes: raise ValueError(f'{op}: brak trybu {key}')
        self.emit(modes[key]); self.emitword(val, tag)

    def dta(self, arg, ln, pass2):
        items, cur, inq, par = [], '', False, 0
        for ch in arg:
            if ch == "'": inq = not inq
            if ch == '(' and not inq: par += 1
            if ch == ')' and not inq: par -= 1
            if ch == ',' and not inq and par == 0:
                items.append(cur); cur = ''
            else: cur += ch
        if cur.strip(): items.append(cur)
        for it in items:
            it = it.strip()
            m = re.match(r"^c'(.*)'$", it)
            if m:
                for ch in m.group(1): self.emit(ord(ch))
                continue
            m = re.match(r'^a\((.*)\)$', it, re.I)
            if m:
                val, tag = self.expr(m.group(1), ln, pass2)
                self.emitword(val, tag); continue
            m = re.match(r'^b\((.*)\)$', it, re.I)
            if m: it = m.group(1)
            val, tag = self.expr(it, ln, pass2)
            if tag or val > 0xFF: raise ValueError(f'dta: bajt poza zakresem: {it}')
            self.emit(val)

    def pointer_stream(self, entries):
        # entries: [(target, pos)], target: 1=glowny, 2=ext, 'abs'=$FFFA
        out = bytearray()
        for tgt in (1, 2):
            poss = sorted(p for t, p in entries if t == tgt)
            if poss:
                out += bytes([0xFE, tgt])
                prev = 0
                for off in poss:
                    delta = off - prev
                    while delta > 0xFB:
                        out.append(0xFF); delta -= 0xFA
                    out.append(delta)
                    prev = off
        for ad in sorted(p for t, p in entries if t == 'abs'):
            out += bytes([0xFD]) + ad.to_bytes(2, 'little')
        out.append(0xFC)
        return out

    def write(self, path):
        data = bytearray()
        for b in self.blocks:
            if b.kind == 'S':
                data += bytes([0xFA, 0xFF])
                data += b.org.to_bytes(2, 'little')
                data += (b.org + len(b.out) - 1).to_bytes(2, 'little')
                data += b.out
            else:
                data += bytes([0xFE, 0xFF, b.num, b.ctrl, 0x00, 0x00])
                data += len(b.out).to_bytes(2, 'little')
                data += b.out
        for base in sorted(set(bb for bb, t, p in self.fixups)):
            entries = [(t, p) for bb, t, p in self.fixups if bb == base]
            body = self.pointer_stream(entries)
            data += bytes([0xFD, 0xFF, base]) + len(body).to_bytes(2, 'little') + body
        for sym in sorted(self.fixS):
            body = self.pointer_stream(self.fixS[sym])
            data += bytes([0xFB, 0xFF]) + sym.encode('ascii')
            data += len(body).to_bytes(2, 'little') + body
        with open(path, 'wb') as f:
            f.write(data)
        return sum(len(b.out) for b in self.blocks), len(self.fixups), \
               sum(len(v) for v in self.fixS.values())

def load_image(path, memlo, symbols):
    """Symulacja loadera SDX: FFFA/FFFE/FFFD/FFFB. Zwraca (mem, blocks, entry)."""
    data = open(path, 'rb').read()
    mem, i = {}, 0
    blocks = {}
    entry = None
    while i < len(data):
        sig = data[i] | (data[i+1] << 8)
        if sig == 0xFFFA:
            start = int.from_bytes(data[i+2:i+4], 'little')
            end = int.from_bytes(data[i+4:i+6], 'little')
            n = end - start + 1
            for j in range(n): mem[start+j] = data[i+6+j]
            if entry is None: entry = start
            i += 6 + n
        elif sig == 0xFFFE:
            num, ctrl = data[i+2], data[i+3]
            ln = int.from_bytes(data[i+6:i+8], 'little')
            addr = memlo
            blocks[num] = addr
            if ctrl & 0x80:
                memlo += ln; i += 8
            else:
                for j in range(ln): mem[addr+j] = data[i+8+j]
                memlo += ln; i += 8 + ln
            if entry is None: entry = addr
        elif sig in (0xFFFD, 0xFFFB):
            if sig == 0xFFFD:
                base = blocks[data[i+2]]
                blen = int.from_bytes(data[i+3:i+5], 'little')
                body = data[i+5:i+5+blen]; i += 5 + blen
            else:
                name = data[i+2:i+10].decode('ascii').strip()
                base = symbols[name]
                blen = int.from_bytes(data[i+10:i+12], 'little')
                body = data[i+12:i+12+blen]; i += 12 + blen
            j, cnt = 0, 0
            while j < len(body):
                bb = body[j]
                if bb == 0xFC: j += 1; break
                if bb == 0xFE:
                    cnt = blocks[body[j+1]]; j += 2; continue
                if bb == 0xFF: cnt += 0xFA; j += 1; continue
                if bb == 0xFD:
                    cnt = int.from_bytes(body[j+1:j+3], 'little')
                    j += 3
                else:
                    cnt += bb
                    j += 1
                w = mem.get(cnt, 0) | (mem.get(cnt+1, 0) << 8)
                w = (w + base) & 0xFFFF
                mem[cnt] = w & 0xFF; mem[cnt+1] = w >> 8
            assert j == len(body), 'zly strumien wskaznikow'
        else:
            raise AssertionError(f'nieznany naglowek {sig:04X} @ {i}')
    return mem, blocks, entry

def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    a = Asm()
    if not a.assemble(lines):
        print('BLEDY:'); [print(' ', e) for e in a.errors]
        sys.exit(1)
    n, nr, ns = a.write(dst)
    print(f'OK: {n} bajtow kodu, {nr} relokacji, {ns} odwolan do symboli -> {dst}')
    if '--map' in sys.argv:
        for k, (kind, v) in sorted(a.labels.items(), key=lambda kv: kv[1][1]):
            print(f'  {kind} {v:04X} {k}')

if __name__ == '__main__':
    main()
