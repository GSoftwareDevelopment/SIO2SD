; ---------------------------------------------------------------------------
; xexboot - 2-sektorowy bootloader plikow XEX dla wirtualnych dyskow
; emulacji SIO2SD (altirra/sio2sd_server.py).
;
; Uklad dysku (sektory 128-bajtowe):
;   sektor 1-3: ten loader (naglowek boot + kod, 384 bajty)
;   sektor 4+ : plik XEX bajt po bajcie (bez naglowkow sektorowych)
;
; Serwer wpisuje dlugosc pliku XEX (24 bity LE) pod offsetem 9
; pierwszego sektora (etykieta xexlen).
;
; Budowanie: python3 tools/build_xexboot.py  ->  altirra/xexboot.bin
; ---------------------------------------------------------------------------

DSKINV	= $E453
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
RUNAD	= $02E0
INITAD	= $02E2
COLDST	= $0244
BOOTQ	= $09

zp	= $43		; wskaznik roboczy (FMSZPG - wolny podczas bootu)
secbuf	= $0900		; bufor sektora (poza obszarem loadera)

	blk sparta $0700

; --- naglowek boot (6 bajtow) ---

	dta 0		; flagi
	dta 3		; liczba sektorow bootu
	dta a($0700)	; adres ladowania
	dta a(bdone)	; wektor init (nieuzywany)

; $0706: OS wywoluje ten adres po zaladowaniu sektorow bootu

	jmp boot

; $0709: dlugosc pliku XEX (patchowana przez serwer!)

xexlen	dta 0,0,0

boot
	lda #1
	sta BOOTQ
	lda #0
	sta COLDST
	sta RUNAD
	sta RUNAD+1
	sta frst
	sta frst+1
	sta havrun
	sta cursec+1
	lda #4
	sta cursec	; dane XEX od sektora 4
	lda #128
	sta bufp	; wymus odczyt pierwszego sektora

	jsr getb	; naglowek $FF $FF
	cmp #$FF
	beq h1ok
bfj0	jmp bfail
h1ok	jsr getb
	cmp #$FF
	bne bfj0

seglp
	lda xexlen
	ora xexlen+1
	ora xexlen+2
	bne sl_0
	jmp bdone	; czysty koniec pliku
sl_0
	jsr getb	; adres poczatku segmentu
	sta zp
	jsr getb
	sta zp+1
	lda zp
	and zp+1
	cmp #$FF
	bne sl_1
	jmp seglp	; powtorzony naglowek $FFFF
sl_1
	lda frst	; zapamietaj pierwszy segment
	ora frst+1
	bne sl_2
	lda zp
	sta frst
	lda zp+1
	sta frst+1
sl_2
	jsr getb	; adres konca segmentu
	sta endl
	jsr getb
	sta endh
	lda #0
	sta INITAD
	sta INITAD+1
cplp
	jsr getb
	ldy #0
	sta (zp),y
	lda zp
	cmp endl
	bne cnx
	lda zp+1
	cmp endh
	beq cdon
cnx
	inc zp
	bne cplp
	inc zp+1
	jmp cplp
cdon
	lda INITAD	; segment ustawil INITAD?
	ora INITAD+1
	beq noini
	jsr doini
noini
	lda RUNAD
	ora RUNAD+1
	beq norun
	lda #1
	sta havrun
norun
	jmp seglp

doini
	jmp (INITAD)

bdone
	lda havrun
	bne brun
	lda frst	; brak RUNAD: startuj od pierwszego segmentu
	sta RUNAD
	lda frst+1
	sta RUNAD+1
brun
	jmp (RUNAD)

bfail
	jmp bfail	; zly plik - stop

; --- kolejny bajt strumienia XEX ---

getb
	ldx bufp
	cpx #128
	bcc gb_1
	jsr rdsec
	ldx #0
gb_1
	lda secbuf,x
	inx
	stx bufp
	pha		; xexlen--
	lda xexlen
	bne gb_2
	lda xexlen+1
	bne gb_3
	dec xexlen+2
gb_3	dec xexlen+1
gb_2	dec xexlen
	pla
	rts

; --- odczyt sektora cursec do secbuf ---

rdsec
	lda #$31
	sta DDEVIC
	lda #1
	sta DUNIT
	lda #$52
	sta DCOMND
	lda #$40
	sta DSTATS
	lda w_buf
	sta DBUFLO
	lda w_buf+1
	sta DBUFHI
	lda #128
	sta DBYTLO
	lda #0
	sta DBYTHI
	lda cursec
	sta DAUX1
	lda cursec+1
	sta DAUX2
	lda #7
	sta DTIMLO
	jsr DSKINV
	bmi bfailj
	inc cursec
	bne rd_9
	inc cursec+1
rd_9	rts
bfailj	jmp bfail

w_buf	dta a(secbuf)
frst	dta 0,0
havrun	dta 0
endl	dta 0
endh	dta 0
bufp	dta 0
cursec	dta 0,0

	end
