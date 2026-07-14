# Bank-aware harness: waliduje mechanizm trampoliny + bloku EXTRAM.
import importlib.util
from py65.devices.mpu6502 import MPU
spec = importlib.util.spec_from_file_location('sx','sdxasm_ext.py')
sx = importlib.util.module_from_spec(spec); spec.loader.exec_module(sx)

MAIN_LO = 0x2000
EXT_LO  = 0x4000        # okno banku $4000-$7FFF (przypadek PORTB)
EXT_HI  = 0x8000
EXT_IDX = 2
VSET, VPOP = 0x07F1, 0x07F4

def load(path):
    """Loader z osobna przestrzenia EXTRAM. Zwraca (blocks, entry, extrange)."""
    data = open(path,'rb').read()
    mainmem = [0]*0x10000
    extmem  = [0]*(EXT_HI-EXT_LO)
    blocks, entry = {}, None
    mnext = MAIN_LO
    i=0
    while i < len(data):
        sig = data[i]|(data[i+1]<<8)
        if sig==0xFFFA:
            st=int.from_bytes(data[i+2:i+4],'little'); en=int.from_bytes(data[i+4:i+6],'little')
            n=en-st+1
            for j in range(n): mainmem[st+j]=data[i+6+j]
            if entry is None: entry=st
            i+=6+n
        elif sig==0xFFFE:
            num,ctrl=data[i+2],data[i+3]; ln=int.from_bytes(data[i+6:i+8],'little')
            if ctrl & 0x02:                 # blok EXTRAM
                addr=EXT_LO; blocks[num]=addr
                for j in range(ln): extmem[addr-EXT_LO+j]=data[i+8+j]
            else:                            # blok glowny
                addr=mnext; blocks[num]=addr
                for j in range(ln): mainmem[addr+j]=data[i+8+j]
                mnext+=ln
            i+=8+ln
        elif sig in (0xFFFD,0xFFFB):
            if sig==0xFFFD:
                base=blocks[data[i+2]]; bl=int.from_bytes(data[i+3:i+5],'little')
                body=data[i+5:i+5+bl]; i+=5+bl
            else:
                name=data[i+2:i+10].decode('ascii').strip(); base=SYMS[name]
                bl=int.from_bytes(data[i+10:i+12],'little'); body=data[i+12:i+12+bl]; i+=12+bl
            j,cnt=0,0
            def rd(a):
                return extmem[a-EXT_LO] if EXT_LO<=a<EXT_HI else mainmem[a]
            def wr(a,v):
                if EXT_LO<=a<EXT_HI: extmem[a-EXT_LO]=v
                else: mainmem[a]=v
            while j<len(body):
                bb=body[j]
                if bb==0xFC: j+=1; break
                if bb==0xFE: cnt=blocks[body[j+1]]; j+=2; continue
                if bb==0xFF: cnt+=0xFA; j+=1; continue
                if bb==0xFD: cnt=int.from_bytes(body[j+1:j+3],'little'); j+=3
                else: cnt+=bb; j+=1
                w=(rd(cnt)|(rd(cnt+1)<<8))+base & 0xFFFF
                wr(cnt,w&0xFF); wr(cnt+1,w>>8)
        else:
            raise AssertionError(f'naglowek {sig:04X}')
    return blocks, entry, mainmem, extmem

SYMS={'INSTALL':0xD000,'EXTENDED':0xD010}

class BankMem:
    """$4000-$7FFF widzi bank glowny (idx0) lub EXTRAM (idx2) wg self.bank."""
    def __init__(self, mainmem, extmem):
        self.main=mainmem; self.ext=extmem
        self.bank=0; self.viol=[]
    def _win(self,a): return EXT_LO<=a<EXT_HI
    def __len__(self): return 0x10000
    def __getitem__(self,a):
        if isinstance(a,slice): return [self[i] for i in range(a.start or 0, a.stop or 0)]
        if self._win(a):
            if self.bank==EXT_IDX: return self.ext[a-EXT_LO]
            self.viol.append(('read',a,self.bank)); return self.main[a]
        return self.main[a]
    def __setitem__(self,a,v):
        v&=0xFF
        if self._win(a):
            if self.bank==EXT_IDX: self.ext[a-EXT_LO]=v; return
            self.viol.append(('write',a,self.bank)); self.main[a]=v; return
        self.main[a]=v

def run(entry, mem):
    mpu=MPU(); mpu.memory=mem
    bankstack=[]
    RET=0xAA00
    mpu.sp=0xFD; mem[0x1FE]=(RET-1)&0xFF; mem[0x1FF]=(RET-1)>>8
    mpu.pc=entry; mpu.a=mpu.x=mpu.y=0
    execviol=[]
    steps=0
    while mpu.pc!=RET:
        if EXT_LO<=mpu.pc<EXT_HI and mem.bank!=EXT_IDX:
            execviol.append((mpu.pc,mem.bank)); break
        if mpu.pc==VSET:
            bankstack.append(mem.bank); mem.bank=mpu.a
            _rts(mpu,mem); continue
        if mpu.pc==VPOP:
            mem.bank=bankstack.pop() if bankstack else 0
            _rts(mpu,mem); continue
        mpu.step(); steps+=1
        assert steps<200000,'petla'
    return execviol

def _rts(mpu,mem):
    lo=mem[0x100+((mpu.sp+1)&0xFF)]; hi=mem[0x100+((mpu.sp+2)&0xFF)]
    mpu.sp=(mpu.sp+2)&0xFF; mpu.pc=((hi<<8)|lo)+1

# ---- build test program ----
prog = r'''
INSTALL	smb 'INSTALL'
EXTENDED smb 'EXTENDED'
	blk sparta $0600
inst	lda EXTENDED
	sta ext_m
	dec INSTALL
	rts
	blk reloc main
devmain	lda ext_m
	jsr $07F1
	jsr disp
	pha
	pla
	jmp $07F4
ext_m	dta 0
memreix	dta 0
xfer	lda memreix
	jsr $07F1
	lda #$AA
	sta $9400
	jmp $07F4
	blk reloc ext
disp	lda extvar
	sta extresult
	jsr xfer
	lda extvar
	sta extok
	clc
	rts
extvar	dta 55
extresult dta 0
extok	dta 0
	blk update address
	blk update symbols
	end
'''
open('t3.asm','w').write(prog)
a=sx.Asm(); ok=a.assemble(prog.splitlines()); assert ok,a.errors
a.write('t3.SYS')
blocks,entry,mainmem,extmem=load('t3.SYS')
def lab(n):
    k,v=a.labels[n.lower()]
    return blocks[1]+v if k=='R' else (blocks[2]+v if k=='X' else v)

# ustaw ext_m=2 (indeks EXTRAM), memreix=0
mainmem[lab('ext_m')]=EXT_IDX
mainmem[lab('memreix')]=0

print('bloki:', {k:hex(v) for k,v in blocks.items()})
mem=BankMem(mainmem,extmem)

print('=== TEST POZYTYWNY: wejscie przez trampoline devmain ===')
ev=run(lab('devmain'),mem)
extresult=mem.ext[lab('extresult')-EXT_LO]
extok=mem.ext[lab('extok')-EXT_LO]
buf=mem.main[0x9400]
print(f'  extresult={extresult} (ozn.55), extok={extok} (ozn.55), buf9400=${buf:02X} (ozn.AA)')
print(f'  naruszenia exec: {ev}  naruszenia danych: {mem.viol}')
assert extresult==55 and extok==55 and buf==0xAA and not ev and not mem.viol, 'POZYTYWNY NIEUDANY'
print('  OK: mechanizm trampoliny + zagniezdzone V_setme/V_popme dziala, brak naruszen')

print('=== TEST NEGATYWNY: wejscie wprost do disp (bez V_setme) ===')
mem2=BankMem([x for x in mainmem],[x for x in extmem]); mem2.bank=0
ev2=run(lab('disp'),mem2)
print(f'  naruszenia exec: {[(hex(p),b) for p,b in ev2]}')
assert ev2, 'detektor NIE wykryl kodu EXTRAM przy zlym banku'
print('  OK: symulator wykrywa wykonanie kodu EXTRAM przy niezmapowanym banku')
print('\nWALIDACJA MECHANIZMU EXTRAM: ZALICZONA')
