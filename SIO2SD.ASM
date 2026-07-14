; ---------------------------------------------------------------------------
; SIO2SD.SYS v1.0
; Sterownik SpartaDOS X: dostep do plikow na karcie SD urzadzenia SIO2SD
;
; Wymagania: SIO2SD z firmware 3.x (komendy plikowe $09-$0A, $20-$27)
; Format:    natywny, relokowalny plik SDX (blk reloc main)
; Assembler: MADS (mads SIO2SD.ASM -o:SIO2SD.SYS)
;
; Instalacja:  SIO2SD.SYS [litera] [/0../3]
;   litera - litera urzadzenia CIO (domyslnie F:)
;   /0../3 - wymus ID urzadzenia SIO2SD (SIO $72..$75, patrz SIOBASE), autodetekcja domyslnie
;
; Urzadzenie (domyslnie F:) obsluguje:
;   OPEN 4 (odczyt), 8 (zapis/nadpis), 9 (dopisywanie), 12 (odczyt+zapis)
;   OPEN 6 (katalog, maska np. "F:*.ATR")
;   XIO 32 RENAME  "F:stara,nowa"
;   XIO 33 DELETE  "F:nazwa" (maska z '*' dozwolona)
;   XIO 37 POINT / XIO 38 NOTE (24-bitowa pozycja w ICAX3/4/5)
;   XIO 39 dlugosc pliku -> ICAX3/4/5
;   XIO 42 MKDIR   "F:nazwa"
;   XIO 43 RMDIR   "F:nazwa"
;   XIO 44 CHDIR   "F:sciezka" ('>' lub '\' rozdziela, '<' w gore, "F:" = korzen)
;   XIO 48 GETCWD  (nazwa biezacego katalogu do bufora + EOL)
; ---------------------------------------------------------------------------

; --- rownania systemowe ---

DOSVEC	= $0A
DOSINI	= $0C
MEMLO	= $02E7
HATABS	= $031A
DVSTAT	= $02EA

ICCOMZ	= $22
ICBALZ	= $24
ICBAHZ	= $25
ICAX1Z	= $2A
ICAX2Z	= $2B

ICAX3	= $034C		; + X (X = nr IOCB * 16)
ICAX4	= $034D
ICAX5	= $034E

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

; --- kody bledow CIO ---

ETOOMANY = 161		; za duzo otwartych plikow (kanal zajety)
ENOTOPEN = 133		; plik nie jest otwarty
EWRONLY	= 131		; otwarty tylko do zapisu
ERDONLY	= 135		; otwarty tylko do odczytu
EEOF	= 136		; koniec pliku
ENFOUND	= 170		; nie znaleziono pliku
EDIRNF	= 150		; nie znaleziono katalogu
EBADNAM	= 165		; bledna nazwa pliku
ENOTIMP	= 146		; funkcja nie zaimplementowana
ENOCARD	= 144		; brak karty / blad urzadzenia
EPERM	= 167		; operacja niedozwolona
EEXIST	= 151		; plik/katalog istnieje
EBADMOD	= 132		; bledny tryb otwarcia
EPOINT	= 171		; bledna pozycja POINT
; adres SIO dla ID 0. sio2sd.org: $73+ID; sprzet testowy: $72+ID -> SIOBASE=$72
SIOBASE	= $72
ENAK	= 139		; NAK z SIO

	opt h-

	blk reloc main

; ===========================================================================
; CZESC REZYDENTNA
; ===========================================================================

start
	jmp install

; --- tablica handlera CIO ---

htab
	dta a(dopen-1)
	dta a(dclose-1)
	dta a(dget-1)
	dta a(dput-1)
	dta a(dstat-1)
	dta a(dspec-1)
	jmp hinit

; --- zmienne stanu ---

devid	dta SIOBASE	; adres SIO urzadzenia (SIOBASE..SIOBASE+3)
siomode	dta 0		; 0 = SIOV, inaczej dzielnik POKEY dla wejscia $CFED
devltr	dta c'F'	; litera urzadzenia CIO
chown	dta 0		; wlasciciel kanalu: nr IOCB*16+1, 0 = wolny
chmode	dta 0		; tryb otwarcia (4,6,8,9,12)
iocbx	dta 0		; nr IOCB*16 zapamietany przy OPEN
xsave	dta 0		; zapas rejestru X
fpos	dta 0,0,0	; logiczna pozycja w pliku (24 bity)
flen	dta 0,0,0	; dlugosc pliku (24 bity)
dvpos	dta 0,0,0	; pozycja I/O w urzadzeniu (24 bity)
wstart	dta 0,0,0	; pozycja poczatku bufora zapisu
endp	dta 0,0,0	; robocze: koniec danych po flush
rcnt	dta 0		; bajty pozostale w buforze odczytu
rptr	dta 0		; indeks w buforze odczytu
wcnt	dta 0		; bajty w buforze zapisu
dircnt	dta a(0)	; pozostale wpisy katalogu (16 bitow)
dirfrst	dta 0		; 1 = najblizsze $04 z aux2=1 (od poczatku)
dphase	dta 0		; 0=nowy wpis, 1=w linii, 2=EOF
dfoot	dta 0		; 1 = stopka byla wygenerowana
lptr	dta 0		; indeks w linii
llen	dta 0		; dlugosc linii
cbyte	dta 0		; bajt roboczy GET/PUT
tbyte	dta 0		; bajt roboczy (porownania nazw)
fnlen	dta 0		; dlugosc nazwy w fnbuf
nnlen	dta 0		; dlugosc drugiej nazwy (rename)
xerr	dta 0		; zamiennik bledu dla NAK
digit	dta 0		; cyfra (druk liczb)
pnflag	dta 0		; flaga wiodacych zer
pnx	dta 0		; indeks wyjsciowy druku liczb
t32	dta 0,0,0,0	; robocze 32 bity (odejmowanie)
num32	dta 0,0,0,0	; drukowana liczba 32-bitowa
skb	dta 0,0,0	; bufor 3-bajtowy (pozycja/dlugosc)
tmpb	dta 0		; bufor 1-bajtowy (status/wersja)
cnt2	dta a(0)	; bufor 2-bajtowy (liczba wpisow)
dtot	dta a(0)	; laczna liczba wpisow (stopka)
frstfl	dta 0		; flaga: skasowano cos w petli delete

; --- slowa adresowe (relokowalne odwolania do wnetrza bloku) ---

w_htab	dta a(htab)
w_rdbuf	dta a(rdbuf)
w_wrbuf	dta a(wrbuf)
w_dire	dta a(dirent)
w_objb	dta a(objbuf)
w_mask	dta a(maskbuf)
w_skb	dta a(skb)
w_tmpb	dta a(tmpb)
w_cnt2	dta a(cnt2)
w_rese	dta a(resend)
w_hook	dta a(reshook)

; --- tablica poteg 10 (32 bity, little-endian) ---

pow10
	dta $00,$CA,$9A,$3B	; 1000000000
	dta $00,$E1,$F5,$05	; 100000000
	dta $80,$96,$98,$00	; 10000000
	dta $40,$42,$0F,$00	; 1000000
	dta $A0,$86,$01,$00	; 100000
	dta $10,$27,$00,$00	; 10000
	dta $E8,$03,$00,$00	; 1000
	dta $64,$00,$00,$00	; 100
	dta $0A,$00,$00,$00	; 10
	dta $01,$00,$00,$00	; 1

; ===========================================================================
; POMOCNICZE: SIO
; ===========================================================================

; ustaw DCB: A = komenda, Y = DSTATS ($00/$40/$80)

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

; wykonaj SIO; wyjscie: Y = status (flaga N wg Y)
; przy wykrytym patchu HISIO (Hias >= 1.32) uzywa wejscia $CFED

gosio
	lda siomode
	bne gs_hs
	jsr SIOV
	ldy DSTATS
	rts
gs_hs	jsr gs_go	; A = dzielnik POKEY
	ldy DSTATS
	rts
gs_go	jmp $CFED

; bufory DCB

bufdire
	lda w_dire
	sta DBUFLO
	lda w_dire+1
	sta DBUFHI
	lda #54
	sta DBYTLO
	lda #0
	sta DBYTHI
	rts

bufobj39
	lda w_objb
	sta DBUFLO
	lda w_objb+1
	sta DBUFHI
	lda #39
	sta DBYTLO
	lda #0
	sta DBYTHI
	rts

bufobj54
	jsr bufobj39
	lda #54
	sta DBYTLO
	rts

bufskb3
	lda w_skb
	sta DBUFLO
	lda w_skb+1
	sta DBUFHI
	lda #3
	sta DBYTLO
	lda #0
	sta DBYTHI
	rts

buftmp1
	lda w_tmpb
	sta DBUFLO
	lda w_tmpb+1
	sta DBUFHI
	lda #1
	sta DBYTLO
	lda #0
	sta DBYTHI
	rts

; zamiana NAK na blad z xerr; wyjscie: Y = status, flaga N wg Y

nakmap
	cpy #ENAK
	bne nm1
	ldy xerr
nm1	cpy #0
	rts

; status urzadzenia (komenda $00): A = stan karty (0..4)
; sukces: N=0; blad: N=1, Y = status SIO

sdstat
	lda #$00
	ldy #$40
	jsr sdcb
	jsr buftmp1
	jsr gosio
	bmi sd_e
	lda tmpb
	ldy #1
	rts
sd_e
	tya
	rts

; ustaw pozycje I/O urzadzenia wg skb (komenda $23)

dseek
	lda #$23
	ldy #$80
	jsr sdcb
	jsr bufskb3
	jmp gosio

; pozycja urzadzenia := fpos (gdy rozna)

syncpos
	lda dvpos
	cmp fpos
	bne sy1
	lda dvpos+1
	cmp fpos+1
	bne sy1
	lda dvpos+2
	cmp fpos+2
	bne sy1
	ldy #1
	rts
sy1
	lda fpos
	sta skb
	lda fpos+1
	sta skb+1
	lda fpos+2
	sta skb+2
	jsr dseek
	bmi sy2
	lda fpos
	sta dvpos
	lda fpos+1
	sta dvpos+1
	lda fpos+2
	sta dvpos+2
	ldy #1
sy2	rts

; inkrementacja fpos (nie zmienia A)

ipos
	inc fpos
	bne ip1
	inc fpos+1
	bne ip1
	inc fpos+2
ip1	rts

; Y=3 gdy fpos==flen, inaczej Y=1

atend
	lda fpos
	cmp flen
	bne ae1
	lda fpos+1
	cmp flen+1
	bne ae1
	lda fpos+2
	cmp flen+2
	bne ae1
	ldy #3
	rts
ae1	ldy #1
	rts

; ===========================================================================
; POMOCNICZE: operacje plikowe SIO2SD
; ===========================================================================

; otworz plik o nazwie z fnbuf; A = aux1 ($20: 1=utworz/otworz, 3=otworz)
; wyjscie: Y = status, N wg Y

fopen
	pha
	ldx #0
fo1	lda fnbuf,x
	beq fo2
	sta objbuf,x
	inx
	cpx #39
	bcc fo1
fo2
	lda #0
fo3	cpx #39
	bcs fo4
	sta objbuf,x
	inx
	bne fo3
fo4
	lda #$20
	ldy #$80
	jsr sdcb
	pla
	sta DAUX1
	jsr bufobj39
	lda #ENFOUND
	sta xerr
	jsr gosio
	jmp nakmap

; pobierz dlugosc pliku ($26) -> flen

fgetlen
	lda #$26
	ldy #$40
	jsr sdcb
	jsr bufskb3
	jsr gosio
	bmi fg1
	lda skb
	sta flen
	lda skb+1
	sta flen+1
	lda skb+2
	sta flen+2
	ldy #1
fg1	rts

; ustaw dlugosc pliku ($27) wg skb

fsetlen
	lda #$27
	ldy #$80
	jsr sdcb
	jsr bufskb3
	jmp gosio

; wyslij maske z maskbuf ($09); A = typy (1=katalogi, 2=pliki, 3=oba)

sendmask
	pha
	lda #$09
	ldy #$80
	jsr sdcb
	pla
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

; liczba wpisow wg maski ($0A) -> cnt2

getcnt
	lda #$0A
	ldy #$40
	jsr sdcb
	lda w_cnt2
	sta DBUFLO
	lda w_cnt2+1
	sta DBUFHI
	lda #2
	sta DBYTLO
	lda #0
	sta DBYTHI
	jmp gosio

; pobierz nastepny wpis katalogu ($04) -> dirent; A = aux2 (1=od poczatku)

getent
	pha
	lda #$04
	ldy #$40
	jsr sdcb
	lda #1
	sta DAUX1
	pla
	sta DAUX2
	jsr bufdire
	jmp gosio

; zbuduj maske w maskbuf ze srch (pusta -> "*", dluga -> prefiks+"*")

mkmask
	ldx #0
	lda srch
	bne mm1
	lda #'*'
	sta maskbuf
	ldx #1
	bne mm4
mm1	lda srch,x
	beq mm4
	sta maskbuf,x
	inx
	cpx #14
	bcc mm1
	lda srch,x
	beq mm4
	lda #'*'
	sta maskbuf,x
	inx
mm4	lda #0
mm5	cpx #16
	bcs mm6
	sta maskbuf,x
	inx
	bne mm5
mm6	rts

; skopiuj fnbuf -> srch

fn2srch
	ldx #0
fn1	lda fnbuf,x
	sta srch,x
	inx
	cpx #40
	bcc fn1
	rts

; znajdz wpis o nazwie srch (A = typy); wynik w dirent
; wyjscie: C=0 znaleziono; C=1 brak (N=0) lub blad SIO (N=1, Y = status)

findent
	sta tbyte
	jsr mkmask
	lda tbyte
	jsr sendmask
	bmi fe_err
	jsr getcnt
	bmi fe_err
	lda cnt2
	ora cnt2+1
	beq fe_nf
	lda #1
fe1	jsr getent
	bmi fe_err
	jsr cmpname
	beq fe_ok
	lda cnt2
	bne fe2
	dec cnt2+1
fe2	dec cnt2
	lda cnt2
	ora cnt2+1
	beq fe_nf
	lda #0
	beq fe1
fe_ok
	ldy #1
	clc
	rts
fe_nf
	ldy #1
	sec
	rts
fe_err
	sec
	rts

; porownaj srch (0-terminowana) z dirent[0..38]; Z=1 gdy zgodne

cmpname
	ldx #0
cn1	lda srch,x
	beq cn_end
	jsr upcase
	sta tbyte
	lda dirent,x
	jsr upcase
	cmp tbyte
	bne cn_no
	inx
	cpx #39
	bcc cn1
	lda #0
	rts
cn_end
	cpx #39
	bcs cn_yes
	lda dirent,x
	beq cn2
	cmp #' '
	bne cn_no
cn2	inx
	bne cn_end
cn_yes
	lda #0
	rts
cn_no
	lda #1
	rts

upcase
	cmp #'a'
	bcc uc1
	cmp #'z'+1
	bcs uc1
	and #$DF
uc1	rts

; ===========================================================================
; PARSOWANIE NAZWY
; ===========================================================================

; z (ICBALZ): "F:NAZWA" lub "F:STARA,NOWA" -> fnbuf/fnlen, nnbuf/nnlen

parsefn
	lda #0
	sta fnlen
	sta nnlen
	sta fnbuf
	sta nnbuf
	ldy #0
pf1	lda (ICBALZ),y
	cmp #':'
	beq pf2
	iny
	cpy #16
	bcc pf1
	ldy #255	; brak ':' - cala nazwa od poczatku
pf2	iny
	ldx #0
pf3	lda (ICBALZ),y
	beq pf_end
	cmp #EOL
	beq pf_end
	cmp #','
	beq pf_sec
	and #$7F
	sta fnbuf,x
	iny
	inx
	cpx #39
	bcc pf3
pf_end
	lda #0
	sta fnbuf,x
	stx fnlen
	rts
pf_sec
	lda #0
	sta fnbuf,x
	stx fnlen
	iny
	ldx #0
pf4	lda (ICBALZ),y
	beq pf5
	cmp #EOL
	beq pf5
	and #$7F
	sta nnbuf,x
	iny
	inx
	cpx #39
	bcc pf4
pf5	lda #0
	sta nnbuf,x
	stx nnlen
	rts

; czy fnbuf zawiera '*' lub '?': Z=1 gdy brak

haswild
	ldx #0
hw1	lda fnbuf,x
	beq hw2
	cmp #'*'
	beq hw3
	cmp #'?'
	beq hw3
	inx
	cpx #39
	bcc hw1
hw2	lda #0
	rts
hw3	lda #1
	rts

; ===========================================================================
; BUFOR ZAPISU
; ===========================================================================

; oproznij bufor zapisu; wyjscie: Y = status, N wg Y

flush
	lda wcnt
	bne fl0
	ldy #1
fl_rts	rts
fl0
	clc
	lda wstart
	adc wcnt
	sta endp
	lda wstart+1
	adc #0
	sta endp+1
	lda wstart+2
	adc #0
	sta endp+2
	sec
	lda flen
	sbc endp
	lda flen+1
	sbc endp+1
	lda flen+2
	sbc endp+2
	bcs fl2
	lda endp
	sta skb
	lda endp+1
	sta skb+1
	lda endp+2
	sta skb+2
	jsr fsetlen
	bmi fl_rts
	lda endp
	sta flen
	lda endp+1
	sta flen+1
	lda endp+2
	sta flen+2
fl2
	lda dvpos
	cmp wstart
	bne fl3
	lda dvpos+1
	cmp wstart+1
	bne fl3
	lda dvpos+2
	cmp wstart+2
	beq fl4
fl3
	lda wstart
	sta skb
	lda wstart+1
	sta skb+1
	lda wstart+2
	sta skb+2
	jsr dseek
	bpl fl4
fl_rt2	rts
fl4
	lda #$25
	ldy #$80
	jsr sdcb
	lda wcnt
	sta DAUX1
	sta DBYTLO
	lda #0
	sta DBYTHI
	lda w_wrbuf
	sta DBUFLO
	lda w_wrbuf+1
	sta DBUFHI
	jsr gosio
	bmi fl_rt2
	lda endp
	sta dvpos
	lda endp+1
	sta dvpos+1
	lda endp+2
	sta dvpos+2
	lda #0
	sta wcnt
	ldy #1
	rts

; ===========================================================================
; BUFOR ODCZYTU
; ===========================================================================

; napelnij bufor odczytu (zaklada rcnt=0 i fpos<flen); Y = status, N wg Y

refill
	jsr syncpos
	bmi rf_err
	sec
	lda flen
	sbc fpos
	sta cbyte
	lda flen+1
	sbc fpos+1
	sta tbyte
	lda flen+2
	sbc fpos+2
	ora tbyte
	bne rf_128
	lda cbyte
	cmp #128
	bcc rf_go
rf_128
	lda #128
rf_go
	sta cbyte
	lda #$24
	ldy #$40
	jsr sdcb
	lda cbyte
	sta DAUX1
	sta DBYTLO
	lda #0
	sta DBYTHI
	lda w_rdbuf
	sta DBUFLO
	lda w_rdbuf+1
	sta DBUFHI
	jsr gosio
	bmi rf_err
	lda cbyte
	sta rcnt
	lda #0
	sta rptr
	clc
	lda dvpos
	adc cbyte
	sta dvpos
	lda dvpos+1
	adc #0
	sta dvpos+1
	lda dvpos+2
	adc #0
	sta dvpos+2
	ldy #1
rf_err	rts

; ===========================================================================
; HANDLER CIO: OPEN
; ===========================================================================

; sprawdz wlasciciela kanalu: Z=1 gdy X+1 == chown

ckown
	lda chown
	beq ck1
	stx tbyte
	inc tbyte
	cmp tbyte
ck1	rts

dopen
	stx iocbx
	lda chown
	beq op0
	ldy #ETOOMANY
	rts
op0
	jsr sdstat
	bpl op1
	rts		; blad SIO (Y ustawione)
op1
	cmp #0
	bne op2
	ldy #ENOCARD
	rts
op2
	jsr parsefn
	lda ICAX1Z
	cmp #6
	beq jodir
	cmp #7
	beq jodir
	cmp #4
	beq ord
	cmp #8
	beq owr
	cmp #9
	beq oap
	cmp #12
	beq oup
	ldy #EBADMOD
o_rts	rts
jodir	jmp odir

; --- odczyt ---
ord
	jsr opncomm
	bmi o_rts
	jsr fgetlen
	bmi o_rts
	jmp op_fin

; --- zapis (tworzy/obcina) ---
owr
	lda fnlen
	beq op_bad
	lda #1
	jsr fopen
	bmi o_rts
	lda #0
	sta skb
	sta skb+1
	sta skb+2
	jsr fsetlen
	bmi o_rts
	lda #0
	sta flen
	sta flen+1
	sta flen+2
	jmp op_fin

; --- dopisywanie ---
oap
	jsr opncomm
	bmi o_rts
	jsr fgetlen
	bmi o_rts
	lda flen
	sta fpos
	lda flen+1
	sta fpos+1
	lda flen+2
	sta fpos+2
	jmp op_fin2

; --- odczyt+zapis ---
oup
	jsr opncomm
	bmi o_rts
	jsr fgetlen
	bmi o_rts
	jmp op_fin

op_bad
	ldy #EBADNAM
	rts

; wspolne otwarcie istniejacego pliku

opncomm
	lda fnlen
	beq oc1
	lda #3
	jmp fopen
oc1
	pla		; zdejmij adres powrotu i zglos blad
	pla
	ldy #EBADNAM
	rts

op_fin
	lda #0
	sta fpos
	sta fpos+1
	sta fpos+2
op_fin2
	lda #0
	sta dvpos
	sta dvpos+1
	sta dvpos+2
	sta rcnt
	sta rptr
	sta wcnt
	lda ICAX1Z
	sta chmode
	lda iocbx
	sta tbyte
	inc tbyte
	lda tbyte
	sta chown
	ldy #1
	rts

; --- katalog ---
odir
	jsr fn2srch
	jsr mkmask
	lda #3
	jsr sendmask
	bmi od_rts
	jsr getcnt
	bmi od_rts
	lda cnt2
	sta dircnt
	sta dtot
	lda cnt2+1
	sta dircnt+1
	sta dtot+1
	lda #1
	sta dirfrst
	lda #0
	sta dphase
	sta dfoot
	lda #6
	sta chmode
	lda iocbx
	sta tbyte
	inc tbyte
	lda tbyte
	sta chown
	ldy #1
od_rts	rts

; ===========================================================================
; HANDLER CIO: CLOSE
; ===========================================================================

dclose
	jsr ckown
	beq cl1
	ldy #1
	rts
cl1
	lda chmode
	cmp #6
	beq cl2
	jsr flush
	bmi cl3
cl2	ldy #1
cl3
	lda #0
	sta chown
	rts

; ===========================================================================
; HANDLER CIO: GET
; ===========================================================================

dget
	jsr ckown
	beq gt0
	ldy #ENOTOPEN
	rts
gt0
	lda chmode
	cmp #6
	beq dirget
	cmp #8
	beq gt_wo
	cmp #9
	beq gt_wo
	lda wcnt
	beq gt1
	jsr flush
	bmi gt_err
gt1
	lda fpos
	cmp flen
	bne gt2
	lda fpos+1
	cmp flen+1
	bne gt2
	lda fpos+2
	cmp flen+2
	bne gt2
	ldy #EEOF
	rts
gt2
	lda rcnt
	bne gt3
	jsr refill
	bmi gt_err
gt3
	ldx rptr
	lda rdbuf,x
	sta cbyte
	inc rptr
	dec rcnt
	jsr ipos
	jsr atend
	lda cbyte
gt_err	rts
gt_wo
	ldy #EWRONLY
	rts

; --- listing katalogu ---

dgeof
	ldy #EEOF
	rts

dirget
	lda dphase
	cmp #1
	beq dgline
	cmp #2
	beq dgeof
	lda dircnt
	ora dircnt+1
	beq dgfoot
	lda dirfrst
	jsr getent
	bmi dg_err
	lda #0
	sta dirfrst
	lda dircnt
	bne dg1
	dec dircnt+1
dg1	dec dircnt
	jsr fmtline
	lda #0
	sta lptr
	lda #1
	sta dphase
dgline
	ldx lptr
	lda linebuf,x
	sta cbyte
	inc lptr
	lda lptr
	cmp llen
	bcc dg2
	lda dfoot
	beq dg3
	lda #2
	sta dphase
	lda cbyte
	ldy #3
	rts
dg3	lda #0
	sta dphase
dg2	lda cbyte
	ldy #1
dg_err	rts
dgfoot
	jsr fmtfoot
	lda #0
	sta lptr
	lda #1
	sta dphase
	sta dfoot
	jmp dgline

; zbuduj linie z dirent -> linebuf

fmtline
	ldx #0
fm1	lda dirent,x
	beq fm2
	sta linebuf,x
	inx
	cpx #39
	bcc fm1
fm2
	cpx #0
	beq fm4
fm3	lda linebuf-1,x
	cmp #' '
	bne fm4
	dex
	bne fm3
fm4
	lda #' '
	sta linebuf,x
	inx
	lda dirent+39
	cmp #1
	bne fm_fil
	ldy #0
fm5	lda dirstr,y
	sta linebuf,x
	inx
	iny
	cpy #5
	bcc fm5
	jmp fm_eol
fm_fil
	lda dirent+44
	sta num32
	lda dirent+45
	sta num32+1
	lda dirent+46
	sta num32+2
	lda dirent+47
	sta num32+3
	jsr prnum
fm_eol
	lda #EOL
	sta linebuf,x
	inx
	stx llen
	rts

dirstr	dta c'<DIR>'
footstr	dta c' WPISOW'

; stopka: "NNN WPISOW"

fmtfoot
	lda dtot
	sta num32
	lda dtot+1
	sta num32+1
	lda #0
	sta num32+2
	sta num32+3
	ldx #0
	jsr prnum
	ldy #0
ff1	lda footstr,y
	sta linebuf,x
	inx
	iny
	cpy #7
	bcc ff1
	lda #EOL
	sta linebuf,x
	inx
	stx llen
	rts

; drukuj num32 dziesietnie do linebuf od X; wyjscie: X za liczba

prnum
	stx pnx
	lda #0
	sta pnflag
	ldy #0
pn_pow
	lda #0
	sta digit
pn_sub
	sec
	lda num32
	sbc pow10,y
	sta t32
	lda num32+1
	sbc pow10+1,y
	sta t32+1
	lda num32+2
	sbc pow10+2,y
	sta t32+2
	lda num32+3
	sbc pow10+3,y
	sta t32+3
	bcc pn_dig
	lda t32
	sta num32
	lda t32+1
	sta num32+1
	lda t32+2
	sta num32+2
	lda t32+3
	sta num32+3
	inc digit
	jmp pn_sub
pn_dig
	cpy #36
	beq pn_prt
	lda digit
	bne pn_prt
	lda pnflag
	beq pn_nxt
pn_prt
	lda digit
	ora #$30
	ldx pnx
	sta linebuf,x
	inc pnx
	lda #1
	sta pnflag
pn_nxt
	iny
	iny
	iny
	iny
	cpy #40
	bcc pn_pow
	ldx pnx
	rts

; ===========================================================================
; HANDLER CIO: PUT
; ===========================================================================

dput
	sta cbyte
	jsr ckown
	beq pt0
	ldy #ENOTOPEN
	rts
pt0
	lda chmode
	cmp #4
	beq pt_ro
	cmp #6
	beq pt_ro
	lda rcnt
	beq pt1
	lda #0
	sta rcnt
	sta rptr
pt1
	lda wcnt
	bne pt2
	lda fpos
	sta wstart
	lda fpos+1
	sta wstart+1
	lda fpos+2
	sta wstart+2
pt2
	ldx wcnt
	lda cbyte
	sta wrbuf,x
	inc wcnt
	jsr ipos
	lda wcnt
	cmp #128
	bcc pt3
	jsr flush
	bmi pt_err
pt3
	ldy #1
pt_err	rts
pt_ro
	ldy #ERDONLY
	rts

; ===========================================================================
; HANDLER CIO: STATUS
; ===========================================================================

dstat
	jsr sdstat
	bmi st1
	sta DVSTAT
	lda #0
	sta DVSTAT+1
	sta DVSTAT+2
	sta DVSTAT+3
	ldy #1
st1	rts

; ===========================================================================
; HANDLER CIO: SPECIAL (XIO)
; ===========================================================================

dspec
	lda ICCOMZ
	cmp #37
	beq j_point
	cmp #38
	beq j_note
	cmp #39
	beq j_getfl
	cmp #32
	beq j_ren
	cmp #33
	beq j_del
	cmp #42
	beq j_mkd
	cmp #43
	beq j_rmd
	cmp #44
	beq j_cwd
	cmp #48
	beq j_gcwd
	ldy #ENOTIMP
	rts

j_point	jmp xpoint
j_note	jmp xnote
j_getfl	jmp xgetfl
j_ren	jmp xren
j_del	jmp xdel
j_mkd	jmp xmkd
j_rmd	jmp xrmd
j_cwd	jmp xcwd
j_gcwd	jmp xgcwd

; kanal musi byc otwartym plikiem (nie katalogiem)

ckfile
	jsr ckown
	beq cf1
	pla
	pla
	ldy #ENOTOPEN
	rts
cf1	lda chmode
	cmp #6
	bne cf2
	pla
	pla
	ldy #ENOTOPEN
cf2	rts

; operacje katalogowe niedozwolone przy otwartym listingu katalogu

cknodir
	lda chown
	beq cd2
	lda chmode
	cmp #6
	bne cd2
	pla
	pla
	ldy #ETOOMANY
cd2	rts

; --- XIO 37: POINT (pozycja w ICAX3/4/5) ---

xpoint
	jsr ckfile
	stx xsave
	jsr flush
	bmi xp_err
	lda #0
	sta rcnt
	sta rptr
	ldx xsave
	sec
	lda flen
	sbc ICAX3,x
	lda flen+1
	sbc ICAX4,x
	lda flen+2
	sbc ICAX5,x
	bcs xp1
	ldy #EPOINT
	rts
xp1
	lda ICAX3,x
	sta fpos
	lda ICAX4,x
	sta fpos+1
	lda ICAX5,x
	sta fpos+2
	ldy #1
xp_err	rts

; --- XIO 38: NOTE ---

xnote
	jsr ckfile
	lda fpos
	sta ICAX3,x
	lda fpos+1
	sta ICAX4,x
	lda fpos+2
	sta ICAX5,x
	ldy #1
	rts

; --- XIO 39: dlugosc pliku -> ICAX3/4/5 ---

xgetfl
	jsr ckfile
	lda flen
	sta ICAX3,x
	lda flen+1
	sta ICAX4,x
	lda flen+2
	sta ICAX5,x
	ldy #1
	rts

; --- XIO 32: RENAME "F:stara,nowa" ---

xren
	jsr cknodir
	jsr parsefn
	lda fnlen
	beq xr_bad
	lda nnlen
	beq xr_bad
	jsr fn2srch
	lda #3
	jsr findent
	bcs xr_nf
	ldx #0
xr1	lda nnbuf,x
	beq xr2
	sta objbuf,x
	inx
	cpx #39
	bcc xr1
xr2
	lda #0
xr3	cpx #39
	bcs xr4
	sta objbuf,x
	inx
	bne xr3
xr4
	ldx #39
xr5	lda dirent,x
	sta objbuf,x
	inx
	cpx #54
	bcc xr5
	lda #$0D
	ldy #$80
	jsr sdcb
	jsr bufobj54
	lda #EPERM
	sta xerr
	jsr gosio
	jmp nakmap
xr_bad
	ldy #EBADNAM
	rts
xr_nf
	bmi xr_e
	ldy #ENFOUND
xr_e	rts

; --- XIO 33: DELETE (z maska) ---

xdel
	jsr cknodir
	jsr parsefn
	lda fnlen
	beq xd_bad
	jsr haswild
	bne xd_mask
	jsr fn2srch
	lda #2
	jsr findent
	bcs xd_nf
	jsr delent
	jmp nakmap
xd_bad
	ldy #EBADNAM
	rts
xd_nf
	bmi xd_e
	ldy #ENFOUND
xd_e	rts
xd_mask
	lda #0
	sta frstfl
	jsr fn2srch
	jsr mkmask
	lda #2
	jsr sendmask
	bmi xd_e
xd_lp
	jsr getcnt
	bmi xd_e
	lda cnt2
	ora cnt2+1
	beq xd_fin
	lda #1
	jsr getent
	bmi xd_e
	lda #1
	sta frstfl
	jsr delent
	bmi xd_de
	jmp xd_lp
xd_de
	jmp nakmap
xd_fin
	lda frstfl
	bne xd_ok
	ldy #ENFOUND
	rts
xd_ok
	ldy #1
	rts

; skasuj obiekt opisany w dirent ($0C)

delent
	lda #$0C
	ldy #$80
	jsr sdcb
	jsr bufdire
	lda #EPERM
	sta xerr
	jmp gosio

; --- XIO 42: MKDIR ---

xmkd
	jsr parsefn
	lda fnlen
	beq xm_bad
	ldx #0
xm1	lda fnbuf,x
	beq xm2
	sta objbuf,x
	inx
	cpx #39
	bcc xm1
xm2
	lda #0
xm3	cpx #39
	bcs xm4
	sta objbuf,x
	inx
	bne xm3
xm4
	lda #$0B
	ldy #$80
	jsr sdcb
	lda #1
	sta DAUX1
	jsr bufobj39
	lda #EEXIST
	sta xerr
	jsr gosio
	jmp nakmap
xm_bad
	ldy #EBADNAM
	rts

; --- XIO 43: RMDIR ---

xrmd
	jsr cknodir
	jsr parsefn
	lda fnlen
	beq xm_bad
	jsr fn2srch
	lda #1
	jsr findent
	bcs xv_nf
	jsr delent
	jmp nakmap
xv_nf
	bmi xv_e
	ldy #EDIRNF
xv_e	rts

; --- XIO 44: CHDIR "F:A>B" / "F:<" / "F:" ---

xcwd
	jsr cknodir
	jsr parsefn
	lda #0
	sta cbyte
	lda fnbuf
	bne xc_lp
	jmp xc_root	; "F:" -> katalog glowny
xc_lp
	ldy cbyte
	lda fnbuf,y
	bne xc1
	ldy #1
	rts
xc1
	cmp #'>'
	beq xc_sep
	cmp #'\'
	beq xc_sep
	ldx #0
xc2	lda fnbuf,y
	beq xc3
	cmp #'>'
	beq xc3
	cmp #'\'
	beq xc3
	sta srch,x
	iny
	inx
	cpx #39
	bcc xc2
xc3
	sty cbyte
	lda #0
	sta srch,x
	lda srch
	cmp #'<'
	bne xc4
	lda srch+1
	beq xc_up
xc4
	lda srch
	cmp #'.'
	bne xc5
	lda srch+1
	cmp #'.'
	bne xc5
	lda srch+2
	beq xc_up
xc5
	lda #1
	jsr findent
	bcs xc_nf
	lda #$05
	ldy #$80
	jsr sdcb
	jsr bufdire
	lda #EDIRNF
	sta xerr
	jsr gosio
	bmi xc_de
	jmp xc_lp
xc_de
	jmp nakmap
xc_nf
	bmi xc_e
	ldy #EDIRNF
xc_e	rts
xc_sep
	inc cbyte
	ldy cbyte
	cpy #1
	beq xc_root
	jmp xc_lp
xc_root
	lda #$07
	ldy #$00
	jsr sdcb
	jsr gosio
	bmi xc_e
	jmp xc_lp
xc_up
	lda #$06
	ldy #$00
	jsr sdcb
	jsr gosio
	bmi xc_e
	jmp xc_lp

; --- XIO 48: GETCWD -> bufor uzytkownika + EOL ---

xgcwd
	lda #$08
	ldy #$40
	jsr sdcb
	jsr bufdire
	jsr gosio
	bmi xg_e
	ldy #0
xg1	lda dirent,y
	beq xg2
	cmp #' '
	beq xg2
	sta (ICBALZ),y
	iny
	cpy #39
	bcc xg1
xg2	lda #EOL
	sta (ICBALZ),y
	ldy #1
xg_e	rts

; ===========================================================================
; REZYDENTNA (RE)INSTALACJA
; ===========================================================================

; wpis do HATABS (pomija, gdy litera juz jest)

hinst
	ldy #0
hi1	lda HATABS,y
	beq hi_free
	cmp devltr
	beq hi_done
	iny
	iny
	iny
	cpy #36
	bcc hi1
	rts
hi_free
	lda devltr
	sta HATABS,y
	lda w_htab
	sta HATABS+1,y
	lda w_htab+1
	sta HATABS+2,y
hi_done	rts

hinit
	ldy #1
	rts

; hak DOSINI: wywolaj poprzedni, potem odtworz wpis i MEMLO

reshook
	jsr $FFFF	; operand podmieniany przy instalacji
	jsr hinst
	lda w_rese
	sta MEMLO
	lda w_rese+1
	sta MEMLO+1
	lda #0
	sta chown
	sta wcnt
	sta rcnt
	rts

; ===========================================================================
; BUFORY REZYDENTNE
; ===========================================================================

fnbuf	:40 dta 0
nnbuf	:40 dta 0
srch	:40 dta 0
maskbuf	:16 dta 0
dirent	:54 dta 0
objbuf	:54 dta 0
linebuf	:64 dta 0
rdbuf	:128 dta 0
wrbuf	:128 dta 0

resend			; koniec czesci rezydentnej

; ===========================================================================
; CZESC INSTALACYJNA (odrzucana po instalacji)
; ===========================================================================

forced	dta 0
argy	dta 0
dtry	dta 0

w_mban	dta a(m_ban)
w_mnod	dta a(m_nodev)
w_mfrc	dta a(m_force)
w_mfnd	dta a(m_found)
w_mold	dta a(m_oldfw)
w_mcnf	dta a(m_conf)
w_mful	dta a(m_full)
w_mins	dta a(m_inst)
w_mhis	dta a(m_his)

; drukuj komunikat: A=lo, X=hi

pmsg
	sta ICBAL0
	stx ICBAH0
	lda #9		; PUTREC
	sta ICCOM0
	lda #$FF
	sta ICBLL0
	lda #0
	sta ICBLH0
	ldx #0
	jmp CIOV

install
	lda w_mban
	ldx w_mban+1
	jsr pmsg

; --- parametry z linii polecen (tylko pod SpartaDOS) ---

	lda $0700
	cmp #'S'
	bne noargs
	ldy #10		; BUFOFF
	lda (DOSVEC),y
	clc
	adc #63		; LBUF
	sta argy
ag_lp
	ldy argy
	cpy #208
	bcs noargs
	lda (DOSVEC),y
	cmp #EOL
	beq noargs
	cmp #'/'
	beq ag_sw
	cmp #'a'
	bcc ag_1
	cmp #'z'+1
	bcs ag_1
	and #$DF
ag_1
	cmp #'A'
	bcc ag_nx
	cmp #'Z'+1
	bcs ag_nx
	sta devltr
	jmp ag_nx
ag_sw
	inc argy
	ldy argy
	lda (DOSVEC),y
	cmp #EOL
	beq noargs
	cmp #'0'
	bcc ag_nx
	cmp #'4'
	bcs ag_nx
	and #$0F
	clc
	adc #SIOBASE
	sta devid
	lda #1
	sta forced
ag_nx
	inc argy
	jmp ag_lp
noargs

; --- patch HISIO? (wariant SIO2BT sonduje $53/$3F kazde urzadzenie) ---

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
hs_yes
	lda #$28
	sta siomode
	lda w_mhis
	ldx w_mhis+1
	jsr pmsg
hs_no

; --- wykrywanie urzadzenia ---

	lda forced
	bne dt_frc
	lda #SIOBASE
	sta devid
dt_lp
	jsr detst
	bpl dt_ok
	inc devid
	lda devid
	cmp #SIOBASE+4
	bcc dt_lp
	lda w_mnod
	ldx w_mnod+1
	jmp pmsg	; koniec bez instalacji
dt_frc
	jsr detst
	bpl dt_ok
	lda w_mfrc
	ldx w_mfrc+1
	jsr pmsg
	jmp dt_go
dt_ok

; --- wersja firmware ---

	lda #$11
	ldy #$40
	jsr sdcb
	jsr buftmp1
	jsr gosio
	bmi fw_old
	lda devid
	and #$0F
	ora #$30
	sta m_fid
	lda tmpb
	lsr @
	lsr @
	lsr @
	lsr @
	ora #$30
	sta m_fw1
	lda tmpb
	and #$0F
	ora #$30
	sta m_fw2
	lda w_mfnd
	ldx w_mfnd+1
	jsr pmsg
	lda tmpb
	lsr @
	lsr @
	lsr @
	lsr @
	cmp #3
	bcs dt_go
fw_old
	lda w_mold
	ldx w_mold+1
	jmp pmsg	; koniec bez instalacji
dt_go

; --- kolizja litery? ---

	ldy #0
cf_lp
	lda HATABS,y
	cmp devltr
	bne cf_nx
	lda w_mcnf
	ldx w_mcnf+1
	jmp pmsg	; koniec bez instalacji
cf_nx
	iny
	iny
	iny
	cpy #36
	bcc cf_lp

; --- wpis HATABS ---

	jsr hinst
	ldy #0
vf_lp
	lda HATABS,y
	cmp devltr
	beq vf_ok
	iny
	iny
	iny
	cpy #36
	bcc vf_lp
	lda w_mful
	ldx w_mful+1
	jmp pmsg	; brak miejsca - koniec bez instalacji
vf_ok

; --- hak DOSINI + MEMLO ---

	lda DOSINI
	sta reshook+1
	lda DOSINI+1
	sta reshook+2
	lda w_hook
	sta DOSINI
	lda w_hook+1
	sta DOSINI+1
	lda w_rese
	sta MEMLO
	lda w_rese+1
	sta MEMLO+1

	lda devltr
	sta m_iltr
	lda w_mins
	ldx w_mins+1
	jmp pmsg	; koniec - czesc rezydentna pozostaje

; test obecnosci urzadzenia (krotki timeout, do 3 prob -
; pierwsza moze zostac zjedzona przez sondowanie obcego patcha SIO)

detst
	lda #3
	sta dtry
dts_1
	lda #$00
	ldy #$40
	jsr sdcb
	lda #2
	sta DTIMLO
	jsr buftmp1
	jsr gosio
	bpl dts_9
	dec dtry
	bne dts_1
	ldy DSTATS
dts_9	rts

; --- komunikaty ---

m_ban	dta c'SIO2SD.SYS v1.0 - sterownik karty SD',EOL
m_nodev	dta c'Blad: brak SIO2SD na SIO $72-$75',EOL
m_force	dta c'Uwaga: SIO2SD nie odpowiada, instaluje',EOL
m_found	dta c'SIO2SD na ID $7'
m_fid	dta c'?'
	dta c', firmware '
m_fw1	dta c'?'
	dta c'.'
m_fw2	dta c'?',EOL
m_oldfw	dta c'Blad: wymagane firmware 3.x',EOL
m_conf	dta c'Blad: litera urzadzenia zajeta',EOL
m_full	dta c'Blad: brak miejsca w HATABS',EOL
m_his	dta c'HISIO wykryty - wejscie $CFED',EOL
m_inst	dta c'Zainstalowano urzadzenie '
m_iltr	dta c'F'
	dta c': (karta SD)',EOL

	blk update address
	end
