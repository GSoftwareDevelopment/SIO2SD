; ---------------------------------------------------------------------------
; SDCDEV.SYS v2.6
; Natywne urzadzenie plikowe jadra SpartaDOS X: SDC1:-SDC4: = karta SD
; w SIO2SD o ID 0-3 (SIO $72-$75, patrz SIOBASE). Umozliwia DIR, CD, MKDIR, RMDIR, COPY,
; REN, DEL, sciezki i wildcardy - obsluga przez jadro SDX.
;
; Wymagania: SpartaDOS X 4.40+ (rejestracja urzadzen jadra), SIO2SD fw 3.x
;
; Instalacja: SDCDEV [/0../3 | /F] [/M<n>] [/H]
;   (bez opcji) - SDC1:-SDC4: = SIO2SD o ID 0-3 (skan informacyjny)
;   /0../3      - sprawdz tylko wskazane ID i zamapuj je na SDC1:
;                 (SDC2:-SDC4: wylaczone); instaluje takze bez odpowiedzi
;   /F          - przeskanuj ID 0-3 i zamapuj PIERWSZE znalezione na SDC1:;
;                 gdy zadne nie odpowiada - nie instaluje w ogole
;   /M<n>       - maks. rownoczesnie otwartych plikow (n=1..4, domyslnie 2);
;                 ograniczenie funkcjonalne (nie zmienia zajetosci pamieci)
;   /H          - sprobuj wysokiej predkosci SIO (turbo). Sonduje SIO2SD
;                 komenda $1E z bitem $80 i przy powodzeniu dodaje $80 do
;                 kolejnych komend. Przy niepowodzeniu wraca do 19200.
; Assembler: MADS (mads SDCDEV.ASM -o:SDCDEV.SYS)
;
; Architektura wg SDX450 Programming Guide, rozdz. 18.3.2/24 (Kernel Interface):
;  - dispatcher funkcji kd_* (Y = kod funkcji, status w A),
;  - rejestracja w DEVNAME/dev_vector, mikrobufory COMTAB2,
;  - rezydencja przez dec INSTALL; instalator w bloku $0400 (nierezydentny),
;  - PODZIAL NA DWA BLOKI: rdzen (~670 B, blk reloc main) w pamieci glownej
;    <$4000 (trampolina devmain, warstwa SIO, petle transferu xferloop/dcopy;
;    dzialaja gdy przelaczony jest bank wolajacego), reszta (~6,5 KB,
;    blk reloc ext) w pamieci rozszerzonej PROGRAMU (indeks 4, banki PORTB);
;  - devmain: lda ext_m / V_setme / jsr devdisp / V_popme; ext_m pobierany
;    z EXTENDED wg rozdz. 18.3.2; wymaga SDX 4.47+ z bankami programu.
;
; Nazwy dlugie (do 39 znakow) sa mapowane na 8.3; nazwy niemieszczace sie
; dostaja forme NNNN_III.EXT, gdzie III = pozycja wpisu w katalogu
; (podkreslenie, bo SDX dopuszcza w nazwach tylko litery/cyfry/'_').
; ---------------------------------------------------------------------------

; --- symbole SDX (rozwiazywane przez loader) ---

INSTALL	smb 'INSTALL'
DEVNAME	smb 'DEVNAME'
DEVSPEC	smb 'DEVSPEC'
COMTAB2	smb 'COMTAB2'
EXTENDED smb 'EXTENDED'

; --- rownania systemowe ---

DOSVEC	= $0A
jkernel	= $0703
dev_index = $0740
dev_vector = $0750

K_FID	= $0760
K_DEV	= $0761
K_NAME	= $0762		; 11 bajtow NNNNNNNNXXX
K_XNAME	= $076D		; 11 bajtow (rename)
K_MODE	= $0778
K_SCAN	= $0779
K_ATTR	= $077A
K_ADDPOS = $0782	; 3 bajty
K_BYTBUF = $0785	; 2 bajty
K_MEMREIX = $0787
K_DENTRY = $0789	; 23 bajty
K_PATH	= $07A0		; 64 bajty

V_setme	= $07F1
V_popme	= $07F4

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

; strona zerowa (dozwolona dla sterownikow, nieuzywana przez SIOV)
zpt	= $3D		; wskaznik roboczy (2 bajty)
zpx	= $3F		; bajt roboczy

; --- kody bledow ---

EBADUNIT = 160		; bledny numer jednostki
ETOOMANY = 161		; brak wolnych uchwytow
ENOTOPEN = 133		; plik nie jest otwarty
EWRONLY	= 131		; otwarty tylko do zapisu
ERDONLY	= 135		; otwarty tylko do odczytu
EEOF	= 136		; koniec pliku
ENFOUND	= 170		; nie znaleziono pliku
EDIRNF	= 150		; nie znaleziono katalogu
EBADNAM	= 165		; bledna nazwa pliku
ENOTIMP	= 146		; funkcja nie zaimplementowana
ENOCARD	= 144		; brak karty / blad urzadzenia
EPERM	= 167		; operacja niedozwolona / katalog niepusty
EEXIST	= 151		; plik/katalog istnieje
ERANGE	= 166		; pozycja poza plikiem
ENAK	= 139		; NAK z SIO

MAXH	= 4		; maks. rownoczesnych uchwytow
; adres SIO dla ID 0. sio2sd.org podaje $73+ID; sprzet testowy (fw 3.3)
; odpowiada na $72+ID (ID 0 -> $72), stad SIOBASE=$72. Zmien na $73 dla
; urzadzen zgodnych ze specyfikacja.
SIOBASE	= $72

	opt h-

; ===========================================================================
; INSTALATOR (blok o stalym adresie, nie zostaje w pamieci)
; ===========================================================================

	blk sparta $0400

inst
	ldx EXTENDED+1	; liczba blokow pamieci rozszerzonej programu
	lda EXTENDED+2,x	; indeks ostatniego (naszego bloku EXTRAM)
	sta ext_m
	lda w_mban
	ldx w_mban+1
	jsr pmsg

; /H nie skacze pod zadne wejscie BIOS-u. Szybkie SIO wykrywamy pozniej
; sonda komendy z bitem $80 i w razie sukcesu nadal wolamy zwykle SIOV.

; --- parametry z linii polecen: /0../3 lub /F ---

	lda $0700
	cmp #'S'
	beq pa_c1
pa_donej jmp pa_done	; trampolina (pa_done poza zasiegiem krotkich skokow)
pa_c1	ldy #10		; BUFOFF
	lda (DOSVEC),y
	clc
	adc #63		; LBUF
	sta argy
pa_lp	ldy argy
	cpy #200
	bcs pa_donej
	lda (DOSVEC),y
	cmp #EOL
	beq pa_donej
	cmp #'/'
	beq pa_sw
pa_nx	inc argy
	jmp pa_lp
pa_sw	inc argy
	ldy argy
	lda (DOSVEC),y
	cmp #EOL
	beq pa_donej
	cmp #'F'
	beq pa_f
	cmp #'f'
	beq pa_f
	cmp #'M'
	beq pa_m
	cmp #'m'
	beq pa_m
	cmp #'H'
	beq pa_h
	cmp #'h'
	beq pa_h
	cmp #'0'
	bcc pa_nx
	cmp #'4'
	bcs pa_nx
	and #$0F
	sta i_id
	lda #1
	sta i_mode
	jmp pa_nx
pa_f	lda #2
	sta i_mode
	jmp pa_nx
; /H: sprobuj wysokiej predkosci SIO (turbo) przez bit $80 komendy
pa_h	lda #1
	sta hsopt
	jmp pa_nx
; /M<n>: maks. otwartych plikow naraz (1-MAXH); brak/bledna cyfra -> bez zmiany
pa_donej2 jmp pa_done
pa_m	inc argy
	ldy argy
	lda (DOSVEC),y
	cmp #EOL
	beq pa_donej2
	cmp #'1'
	bcs pa_mdig
	jmp pa_nx
pa_mdig
	cmp #'0'+MAXH+1
	bcc pa_mok
	jmp pa_nx
pa_mok
	and #$0F
	sta nslots
	jmp pa_nx
pa_done

; --- detekcja wg trybu ---

	lda i_mode
	bne dt_1
	jmp d_all
dt_1	cmp #2
	beq d_fst

; /n: tylko wskazane ID (instaluje takze bez odpowiedzi)

	jsr probeid
	bpl d_onej
	lda i_id
	ora #$30
	sta m_wid
	lda w_mwrn
	ldx w_mwrn+1
	jsr pmsg
	jmp d_map	; bez komunikatu znaleziska
d_onej	jmp d_one

; /F: pierwsze znalezione ID; brak -> bez instalacji

d_fst	lda #0
	sta i_id
d_f1	jsr probeid
	bpl d_one
	inc i_id
	lda i_id
	cmp #4
	bcc d_f1
	lda w_mnof
	ldx w_mnof+1
	jmp pmsg	; koniec bez instalacji

d_one	lda #'1'
	sta m_unum
	lda w_mfnd
	ldx w_mfnd+1
	jsr pmsg
d_map	lda i_id
	sta umap
	lda #$FF
	sta umap+1
	sta umap+2
	sta umap+3
	lda i_id
	ora #$30
	sta m_iid
	jmp d_reg

; tryb domyslny: skan informacyjny ID 0-3, jednostki 1-4 = ID 0-3

d_all	ldx #0
da_1	stx i_ux
	txa
	sta i_id
	jsr probeid
	bmi da_2
	lda i_ux
	ora #$31
	sta m_unum
	lda #1
	sta i_any
	lda w_mfnd
	ldx w_mfnd+1
	jsr pmsg
da_2	ldx i_ux
	inx
	cpx #4
	bcs da_3
	jmp da_1
da_3	ldx #0		; przywroc mape 1:1
da_4	txa
	sta umap,x
	inx
	cpx #4
	bcc da_4
	lda i_any
	bne d_reg
	lda w_mnon
	ldx w_mnon+1
	jsr pmsg

; --- rejestracja urzadzenia w jadrze ---

d_reg
	lda DEVSPEC-1
	asl @
	asl @
	sta i_max
	ldx #0
i_scan
	lda DEVNAME,x
	cmp #' '
	beq i_free
	cmp #'S'
	bne i_next
	lda DEVNAME+1,x
	cmp #'D'
	bne i_next
	lda DEVNAME+2,x
	cmp #'C'
	bne i_next
	lda w_mdup
	ldx w_mdup+1
	jmp pmsg	; juz jest - koniec bez instalacji
i_next
	inx
	inx
	inx
	inx
	cpx i_max
	bcc i_scan
	lda w_mful
	ldx w_mful+1
	jmp pmsg	; brak miejsca - koniec bez instalacji
i_free
	txa
	lsr @
	lsr @
	sta i_dix
	lda #'S'
	sta DEVNAME,x
	lda #'D'
	sta DEVNAME+1,x
	lda #'C'
	sta DEVNAME+2,x
	lda i_dix
	asl @
	tax
	lda w_dmain
	sta dev_vector,x
	lda w_dmain+1
	sta dev_vector+1,x
	ldx i_dix
	lda i_bufb,x
	ora COMTAB2-1
	sta COMTAB2-1
	lda #0
	sta DEVSPEC,x
	ldy #8		; kd_initz
	jsr devmain
	jsr hstune		; /H: sprobuj turbo SIO (jesli podano)

; --- komunikat koncowy ---

	lda i_mode
	beq dr_all
	lda w_mins1
	ldx w_mins1+1
	jsr pmsg
	jmp dr_x
dr_all	lda w_mins
	ldx w_mins+1
	jsr pmsg
dr_x	dec INSTALL	; czesc relokowalna zostaje w pamieci
	rts

; proba ID z i_id (przez jednostke 1); firmware -> m_fw1/m_fw2
; wyjscie: A >= 0 znaleziono / A < 0 brak odpowiedzi

probeid
	lda i_id
	sta umap
	lda #0
	sta curux
	sta i_try
pb_1	lda #$00
	ldy #$40
	jsr sdcb
	lda #2
	sta DTIMLO
	jsr buftmp1
	jsr gosio
	bpl pb_ok
	inc i_try
	lda i_try
	cmp #3
	bcc pb_1
	lda #$FF
	rts
pb_ok	lda #'?'
	sta m_fw1
	sta m_fw2
	lda #$11
	ldy #$40
	jsr sdcb
	lda #2
	sta DTIMLO
	jsr buftmp1
	jsr gosio
	bmi pb_9
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
pb_9	lda #1
	rts



; drukuj komunikat: A=lo, X=hi

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

i_max	dta 0
i_dix	dta 0
i_ux	dta 0
i_any	dta 0
i_try	dta 0
i_mode	dta 0
i_id	dta 0
hsopt	dta 0
argy	dta 0
i_bufb	dta 1,2,4,8,16,32,64,128



; ===========================================================================
; CZESC REZYDENTNA (blok relokowalny - zostaje w pamieci po dec INSTALL)
; ===========================================================================

	blk reloc main

; ===========================================================================
; DANE/KOD INSTALACYJNE PRZENIESIONE TU, BY BLOK $0400 NIE WCHODZIL W STRONE 7
; (uzywane tylko podczas instalacji, ale rezydentne - kilkadziesiat B)
; ===========================================================================

; slowa adresowe komunikatow i wektora (relokowalne)
w_dmain	dta a(devmain)
w_mban	dta a(m_ban)
w_mdup	dta a(m_dup)
w_mful	dta a(m_ful)
w_mfnd	dta a(m_fnd)
w_mnon	dta a(m_non)
w_mins	dta a(m_ins)
w_mwrn	dta a(m_wrn)
w_mnof	dta a(m_nof)
w_mins1	dta a(m_ins1)
w_mhs0	dta a(m_hs0)
w_mhs1	dta a(m_hs1)

; --- /H: dostrajanie turbo SIO przez bit $80 komendy ---
; Najpierw odpytuje $1F|$80. Jesli BIOS/SIO/device obsluzy taki transfer,
; kolejne komendy dostaja bit $80 w gosio. Przy niepowodzeniu zostaje 19200.
hstune
	lda hsopt
	beq ht_ok		; brak /H
	lda #0
	sta curux		; odpytaj jednostke 1 (umap[0])
	lda #$9F		; turbo hIndex dla komend z bitem $80 ($1F|$80)
	ldy #$40
	jsr sdcb
	lda #2
	sta DTIMLO
	jsr buftmp1
	jsr gosio
	bmi ht_lo		; brak odpowiedzi -> 19200
	lda tmpb
	cmp #17
	bcs ht_lo		; 17=off / bledny indeks -> 19200
	lda #$80
	sta siomode		; tryb: dodawaj bit $80 i wolaj SIOV
	lda #$00		; samotest: status $00 przy turbo
	ldy #$40
	jsr sdcb
	lda #2
	sta DTIMLO
	jsr buftmp1
	jsr gosio
	bpl ht_hi		; dziala -> zostaw turbo
	lda #0			; nie dziala -> powrot do 19200
	sta siomode
ht_lo	lda w_mhs0
	ldx w_mhs0+1
	jmp pmsg
ht_hi	lda w_mhs1
	ldx w_mhs1+1
	jmp pmsg
ht_ok	rts


; ===========================================================================
; RDZEN W PAMIECI GLOWNEJ (blok 1, ponizej \$4000, zawsze zmapowany)
; ===========================================================================
; Trampolina wejscia + warstwa SIO + petla transferu (dzialaja takze, gdy
; przelaczony jest bank wolajacego) oraz zmienne czytane w tym oknie.

; --- trampolina: wlacz bank EXTRAM, wywolaj dispatcher, wylacz bank ---
devmain
	lda ext_m
	jsr V_setme
	jsr devdisp
	jmp V_popme
ext_m	dta 0		; indeks pamieci bloku EXTRAM (z EXTENDED)
nslots	dta 2		; maks. otwartych plikow (1-MAXH, /M<n>); 2 = minimum dla COPY

; --- zmienne rdzenia (czytane w oknie obcego banku) ---
curux	dta 0		; biezaca jednostka (0-3)
umap	dta 0,1,2,3	; mapa: jednostka -> ID SIO2SD ($FF = wylaczona)
siomode	dta 0		; 0 = zwykle SIOV, $80 = komendy z bitem high-speed
xerr	dta 0		; zamiennik bledu dla NAK
tmpb	dta 0
xfer	dta 0,0
xrem	dta 0,0
xadr	dta 0,0
xchn	dta 0
xcmd	dta 0
xdst	dta 0

w_tmpb	dta a(tmpb)

sdcb
	sta DCOMND
	sty DSTATS
	ldx curux
	lda umap,x
	clc
	adc #SIOBASE
	sta DDEVIC
	lda #1
	sta DUNIT
	lda #4
	sta DTIMLO
	lda #0
	sta DAUX1
	sta DAUX2
	rts

; SIO; wyjscie: A = status (N wg A)
; w trybie high-speed dodaje bit $80 do komendy i nadal uzywa SIOV.

gosio
	lda siomode
	bne gs_hs
	jsr SIOV
	tya
	rts
gs_hs	lda DCOMND
	pha
	ora #$80
	sta DCOMND
	jsr SIOV
	pla
	sta DCOMND
	tya
	rts

; SIO + zamiana NAK na xerr

gonak
	jsr gosio
	cmp #ENAK
	bne gn1
	lda xerr
gn1	ora #0
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

xferloop
	lda K_ADDPOS
	sta xadr
	lda K_ADDPOS+1
	sta xadr+1
	lda xfer
	sta xrem
	lda xfer+1
	sta xrem+1
	lda K_MEMREIX
	jsr V_setme
xf_lp	lda xrem
	ora xrem+1
	beq xf_done
	lda xrem+1
	bne xf_c1
	lda xrem
	cmp #240
	bcc xf_c2
xf_c1	lda #240
xf_c2	sta xchn
	lda xcmd
	ldy xdst
	jsr sdcb
	lda xchn
	sta DAUX1
	sta DBYTLO
	lda #0
	sta DBYTHI
	lda xadr
	sta DBUFLO
	lda xadr+1
	sta DBUFHI
	jsr gosio
	bmi xf_err
	clc
	lda xadr
	adc xchn
	sta xadr
	bcc xf_x1
	inc xadr+1
xf_x1	sec
	lda xrem
	sbc xchn
	sta xrem
	bcs xf_lp
	dec xrem+1
	jmp xf_lp
xf_done	jsr V_popme
	ldx cslot
	clc
	lda spos0,x
	adc xfer
	sta spos0,x
	lda spos1,x
	adc xfer+1
	sta spos1,x
	lda spos2,x
	adc #0
	sta spos2,x
	ldx curux
	clc
	lda udpos0,x
	adc xfer
	sta udpos0,x
	lda udpos1,x
	adc xfer+1
	sta udpos1,x
	lda udpos2,x
	adc #0
	sta udpos2,x
	lda #1
	rts
xf_err	pha
	jsr V_popme
	pla
	ora #0
	rts

; --- komunikaty instalatora (uzywane tylko podczas instalacji) ---
m_ban	dta c'SDCDEV.SYS v2.6 - karta SD (EXTRAM)',EOL
m_dup	dta c'SDC: juz zainstalowane',EOL
m_ful	dta c'Brak miejsca na urzadzenie',EOL
m_fnd	dta c'SIO2SD na SDC'
m_unum	dta c'?'
	dta c': fw '
m_fw1	dta c'?'
	dta c'.'
m_fw2	dta c'?',EOL
m_non	dta c'Zaden SIO2SD nie odpowiada',EOL
m_hs1	dta c'SIO turbo wlaczone',EOL
m_hs0	dta c'SIO turbo niedostepne - 19200',EOL
m_wrn	dta c'ID '
m_wid	dta c'?'
	dta c' nie odpowiada, instaluje',EOL
m_nof	dta c'Brak SIO2SD - nie zainstalowano',EOL
m_ins	dta c'SDC1:-SDC4: gotowe (ID 0-3)',EOL
m_ins1	dta c'SDC1: gotowe (SIO2SD ID '
m_iid	dta c'?'
	dta c')',EOL

; --- kopiuj dcnt bajtow dbnc -> (xadr) w banku wolajacego; przesun xadr ---
dcopy	lda xadr
	sta zpt
	lda xadr+1
	sta zpt+1
	lda K_MEMREIX
	jsr V_setme
	ldy #0
dcp1	cpy dcnt
	bcs dcp2
	lda dbnc,y
	sta (zpt),y
	iny
	bne dcp1
dcp2	jsr V_popme
	clc
	lda xadr
	adc dcnt
	sta xadr
	bcc dcp3
	inc xadr+1
dcp3	rts
dcnt	dta 0
dbnc	:23 dta 0

; ===========================================================================
; CZESC W PAMIECI ROZSZERZONEJ (blok 2, indeks \$02)
; ===========================================================================
	blk reloc ext

; --- dispatcher funkcji jadra: Y = kod, status w A ---

devdisp
	cpy #21
	bcs dm_ni
	tya
	asl @
	tax
	lda jtab,x
	sta zpt
	lda jtab+1,x
	sta zpt+1
	jmp (zpt)
dm_ni
	lda #ENOTIMP
	rts

jtab
	dta a(kdread)	; 0
	dta a(kdwrite)	; 1
	dta a(kdpos)	; 2
	dta a(kdgtpos)	; 3
	dta a(kdgtlen)	; 4
	dta a(kdni)	; 5  kd_status
	dta a(kdnext)	; 6
	dta a(kdclose)	; 7
	dta a(kdinitz)	; 8
	dta a(kdopen)	; 9
	dta a(kdfirst)	; 10
	dta a(kdren)	; 11
	dta a(kddel)	; 12
	dta a(kdni)	; 13 kd_setatr
	dta a(kdmkdir)	; 14
	dta a(kdrmdir)	; 15
	dta a(kdchdir)	; 16
	dta a(kdcwd)	; 17
	dta a(kdni)	; 18 kd_boot
	dta a(kdcheck)	; 19
	dta a(kdni)	; 20 kd_chvol
kdni
	lda #ENOTIMP
	rts

; --- stan globalny ---

cslot	dta 0		; biezacy slot (0-3)
kfid	dta 0		; przydzielony uchwyt jadra

fid2slot :16 dta $FF	; uchwyt jadra -> slot

; sloty (tablice rownolegle, indeks = slot)
skind	:4 dta 0	; 0=wolny 1=plik 2=katalog
sunit	:4 dta 0
smode	:4 dta 0
sscan	:4 dta 0
sfid	:4 dta 0
spos0	:4 dta 0
spos1	:4 dta 0
spos2	:4 dta 0
slen0	:4 dta 0
slen1	:4 dta 0
slen2	:4 dta 0
sidx0	:4 dta 0	; katalog: indeks dla kd_next
sidx1	:4 dta 0
scnt0	:4 dta 0	; katalog: liczba wpisow
scnt1	:4 dta 0
ssoff	:4 dta 0	; katalog: offset w biezacym wpisie strumienia
sscur0	:4 dta 0	; katalog: indeks wpisu strumienia (0=naglowek)
sscur1	:4 dta 0
srecalc	:4 dta 0	; 1 = przelicz sscur/ssoff z spos

; jednostki (indeks = unitix 0-3)
uctx	:4 dta 0	; slot+1, ktorego plik jest otwarty w urzadzeniu
ueown	:4 dta $FF	; 1 = kursor enumeracji wazny
ueidx0	:4 dta 0	; kursor: indeks nastepnego wpisu z $04-kontynuacja
ueidx1	:4 dta 0
udpos0	:4 dta 0	; pozycja I/O urzadzenia
udpos1	:4 dta 0
udpos2	:4 dta 0

; duze pola slotow i jednostek - przez tablice adresow
slfnp	dta a(slfn0),a(slfn1),a(slfn2),a(slfn3)
spathp	dta a(spath0),a(spath1),a(spath2),a(spath3)
smaskp	dta a(smask0),a(smask1),a(smask2),a(smask3)
ucwdp	dta a(ucwd0),a(ucwd1),a(ucwd2),a(ucwd3)
udevp	dta a(udev0),a(udev1),a(udev2),a(udev3)

; --- bufory robocze ---

e54	:54 dta 0	; wpis katalogu SIO2SD
stage23	:23 dta 0	; zsyntetyzowany wpis SpartaDOS
stgown	dta 0		; wlasciciel stage23 (slot+1), 0=brak
stgidx0	dta 0
stgidx1	dta 0
wpath	:65 dta 0	; efektywna sciezka robocza
wend	dta 0
woff	dta 0
poff	dta 0
tokb	:13 dta 0	; token sciezki / nazwy
f11	:11 dta 0	; wzorzec nazwy (format wewnetrzny)
m11	:11 dta 0	; zmapowana nazwa wpisu
t11	:11 dta 0	; nazwa robocza (tworzenie/rename)
a83	:14 dta 0	; nazwa ASCII "NNNNNNNN.XXX",0
objb	:54 dta 0	; bufor nazwy/obiektu dla komend SIO2SD
skb	dta 0,0,0
cnt2	dta 0,0
fcnt	dta 0,0
fidx	dta 0,0
fstart	dta 0,0
fscan	dta 0
mgidx	dta 0,0		; indeks do mapowania ~NNN ($FFFF = bez ~)
nlen	dta 0
dotp	dta 0
baslen	dta 0
extlen	dta 0
mangl	dta 0
hitcnt	dta 0
flen3	dta 0,0,0
rem0	dta 0
rem1	dta 0
rem2	dta 0
p3	dta 0,0,0
q3	dta 0,0,0
t16	dta 0,0
mstar	dta c'*'
	:15 dta 0
vlabel	dta c'SIO2SD  '

; slowa adresowe (relokowalne)
w_e54	dta a(e54)
w_objb	dta a(objb)
w_skb	dta a(skb)
w_cnt2	dta a(cnt2)
w_mstar	dta a(mstar)

; ===========================================================================
; WARSTWA SIO
; ===========================================================================

; ustaw DCB: A = komenda, Y = DSTATS

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


; status karty: A=1 ok / blad; status 2/4 uniewaznia udev i kursor

cardchk
	lda #$00
	ldy #$40
	jsr sdcb
	jsr buftmp1
	jsr gosio
	bmi cc_e
	lda tmpb
	beq cc_nc
	cmp #1
	beq cc_ok
	cmp #3
	beq cc_ok
	ldx curux
	lda #$FF
	sta ueown,x
	jsr invdev
cc_ok	lda #1
	rts
cc_nc	lda #ENOCARD
	rts
cc_e	ora #0
	rts

; udev[curux] := niewazny

invdev
	jsr setudevp
	ldy #0
	lda #$FF
	sta (zpt),y
	rts

; maska "*" typy 3

setmaskall
	lda #$09
	ldy #$80
	jsr sdcb
	lda #3
	sta DAUX1
	lda w_mstar
	sta DBUFLO
	lda w_mstar+1
	sta DBUFHI
	lda #16
	sta DBYTLO
	lda #0
	sta DBYTHI
	jmp gosio

; liczba wpisow -> cnt2

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

; nastepny wpis -> e54; A = aux2 (1 = od poczatku)

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

; otworz/utworz plik nazwa w objb; A = aux1 (1=utworz, 3=otworz)

fopen20
	pha
	lda #$20
	ldy #$80
	jsr sdcb
	pla
	sta DAUX1
	jsr bufobj39
	lda #ENFOUND
	sta xerr
	jmp gonak

; dlugosc pliku -> flen3

fgetlen
	lda #$26
	ldy #$40
	jsr sdcb
	jsr bufskb3
	jsr gosio
	bmi fg1
	lda skb
	sta flen3
	lda skb+1
	sta flen3+1
	lda skb+2
	sta flen3+2
	lda #1
fg1	ora #0
	rts

; ustaw dlugosc wg skb

fsetlen
	lda #$27
	ldy #$80
	jsr sdcb
	jsr bufskb3
	jmp gosio

; ustaw pozycje wg skb

dseek
	lda #$23
	ldy #$80
	jsr sdcb
	jsr bufskb3
	jmp gosio

; ===========================================================================
; WSKAZNIKI DO DUZYCH POL
; ===========================================================================

setucwdp
	lda curux
	asl @
	tay
	lda ucwdp,y
	sta zpt
	lda ucwdp+1,y
	sta zpt+1
	rts

setudevp
	lda curux
	asl @
	tay
	lda udevp,y
	sta zpt
	lda udevp+1,y
	sta zpt+1
	rts

setspathp
	lda cslot
	asl @
	tay
	lda spathp,y
	sta zpt
	lda spathp+1,y
	sta zpt+1
	rts

setslfnp
	lda cslot
	asl @
	tay
	lda slfnp,y
	sta zpt
	lda slfnp+1,y
	sta zpt+1
	rts

setsmaskp
	lda cslot
	asl @
	tay
	lda smaskp,y
	sta zpt
	lda smaskp+1,y
	sta zpt+1
	rts

; wpath -> spath slotu

savepath
	jsr setspathp
	ldy #0
sv_1	lda wpath,y
	sta (zpt),y
	beq sv_2
	iny
	cpy #64
	bcc sv_1
	lda #0
	sta (zpt),y
sv_2	rts

; spath slotu -> wpath

loadpath
	jsr setspathp
	ldy #0
lp_1	lda (zpt),y
	sta wpath,y
	beq lp_2
	iny
	cpy #64
	bcc lp_1
	lda #0
	sta wpath,y
lp_2	rts

; objb(39) -> lfn slotu

savelfn
	jsr setslfnp
	ldy #0
sl_1	lda objb,y
	sta (zpt),y
	iny
	cpy #39
	bcc sl_1
	lda #0
	sta (zpt),y
	rts

; lfn slotu -> objb(39, dopelnione zerami)

loadlfn
	jsr setslfnp
	ldy #0
ll_1	lda (zpt),y
	sta objb,y
	iny
	cpy #39
	bcc ll_1
	rts

; K_NAME -> maska slotu (pusta nazwa -> same '?')

namemask
	jsr setsmaskp
	lda K_NAME
	cmp #' '
	beq nm_all
	ldy #0
nm_1	lda K_NAME,y
	sta (zpt),y
	iny
	cpy #11
	bcc nm_1
	rts
nm_all	ldy #0
	lda #'?'
nm_2	sta (zpt),y
	iny
	cpy #11
	bcc nm_2
	rts

; maska slotu -> f11

loadmask
	jsr setsmaskp
	ldy #0
lm_1	lda (zpt),y
	sta f11,y
	iny
	cpy #11
	bcc lm_1
	rts

; ===========================================================================
; SCIEZKI
; ===========================================================================

; zbuduj efektywna sciezke w wpath z ucwd[curux] + K_PATH

effpath
	jsr setucwdp
	ldy #0
ef_c1	lda (zpt),y
	sta wpath,y
	beq ef_c2
	iny
	cpy #64
	bcc ef_c1
	lda #0
	sta wpath,y
ef_c2	sty wend
	ldx #0
	lda K_PATH
	cmp #'>'
	beq ef_abs
	cmp #'\'
	beq ef_abs
	jmp ef_lp
ef_abs
	lda #0
	sta wpath
	sta wend
	inx
ef_lp	lda K_PATH,x
	beq ef_done
	cmp #EOL
	beq ef_done
	cmp #'>'
	beq ef_sep
	cmp #'\'
	beq ef_sep
	cmp #'<'
	beq ef_up
	; token
	ldy #0
ef_t1	sta tokb,y
	inx
	iny
	cpy #12
	bcs ef_bad
	lda K_PATH,x
	beq ef_t2
	cmp #EOL
	beq ef_t2
	cmp #'>'
	beq ef_t2
	cmp #'\'
	beq ef_t2
	cmp #'<'
	beq ef_t2
	jmp ef_t1
ef_t2	lda #0
	sta tokb,y
	; ".." = w gore
	lda tokb
	cmp #'.'
	bne ef_app
	lda tokb+1
	cmp #'.'
	bne ef_app
	lda tokb+2
	beq ef_upt
ef_app	stx poff
	jsr appcomp
	bmi ef_bad2
	ldx poff
	jmp ef_lp
ef_sep	inx
	jmp ef_lp
ef_up	inx
ef_upt	jsr dropcomp
	jmp ef_lp
ef_done	lda #1
	rts
ef_bad	lda #EBADNAM
ef_bad2	ora #0
	rts

; dopisz token (tokb) do wpath

appcomp
	ldy wend
	beq ap_1
	lda #'>'
	sta wpath,y
	iny
ap_1	ldx #0
ap_2	lda tokb,x
	beq ap_3
	jsr upch
	cpy #64
	bcs ap_bad
	sta wpath,y
	inx
	iny
	bne ap_2
ap_3	sty wend
	lda #0
	sta wpath,y
	lda #1
	rts
ap_bad	lda #EBADNAM
	rts

; usun ostatni skladnik wpath

dropcomp
	ldy wend
	beq dc_2
dc_1	dey
	beq dc_2
	lda wpath,y
	cmp #'>'
	bne dc_1
dc_2	sty wend
	lda #0
	sta wpath,y
	rts

; ustaw katalog urzadzenia na wpath (z pamiecia stanu)

walkto
	jsr cardchk
	bpl wk_a1
	rts
wk_a1	; udev == wpath ?
	jsr setudevp
	ldy #0
wk_c1	lda (zpt),y
	cmp wpath,y
	bne wk_walk
	cmp #0
	beq wk_okj
	iny
	cpy #64
	bcc wk_c1
wk_okj	jmp wk_ok
wk_walk
	lda #$07	; katalog glowny
	ldy #$00
	jsr sdcb
	jsr gosio
	bpl wk_a2
	rts
wk_a2
	jsr invdev
	ldx curux
	lda #$FF
	sta ueown,x
	lda #0
	sta woff
wk_lp	ldx woff
	lda wpath,x
	beq wk_fin
	; zbierz token
	ldy #0
wk_t1	lda wpath,x
	beq wk_t2
	cmp #'>'
	beq wk_t3
	sta tokb,y
	inx
	iny
	cpy #12
	bcc wk_t1
	lda #EDIRNF
	rts
wk_t3	inx
wk_t2	stx woff
	lda #0
	sta tokb,y
	jsr tok2f11
	bmi wk_e
	lda #$08	; tylko katalogi
	sta fscan
	lda #0
	sta fstart
	sta fstart+1
	jsr findmap
	bmi wk_nf
	lda #$05	; wejdz do katalogu z e54
	ldy #$80
	jsr sdcb
	jsr bufe54
	lda #EDIRNF
	sta xerr
	jsr gonak
	bmi wk_e
	ldx curux
	lda #$FF
	sta ueown,x
	jmp wk_lp
wk_fin	; sukces: udev := wpath, skasuj flage zmian
	jsr setudevp
	ldy #0
wk_c2	lda wpath,y
	sta (zpt),y
	beq wk_f2
	iny
	cpy #64
	bcc wk_c2
	lda #0
	sta (zpt),y
wk_f2	; przeczytaj status, by skasowac flage "zmieniono katalog"
	lda #$00
	ldy #$40
	jsr sdcb
	jsr buftmp1
	jsr gosio
wk_ok	lda #1
	rts
wk_nf	cmp #ENFOUND
	bne wk_e
	lda #EDIRNF
wk_e	ora #0
	rts

; ===========================================================================
; NAZWY
; ===========================================================================

upch
	cmp #'a'
	bcc up_1
	cmp #'z'+1
	bcs up_1
	and #$DF
up_1	rts

; czy A jest poprawnym znakiem 8.3? C=1 tak, C=0 nie (A juz po upch)

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

; token ASCII (tokb) -> f11 (format wewnetrzny, '*' -> '?')

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
tf_err	lda #EBADNAM
	rts

; zmapuj nazwe z e54 na 8.3 -> m11; mgidx = indeks wpisu ($FFFF = bez ~)

map83
	; dlugosc nazwy (odetnij zera i spacje z prawej)
	ldx #39
mp_l1	dex
	bmi mp_l2
	lda e54,x
	beq mp_l1
	cmp #' '
	beq mp_l1
mp_l2	inx
	stx nlen
	; ostatnia kropka
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
	; wypelnij m11 spacjami
	ldx #10
	lda #' '
mp_f1	sta m11,x
	dex
	bpl mp_f1
	; skopiuj baze (do 8 znakow, czyszczac)
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
	; skopiuj rozszerzenie (do 3 znakow)
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
	; przeksztalcenie ~NNN?
	lda mangl
	bne mp_g1
	rts
mp_g1	lda mgidx
	and mgidx+1
	cmp #$FF
	bne mp_g2
	rts		; $FFFF: tylko obciecie (naglowek)
mp_g2
	; baza: 4 znaki (dopelnij '0') + '_' + 3 cyfry indeksu
	ldx #0
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
	; indeks mod 1000 -> t16
	lda mgidx
	sta t16
	lda mgidx+1
	sta t16+1
mp_m3	lda t16
	cmp #$E8	; 1000 = $03E8
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
mp_m4	; setki
	ldx #0
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
	; dziesiatki
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
mp_trunc
mp_ret	rts

; porownaj f11 (z '?') z m11; Z=1 zgodne

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

; filtr atrybutow: fscan vs typ wpisu (e54+39); Z=1 przechodzi

scanflt
	lda fscan
	and #$07	; +P/+H/+A: na karcie nic nie ma atrybutow
	bne sf_no
	lda fscan
	and #$08	; tylko katalogi
	beq sf_1
	lda e54+39
	cmp #1
	bne sf_no
sf_1	lda fscan
	and #$80	; bez katalogow
	beq sf_ok
	lda e54+39
	cmp #1
	beq sf_no
sf_ok	lda #0
	rts
sf_no	lda #1
	rts

; t11 (wewnetrzny) -> a83 ASCII "NNNNNNNN.XXX",0; blad gdy '?'

expand11
	ldx #0
	ldy #0
ex_1	cpy #8
	bcs ex_2
	lda t11,y
	cmp #' '
	beq ex_2
	cmp #'?'
	beq ex_bad
	sta a83,x
	inx
	iny
	bne ex_1
ex_2	; rozszerzenie?
	lda t11+8
	cmp #' '
	beq ex_9
	lda #'.'
	sta a83,x
	inx
	ldy #8
ex_3	cpy #11
	bcs ex_9
	lda t11,y
	cmp #' '
	beq ex_9
	cmp #'?'
	beq ex_bad
	sta a83,x
	inx
	iny
	bne ex_3
ex_9	lda #0
	sta a83,x
	cpx #0
	beq ex_bad
	lda #1
	rts
ex_bad	lda #EBADNAM
	rts

; a83 -> objb (39 bajtow, dopelnione zerami)

a83obj
	ldx #0
ao_1	lda a83,x
	sta objb,x
	beq ao_2
	inx
	cpx #39
	bcc ao_1
ao_2	lda #0
ao_3	cpx #39
	bcs ao_9
	sta objb,x
	inx
	bne ao_3
ao_9	rts

; e54[0..38] -> objb

e54obj
	ldx #0
eo_1	lda e54,x
	sta objb,x
	inx
	cpx #39
	bcc eo_1
	rts

; ===========================================================================
; ENUMERACJA KATALOGU
; ===========================================================================

; pobierz wpis nr fidx do e54 (kursor ueidx/ueown jednostki curux)

fetchent
	ldx curux
	lda ueown,x
	cmp #1
	bne fe_rs
	lda fidx
	cmp ueidx0,x
	lda fidx+1
	sbc ueidx1,x
	bcs fe_lp	; fidx >= ueidx: kontynuuj
fe_rs	jsr setmaskall
	bmi fe_er
	lda #1
	jsr getent
	bmi fe_er
	ldx curux
	lda #1
	sta ueown,x
	sta ueidx0,x
	lda #0
	sta ueidx1,x
fe_lp	ldx curux
	lda fidx
	cmp ueidx0,x
	lda fidx+1
	sbc ueidx1,x
	bcc fe_ok	; fidx < ueidx: e54 = wpis fidx
	lda #0
	jsr getent
	bmi fe_er
	ldx curux
	inc ueidx0,x
	bne fe_lp
	inc ueidx1,x
	jmp fe_lp
fe_ok	lda #1
	rts
fe_er	sta tmpb
	ldx curux
	lda #$FF
	sta ueown,x
	lda tmpb
	ora #0
	rts

; znajdz wpis pasujacy do f11+fscan od indeksu fstart
; wyjscie: A=1 (e54, fidx, m11) / A=ENFOUND / blad

findmap
	jsr setmaskall
	bmi fm_e
	jsr getcnt
	bmi fm_e
	lda cnt2
	sta fcnt
	lda cnt2+1
	sta fcnt+1
	lda fstart
	sta fidx
	lda fstart+1
	sta fidx+1
fm_lp	lda fidx
	cmp fcnt
	lda fidx+1
	sbc fcnt+1
	bcs fm_nf
	jsr fetchent
	bmi fm_e
	lda fidx
	sta mgidx
	lda fidx+1
	sta mgidx+1
	jsr map83
	jsr match11
	bne fm_nx
	jsr scanflt
	bne fm_nx
	lda #1
	rts
fm_nx	inc fidx
	bne fm_lp
	inc fidx+1
	jmp fm_lp
fm_nf	lda #ENFOUND
fm_e	ora #0
	rts

; ===========================================================================
; SYNTEZA WPISOW KATALOGU (format SpartaDOS, 23 bajty)
; ===========================================================================

; e54 + m11 -> stage23

build23
	lda #$08	; wpis w uzyciu
	ldx e54+39
	cpx #1
	bne bd_1
	lda #$28	; + podkatalog
bd_1	sta stage23
	lda e54+40	; "numer mapy" = klaster
	sta stage23+1
	lda e54+41
	sta stage23+2
	lda e54+44	; dlugosc (24 bity)
	sta stage23+3
	lda e54+45
	sta stage23+4
	lda e54+46
	sta stage23+5
	ldx #0
bd_2	lda m11,x
	sta stage23+6,x
	inx
	cpx #11
	bcc bd_2
	lda #0
	ldx #17
bd_3	sta stage23,x
	inx
	cpx #23
	bcc bd_3
	lda #0
	sta stgown	; zawartosc nie odpowiada strumieniowi
	lda #1
	rts

; naglowek katalogu slotu cslot -> stage23 (wpath = sciezka slotu)

mkhdr
	lda #$28
	sta stage23
	lda #1
	sta stage23+1
	lda #0
	sta stage23+2
	ldx cslot
	lda slen0,x
	sta stage23+3
	lda slen1,x
	sta stage23+4
	lda slen2,x
	sta stage23+5
	; nazwa: ostatni skladnik wpath lub etykieta wolumenu
	lda wpath
	bne mh_1
	; korzen
	ldx #0
mh_v1	lda vlabel,x
	sta stage23+6,x
	inx
	cpx #8
	bcc mh_v1
	lda #' '
	sta stage23+14
	sta stage23+15
	sta stage23+16
	jmp mh_9
mh_1	; znajdz poczatek ostatniego skladnika
	ldy wend
mh_2	dey
	beq mh_3
	lda wpath,y
	cmp #'>'
	bne mh_2
	iny
mh_3	; skopiuj do tokb
	ldx #0
mh_4	lda wpath,y
	beq mh_5
	sta tokb,x
	iny
	inx
	cpx #12
	bcc mh_4
mh_5	lda #0
	sta tokb,x
	jsr tok2f11
	ldx #0
mh_6	lda f11,x
	sta stage23+6,x
	inx
	cpx #11
	bcc mh_6
mh_9	lda #0
	ldx #17
mh_a	sta stage23,x
	inx
	cpx #23
	bcc mh_a
	lda #0
	sta stgown
	lda #1
	rts

; t16 * 23 -> p3

mul23
	lda t16
	sta p3
	sta q3
	lda t16+1
	sta p3+1
	sta q3+1
	lda #0
	sta p3+2
	sta q3+2
	jsr m23s	; q3 = 2x
	jsr m23a	; p3 = 3x
	jsr m23s	; q3 = 4x
	jsr m23a	; p3 = 7x
	jsr m23s	; 8x
	jsr m23s	; q3 = 16x
	jsr m23a	; p3 = 23x
	rts
m23s	asl q3
	rol q3+1
	rol q3+2
	rts
m23a	clc
	lda p3
	adc q3
	sta p3
	lda p3+1
	adc q3+1
	sta p3+1
	lda p3+2
	adc q3+2
	sta p3+2
	rts

; spos slotu / 23 -> sscur (iloraz), ssoff (reszta)

recalc23
	ldx cslot
	lda spos0,x
	sta p3
	lda spos1,x
	sta p3+1
	lda spos2,x
	sta p3+2
	lda #0
	sta t16
	sta t16+1
rc_lp	lda p3+1
	ora p3+2
	bne rc_sub
	lda p3
	cmp #23
	bcc rc_done
rc_sub	sec
	lda p3
	sbc #23
	sta p3
	lda p3+1
	sbc #0
	sta p3+1
	lda p3+2
	sbc #0
	sta p3+2
	inc t16
	bne rc_lp
	inc t16+1
	jmp rc_lp
rc_done	ldx cslot
	lda t16
	sta sscur0,x
	lda t16+1
	sta sscur1,x
	lda p3
	sta ssoff,x
	rts

; zapewnij stage23 = wpis strumienia sscur slotu cslot

ensstage
	ldx cslot
	lda cslot
	clc
	adc #1
	cmp stgown
	bne es_ld
	lda sscur0,x
	cmp stgidx0
	bne es_ld
	lda sscur1,x
	cmp stgidx1
	bne es_ld
	lda #1
	rts
es_ld	jsr loadpath
	jsr walkto
	bmi es_e
	ldx cslot
	lda sscur0,x
	ora sscur1,x
	bne es_ent
	jsr mkhdr
	jmp es_set
es_ent	sec
	lda sscur0,x
	sbc #1
	sta fidx
	sta mgidx
	lda sscur1,x
	sbc #0
	sta fidx+1
	sta mgidx+1
	jsr fetchent
	bmi es_e
	jsr map83
	jsr build23
es_set	ldx cslot
	lda cslot
	clc
	adc #1
	sta stgown
	lda sscur0,x
	sta stgidx0
	lda sscur1,x
	sta stgidx1
	lda #1
	rts
es_e	ora #0
	rts

; ===========================================================================
; KONTEKST PLIKU I TRANSFERY
; ===========================================================================

; zapewnij: plik slotu otwarty w urzadzeniu + pozycja urzadzenia = spos

ensfile
	ldx cslot
	lda sunit,x
	sta curux
	lda cslot
	clc
	adc #1
	sta zpx
	ldx curux
	lda uctx,x
	cmp zpx
	beq en_pos
	jsr loadpath
	jsr walkto
	bmi en_e
	jsr loadlfn
	lda #3
	jsr fopen20
	bmi en_e
	ldx curux
	lda zpx
	sta uctx,x
	lda #0
	sta udpos0,x
	sta udpos1,x
	sta udpos2,x
en_pos	; p3 = spos slotu
	ldx cslot
	lda spos0,x
	sta p3
	lda spos1,x
	sta p3+1
	lda spos2,x
	sta p3+2
	ldx curux
	lda udpos0,x
	cmp p3
	bne en_sk
	lda udpos1,x
	cmp p3+1
	bne en_sk
	lda udpos2,x
	cmp p3+2
	bne en_sk
	lda #1
	rts
en_sk	lda p3
	sta skb
	lda p3+1
	sta skb+1
	lda p3+2
	sta skb+2	
	jsr dseek
	bmi en_e
	ldx curux
	lda p3
	sta udpos0,x
	lda p3+1
	sta udpos1,x
	lda p3+2
	sta udpos2,x
	lda #1
	rts
en_e	ora #0
	rts

; status po odczycie: A=3 gdy pozycja == dlugosc (koniec danych), inaczej 1

endst
	ldx cslot
	lda spos0,x
	cmp slen0,x
	bne nd_1
	lda spos1,x
	cmp slen1,x
	bne nd_1
	lda spos2,x
	cmp slen2,x
	bne nd_1
	lda #3
	rts
nd_1	lda #1
	rts

; rem = slen-spos; xfer = min(K_BYTBUF, rem); A=0 gdy rem==0

calcxfer
	ldx cslot
	sec
	lda slen0,x
	sbc spos0,x
	sta rem0
	lda slen1,x
	sbc spos1,x
	sta rem1
	lda slen2,x
	sbc spos2,x
	sta rem2
	lda rem2
	bne cx_full
	lda rem0
	ora rem1
	bne cx_1
	lda #0
	sta xfer
	sta xfer+1
	rts
cx_1	lda rem0
	cmp K_BYTBUF
	lda rem1
	sbc K_BYTBUF+1
	bcs cx_full
	lda rem0
	sta xfer
	lda rem1
	sta xfer+1
	lda #1
	rts
cx_full	lda K_BYTBUF
	sta xfer
	lda K_BYTBUF+1
	sta xfer+1
	lda #1
	rts

; przeslij xfer bajtow K_ADDPOS <-> urzadzenie (xcmd/xdst)
; aktualizuje spos slotu i udpos jednostki


; ===========================================================================
; UCHWYTY
; ===========================================================================

; K_FID -> cslot + curux

getslot
	lda K_FID
	and #$0F
	tax
	lda fid2slot,x
	cmp #MAXH
	bcs gs_bad
	sta cslot
	tax
	lda skind,x
	beq gs_bad
	lda sunit,x
	sta curux
	lda #1
	rts
gs_bad	lda #ENOTOPEN
	rts

; przydziel uchwyt jadra + slot

allocslot
	ldy #0
as_f	lda dev_index,y
	cmp #$FF
	beq as_f2
	iny
	cpy #16
	bcc as_f
	lda #ETOOMANY
	rts
as_f2	sty kfid
	ldx #0
as_s	lda skind,x
	beq as_ok
	inx
	cpx nslots
	bcc as_s
	lda #ETOOMANY
	rts
as_ok	stx cslot
	lda kfid
	sta K_FID
	tax
	lda cslot
	sta fid2slot,x
	ldx cslot
	lda kfid
	sta sfid,x
	; uniewaznij stage, gdyby slot byl wczesniej uzywany
	lda cslot
	clc
	adc #1
	cmp stgown
	bne as_9
	lda #0
	sta stgown
as_9	lda #1
	rts

; ===========================================================================
; FUNKCJE JADRA
; ===========================================================================

kdinitz
	ldx #0
	lda #0
in_1	sta skind,x
	inx
	cpx #MAXH
	bcc in_1
	ldx #0
	lda #$FF
in_2	sta fid2slot,x
	inx
	cpx #16
	bcc in_2
	lda #0
	sta stgown
	ldx #0
in_3	lda #0
	sta uctx,x
	lda #$FF
	sta ueown,x
	stx curux
	txa
	pha
	jsr setucwdp
	lda #0
	ldy #0
	sta (zpt),y
	jsr setudevp
	lda #$FF
	sta (zpt),y
	pla
	tax
	inx
	cpx #4
	bcc in_3
	lda #0
	sta curux
	lda #1
	rts

; K_DEV -> curux

getunit
	lda K_DEV
	and #$0F
	beq gu_bad
	cmp #5
	bcs gu_bad
	sec
	sbc #1
	sta curux
	tax
	lda umap,x
	cmp #$FF
	beq gu_bad
	lda #1
	rts
gu_bad	lda #EBADUNIT
	rts

; --- kd_open (9) ---

kdopen
	jsr getunit
	bpl kdo_a1
	rts
kdo_a1	jsr effpath
	bpl kdo_a2
	rts
kdo_a2	jsr walkto
	bpl kdo_a3
	rts
kdo_a3	lda K_MODE
	and #$10
	bne kdo_a4
	jmp kdo_fil
kdo_a4
	; --- katalog ---
	lda K_MODE
	and #$0F
	cmp #4
	beq kdo_d1
	lda #ENOTIMP
	rts
kdo_d1	jsr setmaskall
	bpl kdo_a5
	rts
kdo_a5	jsr getcnt
	bpl kdo_a6
	rts
kdo_a6	jsr allocslot
	bpl kdo_a7
	rts
kdo_a7
	ldx cslot
	lda cnt2
	sta scnt0,x
	lda cnt2+1
	sta scnt1,x
	; slen = (cnt+1)*23
	clc
	lda cnt2
	adc #1
	sta t16
	lda cnt2+1
	adc #0
	sta t16+1
	jsr mul23
	ldx cslot
	lda p3
	sta slen0,x
	lda p3+1
	sta slen1,x
	lda p3+2
	sta slen2,x
	lda #2
	sta skind,x
	lda curux
	sta sunit,x
	lda K_MODE
	sta smode,x
	lda K_SCAN
	sta sscan,x
	lda #23
	sta spos0,x
	lda #0
	sta spos1,x
	sta spos2,x
	sta sidx0,x
	sta sidx1,x
	lda #1
	sta srecalc,x
	jsr namemask
	jsr savepath
	jsr mkhdr
	; naglowek -> K_DENTRY
	ldx #22
kdo_d2	lda stage23,x
	sta K_DENTRY,x
	dex
	bpl kdo_d2
	lda #1
	rts
kdo_r	ora #0
	rts
kdo_fil
	lda K_MODE
	and #$0F
	cmp #4
	beq kdo_f1
	cmp #8
	beq kdo_f1
	cmp #9
	beq kdo_f1
	cmp #12
	beq kdo_f1
	lda #ENOTIMP
	rts
kdo_f1	ldx #10
kdo_c	lda K_NAME,x
	sta f11,x
	dex
	bpl kdo_c
	lda K_SCAN
	sta fscan
	lda #0
	sta fstart
	sta fstart+1
	jsr findmap
	bpl kdo_have
	cmp #ENFOUND
	beq kdo_nf
	rts		; blad SIO
kdo_nf	lda K_MODE
	and #$0F
	cmp #4
	bne kdo_cr
	lda #ENFOUND
	rts
kdo_cr	; utworz nowy plik
	ldx #10
kdo_c2	lda K_NAME,x
	sta t11,x
	dex
	bpl kdo_c2
	jsr expand11
	bpl kdo_a8
	rts
kdo_a8	jsr a83obj
	lda #1
	jsr fopen20
	bpl kdo_a9
	rts
kdo_a9
	ldx curux
	lda #$FF
	sta ueown,x
	lda #0
	sta flen3
	sta flen3+1
	sta flen3+2
	jmp kdo_new
kdo_have
	jsr e54obj
	lda #3
	jsr fopen20
	bpl kdo_aa
	rts
kdo_aa	jsr fgetlen
	bpl kdo_ab
	rts
kdo_ab
	lda K_MODE
	and #$0F
	cmp #8
	bne kdo_new
	lda #0
	sta skb
	sta skb+1
	sta skb+2
	jsr fsetlen
	bpl kdo_ac
	rts
kdo_ac	lda #0
	sta flen3
	sta flen3+1
	sta flen3+2
kdo_new
	jsr allocslot
	bpl kdo_ad
	rts
kdo_ad
	ldx cslot
	lda #1
	sta skind,x
	lda curux
	sta sunit,x
	lda K_MODE
	sta smode,x
	lda flen3
	sta slen0,x
	lda flen3+1
	sta slen1,x
	lda flen3+2
	sta slen2,x
	; pozycja: tryb 9 od konca, inaczej 0
	lda K_MODE
	and #$0F
	cmp #9
	beq kdo_ap
	lda #0
	sta spos0,x
	sta spos1,x
	sta spos2,x
	beq kdo_p2
kdo_ap	lda flen3
	sta spos0,x
	lda flen3+1
	sta spos1,x
	lda flen3+2
	sta spos2,x
kdo_p2	jsr savelfn
	jsr savepath
	ldx curux
	lda cslot
	clc
	adc #1
	sta uctx,x
	lda #0
	sta udpos0,x
	sta udpos1,x
	sta udpos2,x
	lda #1
	rts

; --- kd_read (0) ---

kdread
	jsr getslot
	bmi kr_r
	ldx cslot
	lda skind,x
	cmp #1
	beq kr_fil
	jmp drread
kr_fil	lda smode,x
	and #$0F
	cmp #8
	beq kr_wo
	cmp #9
	beq kr_wo
	jsr calcxfer
	bne kr_1
	lda #0
	sta K_BYTBUF
	sta K_BYTBUF+1
	lda #EEOF
	rts
kr_1	lda xfer
	ora xfer+1
	bne kr_2
	lda #1
	rts
kr_2	jsr ensfile
	bmi kr_r
	lda #$24
	sta xcmd
	lda #$40
	sta xdst
	jsr xferloop
	bmi kr_r
	lda xfer
	sta K_BYTBUF
	lda xfer+1
	sta K_BYTBUF+1
	jmp endst
kr_wo	lda #EWRONLY
	rts
kr_r	ora #0
	rts

; --- kd_write (1) ---

kdwrite
	jsr getslot
	bpl kw_a0
	rts
kw_a0	ldx cslot
	lda skind,x
	cmp #1
	beq kw_1
	lda #ENOTIMP
	rts
kw_1	lda smode,x
	and #$0F
	cmp #4
	bne kw_2
	lda #ERDONLY
	rts
kw_2	lda K_BYTBUF
	sta xfer
	lda K_BYTBUF+1
	sta xfer+1
	ora K_BYTBUF
	bne kw_3
	lda #1
	rts
kw_3	jsr ensfile
	bpl kw_a1
	rts
kw_a1
	; endp (p3) = spos + xfer
	ldx cslot
	clc
	lda spos0,x
	adc xfer
	sta p3
	lda spos1,x
	adc xfer+1
	sta p3+1
	lda spos2,x
	adc #0
	sta p3+2
	; endp > slen ?
	sec
	lda slen0,x
	sbc p3
	lda slen1,x
	sbc p3+1
	lda slen2,x
	sbc p3+2
	bcs kw_4
	; przedluz plik
	lda p3
	sta skb
	lda p3+1
	sta skb+1
	lda p3+2
	sta skb+2
	jsr fsetlen
	bpl kw_a2
	rts
kw_a2	ldx cslot
	lda p3
	sta slen0,x
	lda p3+1
	sta slen1,x
	lda p3+2
	sta slen2,x
kw_4	lda #$25
	sta xcmd
	lda #$80
	sta xdst
	jsr xferloop
	bmi kw_r
	lda xfer
	sta K_BYTBUF
	lda xfer+1
	sta K_BYTBUF+1
	lda #1
	rts
kw_r	ora #0
	rts

; --- odczyt strumienia katalogu ---

drread
	ldx cslot
	lda smode,x
	and #$0F
	cmp #4
	beq dr_0
	lda #EWRONLY
	rts
dr_0	jsr calcxfer
	bne dr_1
	lda #0
	sta K_BYTBUF
	sta K_BYTBUF+1
	lda #EEOF
	rts
dr_1	lda xfer
	ora xfer+1
	bne dr_2
	lda #1
	rts
dr_2	ldx cslot
	lda srecalc,x
	beq dr_3
	jsr recalc23
	ldx cslot
	lda #0
	sta srecalc,x
dr_3	lda K_ADDPOS
	sta xadr
	lda K_ADDPOS+1
	sta xadr+1
	lda xfer
	sta xrem
	lda xfer+1
	sta xrem+1
; petla po wpisach: przygotuj wpis (bank EXTRAM), skopiuj do wolajacego (dcopy)
dr_lp	lda xrem
	ora xrem+1
	bne dr_4
	jmp dr_fin
dr_4	jsr ensstage		; bank EXTRAM: dozwolone SIO i dostep do stage23
	bpl dr_a1
	rts			; blad ensstage (A<0), bank nietkniety
dr_a1	ldx cslot
	lda #23
	sec
	sbc ssoff,x		; A = 23 - ssoff (1..23), bajty do konca wpisu
	ldy xrem+1
	bne dr_r1		; xrem >= 256 -> run = A
	cmp xrem
	bcc dr_r1
	lda xrem		; xrem < A -> run = xrem
dr_r1	sta dcnt
	ldy ssoff,x		; stage23[ssoff..] -> dbnc (bank EXTRAM)
	ldx #0
dr_c1	lda stage23,y
	sta dbnc,x
	iny
	inx
	cpx dcnt
	bcc dr_c1
	ldx cslot		; ssoff += dcnt; przy 23 -> nastepny wpis
	lda ssoff,x
	clc
	adc dcnt
	cmp #23
	bcc dr_s1
	lda #0
	sta ssoff,x
	inc sscur0,x
	bne dr_s2
	inc sscur1,x
	jmp dr_s2
dr_s1	sta ssoff,x
dr_s2	sec			; xrem -= dcnt
	lda xrem
	sbc dcnt
	sta xrem
	bcs dr_s3
	dec xrem+1
dr_s3	jsr dcopy		; dbnc -> wolajacy (przelacza bank wewnatrz)
	jmp dr_lp
dr_fin	ldx cslot
	clc
	lda spos0,x
	adc xfer
	sta spos0,x
	lda spos1,x
	adc xfer+1
	sta spos1,x
	lda spos2,x
	adc #0
	sta spos2,x
	lda xfer
	sta K_BYTBUF
	lda xfer+1
	sta K_BYTBUF+1
	jmp endst

; --- kd_pos (2) ---

kdpos
	jsr getslot
	bmi kp_r
	ldx cslot
	lda smode,x
	and #$0F
	cmp #4
	bne kp_set
	; tryb odczytu: pozycja <= dlugosc
	sec
	lda slen0,x
	sbc K_ADDPOS
	lda slen1,x
	sbc K_ADDPOS+1
	lda slen2,x
	sbc K_ADDPOS+2
	bcs kp_set
	lda #ERANGE
	rts
kp_set	lda K_ADDPOS
	sta spos0,x
	lda K_ADDPOS+1
	sta spos1,x
	lda K_ADDPOS+2
	sta spos2,x
	lda skind,x
	cmp #2
	bne kp_ok
	lda #1
	sta srecalc,x
kp_ok	lda #1
	rts
kp_r	ora #0
	rts

; --- kd_gtpos (3) / kd_gtlen (4) ---

kdgtpos
	jsr getslot
	bmi kg_r
	ldx cslot
	lda spos0,x
	sta K_ADDPOS
	lda spos1,x
	sta K_ADDPOS+1
	lda spos2,x
	sta K_ADDPOS+2
	lda #1
	rts
kg_r	ora #0
	rts

kdgtlen
	jsr getslot
	bmi kg_r
	ldx cslot
	lda slen0,x
	sta K_ADDPOS
	lda slen1,x
	sta K_ADDPOS+1
	lda slen2,x
	sta K_ADDPOS+2
	lda #1
	rts

; --- kd_close (7) ---

kdclose
	jsr getslot
	bmi kc_ok	; tolerancyjnie
	ldx cslot
	lda #0
	sta skind,x
	lda sfid,x
	tax
	lda #$FF
	sta fid2slot,x
	; kontekst pliku
	lda cslot
	clc
	adc #1
	sta zpx
	ldx curux
	lda uctx,x
	cmp zpx
	bne kc_1
	lda #0
	sta uctx,x
kc_1	; stage
	lda stgown
	cmp zpx
	bne kc_ok
	lda #0
	sta stgown
kc_ok	lda #1
	rts

; --- kd_next (6) ---

kdnext
	jsr getslot
	bmi kn_r
	ldx cslot
	lda skind,x
	cmp #2
	beq kn_0
	lda #ENOTOPEN
	rts
kn_0	jsr loadpath
	jsr walkto
	bmi kn_r
kn_lp	ldx cslot
	lda sidx0,x
	cmp scnt0,x
	lda sidx1,x
	sbc scnt1,x
	bcs kn_end
	lda sidx0,x
	sta fidx
	sta mgidx
	lda sidx1,x
	sta fidx+1
	sta mgidx+1
	inc sidx0,x
	bne kn_2
	inc sidx1,x
kn_2	jsr fetchent
	bmi kn_r
	jsr map83
	jsr loadmask
	jsr match11
	bne kn_lp
	ldx cslot
	lda sscan,x
	sta fscan
	jsr scanflt
	bne kn_lp
	jsr build23
	ldx #22
kn_c	lda stage23,x
	sta K_DENTRY,x
	dex
	bpl kn_c
	lda #1
	rts
kn_end	lda #EEOF
kn_r	ora #0
	rts

; --- kd_first (10) ---

kdfirst
	lda #$14
	sta K_MODE
	jsr kdopen
	bpl kf_1
	rts
kf_1	jsr kdnext
	bpl kf_9
	cmp #EEOF
	bne kf_9
	lda #ENFOUND	; pusty wynik FFIRST = "nie znaleziono"
kf_9	ora #0
	rts

; --- kd_rename (11) ---

kdren
	jsr getunit
	bpl rn_a1
	rts
rn_a1	jsr effpath
	bpl rn_a2
	rts
rn_a2	jsr walkto
	bpl rn_a3
	rts
rn_a3
	lda #0
	sta hitcnt
	sta fstart
	sta fstart+1
rn_lp	ldx #10
rn_c	lda K_NAME,x
	sta f11,x
	dex
	bpl rn_c
	lda K_SCAN
	sta fscan
	jsr findmap
	bmi rn_done
	; nowa nazwa: x_name z '?' uzupelnianym z m11
	ldx #10
rn_m	lda K_XNAME,x
	cmp #'?'
	bne rn_m1
	lda m11,x
rn_m1	sta t11,x
	dex
	bpl rn_m
	jsr expand11
	bmi rn_r
	jsr a83obj
	ldx #39
rn_o	lda e54,x
	sta objb,x
	inx
	cpx #54
	bcc rn_o
	lda #$0D
	ldy #$80
	jsr sdcb
	jsr bufobj54
	lda #EPERM
	sta xerr
	jsr gonak
	bmi rn_r
	inc hitcnt
	ldx curux
	lda #$FF
	sta ueown,x
	clc
	lda fidx
	adc #1
	sta fstart
	lda fidx+1
	adc #0
	sta fstart+1
	jmp rn_lp
rn_done	cmp #ENFOUND
	bne rn_r
	lda hitcnt
	beq rn_nf
	lda #1
	rts
rn_nf	lda #ENFOUND
rn_r	ora #0
	rts

; --- kd_delete (12) ---

kddel
	jsr getunit
	bmi dl_r
	jsr effpath
	bmi dl_r
	jsr walkto
	bmi dl_r
	lda #0
	sta hitcnt
dl_lp	ldx #10
dl_c	lda K_NAME,x
	sta f11,x
	dex
	bpl dl_c
	lda K_SCAN
	sta fscan
	lda #0
	sta fstart
	sta fstart+1
	jsr findmap
	bmi dl_done
	lda e54+39
	cmp #1
	beq dl_skip	; katalogow nie kasujemy przez DELETE
	lda #$0C
	ldy #$80
	jsr sdcb
	jsr bufe54
	lda #EPERM
	sta xerr
	jsr gonak
	bmi dl_r
	inc hitcnt
	ldx curux
	lda #$FF
	sta ueown,x
	jmp dl_lp
dl_skip	; pomin katalog: szukaj od nastepnego... (fstart stale 0, wiec
	; uzyj petli z fstart)
	clc
	lda fidx
	adc #1
	sta fstart
	lda fidx+1
	adc #0
	sta fstart+1
	jmp dl_lp2
dl_done	cmp #ENFOUND
	bne dl_r
	lda hitcnt
	beq dl_nf
	lda #1
	rts
dl_nf	lda #ENFOUND
dl_r	ora #0
	rts
dl_lp2	ldx #10
dl_c2	lda K_NAME,x
	sta f11,x
	dex
	bpl dl_c2
	lda K_SCAN
	sta fscan
	jsr findmap
	bmi dl_done
	lda e54+39
	cmp #1
	beq dl_skip
	lda #$0C
	ldy #$80
	jsr sdcb
	jsr bufe54
	lda #EPERM
	sta xerr
	jsr gonak
	bmi dl_r
	inc hitcnt
	ldx curux
	lda #$FF
	sta ueown,x
	jmp dl_lp

; --- kd_credir (14) ---

kdmkdir
	jsr getunit
	bmi mk_r
	jsr effpath
	bmi mk_r
	jsr walkto
	bmi mk_r
	ldx #10
mk_c	lda K_NAME,x
	sta f11,x
	sta t11,x
	dex
	bpl mk_c
	jsr expand11
	bmi mk_r
	; istnieje juz?
	lda #0
	sta fscan
	sta fstart
	sta fstart+1
	jsr findmap
	bmi mk_1
	lda #EEXIST
	rts
mk_1	cmp #ENFOUND
	bne mk_r
	jsr a83obj
	lda #$0B
	ldy #$80
	jsr sdcb
	lda #1
	sta DAUX1
	jsr bufobj39
	lda #EEXIST
	sta xerr
	jsr gonak
	bmi mk_r
	ldx curux
	lda #$FF
	sta ueown,x
	lda #1
	rts
mk_r	ora #0
	rts

; --- kd_deldir (15) ---

kdrmdir
	jsr getunit
	bmi rm_r
	jsr effpath
	bmi rm_r
	jsr walkto
	bmi rm_r
	ldx #10
rm_c	lda K_NAME,x
	sta f11,x
	dex
	bpl rm_c
	lda #$08	; tylko katalogi
	sta fscan
	lda #0
	sta fstart
	sta fstart+1
	jsr findmap
	bmi rm_nf
	lda #$0C
	ldy #$80
	jsr sdcb
	jsr bufe54
	lda #EPERM	; zapewne niepusty
	sta xerr
	jsr gonak
	bmi rm_r
	ldx curux
	lda #$FF
	sta ueown,x
	lda #1
	rts
rm_nf	cmp #ENFOUND
	bne rm_r
	lda #EDIRNF
rm_r	ora #0
	rts

; --- kd_chdir (16) ---

kdchdir
	jsr getunit
	bmi cd_r
	jsr effpath
	bmi cd_r
	jsr walkto
	bmi cd_r
	jsr setucwdp
	ldy #0
cd_1	lda wpath,y
	sta (zpt),y
	beq cd_2
	iny
	cpy #64
	bcc cd_1
	lda #0
	sta (zpt),y
cd_2	lda #1
	rts
cd_r	ora #0
	rts

; --- kd_cwd (17) ---

kdcwd
	jsr getunit
	bmi cw_r
	jsr setucwdp
	ldy #0
cw_1	lda (zpt),y
	sta K_PATH,y
	beq cw_2
	iny
	cpy #64
	bcc cw_1
	lda #0
	sta K_PATH,y
cw_2	lda #1
	rts
cw_r	ora #0
	rts

; --- kd_check (19) ---

; format odpowiedzi jadra 4.4x (wg implementacji PCLink):
; [0]=$21 wersja formatu, [1-2] wsk. katalogu gl., [3-4] sektory ogolem,
; [5-6] wolne sektory, [7] dl. bitmapy, [8-13] rozne wskazniki,
; [14-21] etykieta woluminu, [22] sciezki, [23] kod B/sektor,
; [24] numer wersji, [25-26] rzeczywiste B/sektor, [29] sekt./klaster

kdcheck
	jsr getunit
	bmi ck_r
	jsr cardchk
	bmi ck_r
	ldx #63
	lda #0
ck_0	sta K_PATH,x
	dex
	bpl ck_0
	lda #$21	; wersja formatu danych
	sta K_PATH
	lda #$FF	; sektory: ogolem i wolne = 65535
	sta K_PATH+3
	sta K_PATH+4
	sta K_PATH+5
	sta K_PATH+6
	ldx #0
ck_1	lda vlabel,x
	sta K_PATH+14,x
	inx
	cpx #8
	bcc ck_1
	lda #$01
	sta K_PATH+23	; kod rozmiaru sektora
	sta K_PATH+29	; sektory na klaster
	lda #$80
	sta K_PATH+24	; numer wersji
	lda #$02
	sta K_PATH+26	; rzeczywisty rozmiar sektora = $0200
	lda #1
	rts
ck_r	ora #0
	rts

; ===========================================================================
; DUZE BUFORY SLOTOW I JEDNOSTEK
; ===========================================================================

; slot 0 oraz bufory jednostek (ucwd/udev) - zawsze rezydentne
slfn0	:40 dta 0
spath0	:65 dta 0
smask0	:11 dta 0
ucwd0	:65 dta 0
ucwd1	:65 dta 0
ucwd2	:65 dta 0
ucwd3	:65 dta 0
udev0	:65 dta 0
udev1	:65 dta 0
udev2	:65 dta 0
udev3	:65 dta 0

; --- komunikaty instalatora (w bloku rezydentnym z braku miejsca
; na stronach 4-6; mechanizm INSTALL i tak trzyma caly blok) ---


; ===========================================================================
; BUFORY SLOTOW 1..MAXH-1 (bufory nazw/sciezek/masek nadmiarowych slotow)
; ===========================================================================

slfn1	:40 dta 0
spath1	:65 dta 0
smask1	:11 dta 0
slfn2	:40 dta 0
spath2	:65 dta 0
smask2	:11 dta 0
slfn3	:40 dta 0
spath3	:65 dta 0
smask3	:11 dta 0

	blk update address
	blk update symbols
	end
