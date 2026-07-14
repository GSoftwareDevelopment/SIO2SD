; ---------------------------------------------------------------------------
; SDMOUNT.COM v1.0 - montowanie obrazow ATR/XEX z karty SIO2SD pod D1:-D15:
;
; Uzycie (SpartaDOS X):
;   SDMOUNT                     - lista zamontowanych napedow
;   SDMOUNT D2: PLIK.ATR        - zamontuj plik (z biezacego katalogu karty)
;   SDMOUNT D2: GRY>PLIK.ATR    - zamontuj plik ze sciezki na karcie
;   SDMOUNT D2: /E              - podepnij pusty dysk
;   SDMOUNT D2: /D              - odlacz naped
;   /0../3                      - ID urzadzenia SIO2SD (domyslnie 0)
;
; Nazwy plikow podaje sie tak, jak pokazuje DIR na SDC: (mapowanie 8.3,
; w tym nazwy NNNN_III.EXT). Na prawdziwym SIO2SD zmiana jest natychmiast
; widoczna; w emulacji Altirry naped obsluguje sio2sd_server.py.
;
; Assembler: MADS (mads SDMOUNT.ASM -o:SDMOUNT.COM)
; ---------------------------------------------------------------------------

DOSVEC	= $0A
DDEVIC	= $0300
DUNIT	= $0301
DCOMND	= $0302
DSTATS	= $0303
DBUFLO	= $0304
DBUFHI	= $0305
DTIMLO	= $0306
DBYTLO	= $0308
DBYTHI	= $0309
DAUX1	= $030A
DAUX2	= $030B
CIOV	= $E456
SIOV	= $E459
ICCOM0	= $0342
ICBAL0	= $0344
ICBAH0	= $0345
ICBLL0	= $0348
ICBLH0	= $0349
EOL	= $9B
; adres SIO dla ID 0: sio2sd.org podaje $73, sprzet testowy $72 (jak SDCDEV)
SIOBASE	= $72

	opt h-

	blk reloc main

start
	jmp main

; ===========================================================================
; ZMIENNE I BUFORY
; ===========================================================================

devid	dta SIOBASE	; adres SIO (SIOBASE + ID)
siomode	dta 0		; 0 = SIOV, inaczej dzielnik POKEY dla $CFED
drive	dta 0		; numer napedu 1-15 (0 = brak)
action	dta 0		; 0=lista 1=mount 2=empty 3=disconnect
serr	dta 0		; ostatni status SIO (diagnostyka)
havenam	dta 0
pathmode dta 0
pathbad	dta 0
argy	dta 0
tmpb	dta 0
pathi	dta 0
pathlast dta 0
upcnt	dta 0
fcnt	dta 0,0
fidx	dta 0,0
mgidx	dta 0,0
nlen	dta 0
dotp	dta 0
baslen	dta 0
extlen	dta 0
mangl	dta 0
t16	dta 0,0
lstbase	dta 0
lsti	dta 0
lsti2	dta 0
lcnt	dta 0
lx	dta 0

tokb	:13 dta 0
pathbuf	:65 dta 0
f11	:11 dta 0
m11	:11 dta 0
e54	:54 dta 0
ebuf	:216 dta 0
maskbuf	:16 dta 0
linebuf	:56 dta 0

mstar	dta c'*'
	:15 dta 0

w_e54	dta a(e54)
w_ebuf	dta a(ebuf)
w_mask	dta a(maskbuf)
w_tmpb	dta a(tmpb)
w_fcnt	dta a(fcnt)
w_line	dta a(linebuf)
w_mban	dta a(m_ban)
w_mnod	dta a(m_nod)
w_muse	dta a(m_use)
w_mnf	dta a(m_nf)
w_mok	dta a(m_ok)
w_mdis	dta a(m_dis)
w_memp	dta a(m_emp)
w_mnon	dta a(m_non)
w_merr	dta a(m_err)
w_medir	dta a(m_edir)
w_mstat	dta a(m_stat)

; ===========================================================================
; SIO
; ===========================================================================

sdcb
	sta DCOMND
	sty DSTATS
	lda devid
	sta DDEVIC
	lda #1
	sta DUNIT
	lda #4
	sta DTIMLO
	lda #0
	sta DAUX1
	sta DAUX2
	rts

gosio
	lda siomode
	bne gs_hs
	jsr SIOV
	tya
	rts
gs_hs	jsr gs_go
	tya
	rts
gs_go	jmp $CFED

bufe54
	lda w_e54
	sta DBUFLO
	lda w_e54+1
	sta DBUFHI
	lda #54
	sta DBYTLO
	lda #0
	sta DBYTHI
	rts

setmask
	lda #$09
	ldy #$80
	jsr sdcb
	lda #3
	sta DAUX1
	lda w_mask
	sta DBUFLO
	lda w_mask+1
	sta DBUFHI
	lda #16
	sta DBYTLO
	lda #0
	sta DBYTHI
	jmp gosio

getcnt
	lda #$0A
	ldy #$40
	jsr sdcb
	lda w_fcnt
	sta DBUFLO
	lda w_fcnt+1
	sta DBUFHI
	lda #2
	sta DBYTLO
	lda #0
	sta DBYTHI
	jmp gosio

getent
	pha
	lda #$04
	ldy #$40
	jsr sdcb
	lda #1
	sta DAUX1
	pla
	sta DAUX2
	jsr bufe54
	jmp gosio

cardok
	lda #$00
	ldy #$40
	jsr sdcb
	lda #2
	sta DTIMLO
	lda w_tmpb
	sta DBUFLO
	lda w_tmpb+1
	sta DBUFHI
	lda #1
	sta DBYTLO
	lda #0
	sta DBYTHI
	jsr gosio
	bmi co_9
	lda tmpb
	bne co_ok
	lda #$FF
	rts
co_ok	lda #1
co_9	ora #0
	rts

rootdir
	lda #$07
	ldy #$00
	jsr sdcb
	jmp gosio

parentdir
	lda #$06
	ldy #$00
	jsr sdcb
	jmp gosio

setdir_e54
	lda #$05
	ldy #$80
	jsr sdcb
	jsr bufe54
	jmp gosio

; ===========================================================================
; MAPOWANIE NAZW (jak w SDCDEV.SYS)
; ===========================================================================

upch
	cmp #'a'
	bcc up_1
	cmp #'z'+1
	bcs up_1
	and #$DF
up_1	rts

validch
	cmp #'A'
	bcc vc_1
	cmp #'Z'+1
	bcc vc_ok
vc_1	cmp #'0'
	bcc vc_2
	cmp #'9'+1
	bcc vc_ok
vc_2	cmp #'_'
	beq vc_ok
	cmp #'-'
	beq vc_ok
	cmp #'!'
	beq vc_ok
	cmp #'@'
	beq vc_ok
	cmp #'#'
	beq vc_ok
	cmp #'&'
	beq vc_ok
	cmp #'('
	beq vc_ok
	cmp #')'
	beq vc_ok
	clc
	rts
vc_ok	sec
	rts

; tokb (ASCII 8.3) -> f11

tok2f11
	ldx #10
	lda #' '
tf_f	sta f11,x
	dex
	bpl tf_f
	ldx #0
	ldy #0
tf_b	lda tokb,x
	beq tf_ok
	cmp #'.'
	beq tf_dot
	cmp #'*'
	beq tf_star
	jsr upch
	cpy #8
	bcs tf_err
	sta f11,y
	inx
	iny
	bne tf_b
tf_star	lda #'?'
tf_s1	cpy #8
	bcs tf_s2
	sta f11,y
	iny
	bne tf_s1
tf_s2	inx
	lda tokb,x
	beq tf_ok
	cmp #'.'
	beq tf_dot
	bne tf_err
tf_dot	inx
	ldy #8
tf_e	lda tokb,x
	beq tf_ok
	cmp #'*'
	beq tf_es
	jsr upch
	cpy #11
	bcs tf_err
	sta f11,y
	inx
	iny
	bne tf_e
tf_es	lda #'?'
tf_e1	cpy #11
	bcs tf_ok
	sta f11,y
	iny
	bne tf_e1
tf_ok	lda #1
	rts
tf_err	lda #$FF
	rts

; e54 + mgidx -> m11 (mapowanie LFN na 8.3, styl NNNN_III)

map83
	ldx #39
mp_l1	dex
	bmi mp_l2
	lda e54,x
	beq mp_l1
	cmp #' '
	beq mp_l1
mp_l2	inx
	stx nlen
	lda #$FF
	sta dotp
	ldx #0
mp_d1	cpx nlen
	bcs mp_d2
	lda e54,x
	cmp #'.'
	bne mp_d3
	stx dotp
mp_d3	inx
	bne mp_d1
mp_d2	lda dotp
	cmp #$FF
	bne mp_e1
	lda nlen
	sta baslen
	lda #0
	sta extlen
	beq mp_e2
mp_e1	sta baslen
	sec
	lda nlen
	sbc dotp
	sec
	sbc #1
	sta extlen
mp_e2	lda #0
	sta mangl
	lda baslen
	beq mp_mg
	cmp #9
	bcc mp_e3
mp_mg	lda #1
	sta mangl
mp_e3	lda extlen
	cmp #4
	bcc mp_e4
	lda #1
	sta mangl
mp_e4
	ldx #10
	lda #' '
mp_f1	sta m11,x
	dex
	bpl mp_f1
	ldx #0
	ldy #0
mp_b1	cpx baslen
	bcs mp_b9
	cpy #8
	bcs mp_b9
	lda e54,x
	jsr upch
	jsr validch
	bcs mp_b2
	lda #1
	sta mangl
	lda #'_'
mp_b2	sta m11,y
	inx
	iny
	bne mp_b1
mp_b9
	lda dotp
	cmp #$FF
	beq mp_x9
	clc
	adc #1
	tax
	ldy #8
mp_x1	cpx nlen
	bcs mp_x9
	cpy #11
	bcs mp_x9
	lda e54,x
	jsr upch
	jsr validch
	bcs mp_x2
	lda #1
	sta mangl
	lda #'_'
mp_x2	sta m11,y
	inx
	iny
	bne mp_x1
mp_x9
	lda mangl
	bne mp_g1
	rts
mp_g1	ldx #0
mp_m1	lda m11,x
	cmp #' '
	bne mp_m2
	lda #'0'
	sta m11,x
mp_m2	inx
	cpx #4
	bcc mp_m1
	lda #'_'
	sta m11+4
	lda mgidx
	sta t16
	lda mgidx+1
	sta t16+1
mp_m3	lda t16
	cmp #$E8
	lda t16+1
	sbc #$03
	bcc mp_m4
	sec
	lda t16
	sbc #$E8
	sta t16
	lda t16+1
	sbc #$03
	sta t16+1
	jmp mp_m3
mp_m4	ldx #0
mp_m5	lda t16
	cmp #100
	lda t16+1
	sbc #0
	bcc mp_m6
	sec
	lda t16
	sbc #100
	sta t16
	lda t16+1
	sbc #0
	sta t16+1
	inx
	bne mp_m5
mp_m6	txa
	ora #$30
	sta m11+5
	ldx #0
	lda t16
mp_m7	cmp #10
	bcc mp_m8
	sec
	sbc #10
	inx
	bne mp_m7
mp_m8	sta tmpb
	txa
	ora #$30
	sta m11+6
	lda tmpb
	ora #$30
	sta m11+7
	rts

match11
	ldx #0
mt_1	lda f11,x
	cmp #'?'
	beq mt_2
	cmp m11,x
	bne mt_no
mt_2	inx
	cpx #11
	bcc mt_1
	lda #0
	rts
mt_no	lda #1
	rts

; znajdz plik pasujacy do f11 w biezacym katalogu karty -> e54
; wyjscie: A=1 znaleziono / A=$FF brak / A=blad SIO (N=1)

findfil
	ldx #0
	lda #'*'
	sta maskbuf
	lda #0
ff_0	inx
	sta maskbuf,x
	cpx #15
	bcc ff_0
	jsr setmask
	bmi ff_9
	jsr getcnt
	bmi ff_9
	lda #0
	sta fidx
	sta fidx+1
	lda fcnt
	ora fcnt+1
	beq ff_nf
	lda #1
ff_lp	jsr getent
	bmi ff_9
	lda fidx
	sta mgidx
	lda fidx+1
	sta mgidx+1
	jsr map83
	jsr match11
	beq ff_hit
	inc fidx
	bne ff_1
	inc fidx+1
ff_1	lda fidx
	cmp fcnt
	lda fidx+1
	sbc fcnt+1
	bcs ff_nf
	lda #0
	beq ff_lp
ff_hit	lda #1
	rts
ff_nf	lda #0
ff_9	ora #0
	rts

; pathbuf (8.3 skladniki rozdzielone >, \ albo /) -> e54 pliku
; zwykla nazwa pliku nie trafia tutaj - obsluguje ja stara droga findfil.
; wyjscie: A=1 znaleziono / A=0 brak / N=blad SIO

findpath
	lda #0
	sta pathi
	sta upcnt
	lda pathbuf
	cmp #'>'
	beq fp_abs
	cmp #'\'
	beq fp_abs
	cmp #'/'
	beq fp_abs
	jmp fp_lp
fp_abs	inc pathi
	jsr rootdir
	bpl fp_lp
	rts
fp_lp	ldx pathi
	ldy #0
fp_c1	lda pathbuf,x
	beq fp_last
	cmp #'>'
	beq fp_sep
	cmp #'\'
	beq fp_sep
	cmp #'/'
	beq fp_sep
	cpy #12
	bcs fp_nf
	sta tokb,y
	inx
	iny
	jmp fp_c1
fp_sep	lda #0
	sta pathlast
	inx
	stx pathi
	jmp fp_tok
fp_last	lda #1
	sta pathlast
	stx pathi
fp_tok	lda #0
	sta tokb,y
	cpy #0
	beq fp_nf
	jsr tok2f11
	bmi fp_nf
	jsr findfil
	bmi fp_9
	cmp #1
	bne fp_nf
	lda pathlast
	bne fp_ok
	lda e54+39
	cmp #1
	bne fp_nf
	jsr setdir_e54
	bmi fp_9
	inc upcnt
	jmp fp_lp
fp_ok	lda #1
	rts
fp_nf	lda #0
fp_9	ora #0
	rts

restore_path
	lda upcnt
	beq rp_ok
rp_lp	jsr parentdir
	bmi rp_e
	dec upcnt
	bne rp_lp
rp_ok	lda #1
	rts
rp_e	ora #0
	rts

; ===========================================================================
; PROGRAM GLOWNY
; ===========================================================================

pmsg
	sta ICBAL0
	stx ICBAH0
	lda #9
	sta ICCOM0
	lda #$FF
	sta ICBLL0
	lda #0
	sta ICBLH0
	ldx #0
	jmp CIOV

main
	lda w_mban
	ldx w_mban+1
	jsr pmsg

; HISIO?

	lda $CFF0
	cmp #'H'
	bne hs_no
	lda $CFF1
	cmp #'i'
	bne hs_no
	lda $CFF2
	cmp #'a'
	bne hs_no
	lda $CFF3
	cmp #'s'
	bne hs_no
	lda $CFF5
	cmp #'1'
	bcc hs_no
	bne hs_yes
	lda $CFF7
	cmp #'3'
	bcc hs_no
	bne hs_yes
	lda $CFF8
	cmp #'2'
	bcc hs_no
hs_yes	lda #$28
	sta siomode
hs_no

; --- parsuj argumenty ---

	ldy #10		; BUFOFF
	lda (DOSVEC),y
	clc
	adc #63
	sta argy
	jmp pa_lp
pa_dj	jmp pa_done
pa_lp	ldy argy
	cpy #200
	bcs pa_dj
	lda (DOSVEC),y
	cmp #EOL
	beq pa_dj
	cmp #' '
	bne pa_tok
	inc argy
	jmp pa_lp
pa_tok	cmp #'/'
	beq pa_sw
	cmp #'D'
	beq pa_drv
	cmp #'d'
	beq pa_drv
	jmp pa_nam
pa_sw	sty lx
	inc argy
	ldy argy
	lda (DOSVEC),y
	cmp #EOL
	beq pa_dj
	jsr upch
	cmp #'E'
	beq pa_e
	cmp #'D'
	beq pa_d
	cmp #'0'
	bcc pa_slash
	cmp #'4'
	bcs pa_slash
	and #$0F
	clc
	adc #SIOBASE
	sta devid
pa_skip	inc argy
	jmp pa_lp
pa_slash
	lda lx
	sta argy
	jmp pa_nam
pa_e	lda #2
	sta action
	jmp pa_skip
pa_d	lda #3
	sta action
	jmp pa_skip
pa_drv	; 'D' cyfry ':'  -> drive; bez ':' -> traktuj jak nazwe
	sty lx		; zapamietaj poczatek tokenu
	inc argy
	ldy argy
	lda (DOSVEC),y
	cmp #'1'
	bcc pa_nam2
	cmp #'9'+1
	bcs pa_nam2
	and #$0F
	sta drive
	inc argy
	ldy argy
	lda (DOSVEC),y
	cmp #':'
	beq pa_dok
	cmp #'0'
	bcc pa_nam2
	cmp #'6'	; druga cyfra 0-5 (D10:-D15:)
	bcs pa_nam2
	pha
	lda drive
	cmp #1
	bne pa_x1
	pla
	and #$0F
	clc
	adc #10
	sta drive
	inc argy
	ldy argy
	lda (DOSVEC),y
	cmp #':'
	beq pa_dok
pa_nam2	lda lx
	sta argy
	lda #0
	sta drive
	jmp pa_nam
pa_x1	pla
	jmp pa_nam2
pa_dok	inc argy
	jmp pa_lp
pa_nam	; nazwa/sciezka pliku -> pathbuf, a dla zwyklej nazwy takze tokb
	ldx #0
	lda #0
	sta pathmode
	sta pathbad
pn_1	ldy argy
	lda (DOSVEC),y
	cmp #EOL
	beq pn_9
	cmp #' '
	beq pn_9
	cpx #64
	bcs pn_bad
	sta pathbuf,x
	cmp #'>'
	beq pn_sep
	cmp #'\'
	beq pn_sep
	cmp #'/'
	beq pn_sep
	jmp pn_c1
pn_sep	lda #1
	sta pathmode
pn_c1	cpx #12
	bcs pn_c2
	lda pathbuf,x
	sta tokb,x
pn_c2
	inx
	inc argy
	jmp pn_1
pn_9	lda #0
	sta pathbuf,x
	cpx #12
	bcs pn_z12
	sta tokb,x
	jmp pn_zok
pn_z12	sta tokb+12
pn_zok
	cpx #0
	bne pn_a
	jmp pa_lp
pn_bad	lda #1
	sta pathbad
pn_b1	ldy argy
	lda (DOSVEC),y
	cmp #EOL
	beq pn_9
	cmp #' '
	beq pn_9
	inc argy
	jmp pn_b1
pn_a	lda #1
	sta havenam
	sta action
	jmp pa_lp
pa_done

; --- walidacja i akcja ---

	lda drive
	bne go_act
	lda action
	bne du_1
	jmp go_list
du_1	lda w_muse
	ldx w_muse+1
	jmp pmsg
go_act
	lda action
	cmp #1
	bne ga_1
	jmp go_mnt
ga_1	cmp #2
	bne ga_2
	jmp go_emp
ga_2	cmp #3
	bne ga_3
	jmp go_dis
ga_3	lda w_muse
	ldx w_muse+1
	jmp pmsg

; --- montowanie pliku ---

go_mnt
	lda pathbad
	beq gm_p0
	jmp e_use
gm_p0
	jsr cardok
	bpl gm_1
	jmp e_nod
gm_1	lda pathmode
	beq gm_old
	jsr findpath
	sta tmpb
	jsr restore_path
	bpl gm_p2
	jmp e_dir
gm_p2	lda tmpb
	bpl gm_3
	jmp e_dir
gm_old	jsr tok2f11
	bpl gm_2
	jmp e_use
gm_2	jsr findfil
	bpl gm_3
	jmp e_dir
gm_3	cmp #0
	bne gm_4
	lda w_mnf
	ldx w_mnf+1
	jmp pmsg
gm_4	; $02: aux1=drive aux2=1, dane=e54
	lda #$02
	ldy #$80
	jsr sdcb
	lda drive
	sta DAUX1
	lda #1
	sta DAUX2
	jsr bufe54
	jsr gosio
	bpl gm_ok
	jmp e_err
gm_ok	lda w_mok
	ldx w_mok+1
	jmp pmsg

; --- pusty dysk ---

go_emp
	jsr cardok
	bmi e_nod
	ldx #0
	lda #0
ge_1	sta e54,x
	inx
	cpx #54
	bcc ge_1
	lda #3
	sta e54+39
	lda #$02
	ldy #$80
	jsr sdcb
	lda drive
	sta DAUX1
	lda #1
	sta DAUX2
	jsr bufe54
	jsr gosio
	bpl ge_ok
	jmp e_err
ge_ok	lda w_memp
	ldx w_memp+1
	jmp pmsg

; --- odlaczenie ---

go_dis
	lda #$03
	ldy #$00
	jsr sdcb
	lda drive
	sta DAUX1
	lda #1
	sta DAUX2
	jsr gosio
	bpl gd_ok
	jmp e_err
gd_ok	lda w_mdis
	ldx w_mdis+1
	jmp pmsg

e_nod	lda w_mnod
	ldx w_mnod+1
	jmp pmsg
e_use	lda w_muse
	ldx w_muse+1
	jmp pmsg
e_dir	sta serr		; A = status SIO
	lda w_medir
	ldx w_medir+1
	jsr pmsg
	jmp prstat
e_err	sta serr
	lda w_merr
	ldx w_merr+1
	jsr pmsg
prstat	jsr puthex
	lda w_mstat
	ldx w_mstat+1
	jmp pmsg

; serr -> hex w m_st1/m_st2
puthex	lda serr
	lsr @
	lsr @
	lsr @
	lsr @
	jsr hexdig
	sta m_st1
	lda serr
	and #$0F
	jsr hexdig
	sta m_st2
	rts
hexdig	cmp #10
	bcc hd0
	adc #'A'-11
	rts
hd0	adc #'0'
	rts

; --- lista mapowan ($01 po 4 wpisy) ---

go_list
	jsr cardok
	bpl gl_0
	jmp e_nod
gl_0	lda #0
	sta havenam	; uzyj jako "cos wypisano"
	lda #1
	sta lstbase
gl_lp	lda #4
	sta lcnt
	lda lstbase
	cmp #13
	bne gl_1
	lda #3
	sta lcnt
gl_1	lda #$01
	ldy #$40
	jsr sdcb
	lda lstbase
	sta DAUX1
	lda lcnt
	sta DAUX2
	lda w_ebuf
	sta DBUFLO
	lda w_ebuf+1
	sta DBUFHI
	lda #0
	sta DBYTHI
	lda lcnt
	cmp #4
	bne gl_2
	lda #216
	sta DBYTLO
	jmp gl_3
gl_2	lda #162
	sta DBYTLO
gl_3	jsr gosio
	bmi gl_er
	lda #0
	sta lsti
gl_e	lda lsti
	cmp lcnt
	bcs gl_nx
	jsr prent
	inc lsti
	jmp gl_e
gl_er	jmp e_err
gl_nx	clc
	lda lstbase
	adc #4
	sta lstbase
	cmp #16
	bcc gl_lp
	lda havenam
	bne gl_9
	lda w_mnon
	ldx w_mnon+1
	jmp pmsg
gl_9	rts

; wypisz wpis nr lsti z ebuf (gdy typ != 0); naped = lstbase+lsti

prent
	lda #0
	sta t16
	ldx lsti
pr_m1	cpx #0
	beq pr_m2
	clc
	lda t16
	adc #54
	sta t16
	dex
	jmp pr_m1
pr_m2
	ldx t16
	lda ebuf+39,x	; typ wpisu
	bne pr_go
	rts
pr_go	sta tmpb
	clc
	lda lstbase
	adc lsti
	sta lx		; numer napedu
	ldx #0
	lda #'D'
	sta linebuf,x
	inx
	lda lx
	cmp #10
	bcc pr_d1
	lda #'1'
	sta linebuf,x
	inx
	lda lx
	sec
	sbc #10
	sta lx
pr_d1	lda lx
	ora #$30
	sta linebuf,x
	inx
	lda #':'
	sta linebuf,x
	inx
	lda #' '
	sta linebuf,x
	inx
	lda tmpb
	cmp #3
	bne pr_fil
	ldy #0
pr_e1	lda txtemp,y
	sta linebuf,x
	inx
	iny
	cpy #12
	bcc pr_e1
	jmp pr_eol
pr_fil	lda #0
	sta lsti2
pr_f1	lda lsti2
	cmp #39
	bcs pr_eol
	clc
	adc t16
	tay
	lda ebuf,y
	beq pr_eol
	sta linebuf,x
	inx
	inc lsti2
	jmp pr_f1
pr_eol	lda #EOL
	sta linebuf,x
	lda w_line
	ldx w_line+1
	jsr pmsg
	lda #1
	sta havenam
	rts

txtemp	dta c'(pusty dysk)'

; --- komunikaty ---

m_ban	dta c'SDMOUNT v1.0',EOL
m_nod	dta c'SIO2SD nie odpowiada',EOL
m_use	dta c'Uzycie: SDMOUNT [/0-3] [Dn: PLIK | Dn: SCIEZKA>PLIK | Dn: /E | Dn: /D]',EOL
m_nf	dta c'Nie znaleziono pliku',EOL
m_ok	dta c'Zamontowano',EOL
m_dis	dta c'Odlaczono',EOL
m_emp	dta c'Podpieto pusty dysk',EOL
m_non	dta c'Brak zamontowanych napedow',EOL
m_err	dta c'Blad montowania',EOL
m_edir	dta c'Blad odczytu katalogu',EOL
m_stat	dta c'  kod SIO=$'
m_st1	dta c'?'
m_st2	dta c'?',EOL

	blk update address
	end
