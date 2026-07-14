# Sterowniki SpartaDOS X dla SIO2SD (karta SD)

Dwa sterowniki dajace SpartaDOS X dostep do **plikow na karcie SD**
urzadzenia SIO2SD (obok normalnego montowania ATR-ow). Oba rozmawiaja
z SIO2SD jego natywnym API na szynie SIO (komendy $00-$27, patrz
http://www.sio2sd.org/commands/).

**Wymagane firmware SIO2SD 3.x** (dopiero ono ma komendy plikowe $20-$27).

> **Adres SIO urzadzenia.** Dokumentacja sio2sd.org podaje `$73 + ID`
> (ID 0 -> `$73`). Na testowanym sprzecie (fw 3.3) urzadzenie o ID 0
> odpowiada jednak na `$72`, a nie `$73` - dlatego oba sterowniki oraz
> emulacja Altirry uzywaja bazy `$72 + ID` (stala `SIOBASE` w zrodlach
> `SDCDEV.ASM`/`SIO2SD.ASM`). Jesli Twoje urzadzenie jest zgodne ze
> specyfikacja ($73), ustaw `SIOBASE = $72` z powrotem na `$73` w obu
> plikach i przebuduj (oraz `0x72`->`0x73` w `altirra/sio2sd_server.py`
> i `$72`->`$73` w `altirra/sio2sd.atdevice`, jesli korzystasz z emulacji).

| Sterownik | Typ | Co daje |
|---|---|---|
| **SDCDEV.SYS** (zalecany) | natywne urzadzenie plikowe jadra SDX | `SDC1:`-`SDC4:` z pelna obsluga `DIR`, `CD`, `MKDIR`, `RMDIR`, `COPY`, `REN`, `DEL`, sciezek i wildcardow; wiele otwartych plikow naraz |
| **SIO2SD.SYS** | klasyczny handler CIO (HATABS) | urzadzenie `F:` dla COPY/TYPE/BASIC; dziala tez poza jadrem SDX; **nie** obsluguje `DIR`/`CD` z CLI |

## SDCDEV.SYS - urzadzenie SDC: (SpartaDOS X 4.40+)

Instalacja (z linii polecen lub AUTOEXEC.BAT):

    D1:>SDCDEV [/0../3 | /F] [/M<n>] [/H]

Tryby instalacji:

* bez opcji - jednostki `SDC1:`-`SDC4:` = SIO2SD o ID 0-3; skan
  wykrywa i wypisuje obecne urzadzenia (informacyjnie),
* `/0`..`/3` - sprawdz tylko wskazane ID i zamapuj je na `SDC1:`
  (jednostki 2-4 wylaczone, blad 160); instaluje takze, gdy
  urzadzenie chwilowo nie odpowiada,
* `/F` - przeskanuj ID 0-3 i zamapuj **pierwsze znalezione** na
  `SDC1:`; gdy zadne nie odpowiada, sterownik nie instaluje sie wcale.

Dodatkowo `/M<n>` (n=1..4) ustawia maksymalna liczbe **rownoczesnie
otwartych plikow/katalogow**; domyslnie **2**. To ograniczenie
funkcjonalne (nie zmienia zajetosci pamieci). Domyslne **2** to minimum,
ktorego SDX potrzebuje na `COPY` w obrebie jednego `SDC:` (1. uchwyt na
katalog, 2. na plik zrodlowy). `/M1` oszczedza jeden slot, ale wtedy taki
`COPY` sie nie powiedzie. Opcje mozna laczyc, np. `SDCDEV /F /M3`.

Opcja `/H` probuje **wysokiej predkosci SIO (turbo)** zamiast standardowych
19200 bodow. Sterownik odpytuje SIO2SD o indeks predkosci komenda `$1E`
z ustawionym bitem `$80` (`$9E`), a potem robi samotest statusem `$00|$80`.
Jesli BIOS/handler SIO i urzadzenie obsluza taki tryb, kolejne komendy
SIO2SD dostaja bit `$80`; jesli nie, sterownik automatycznie wraca do 19200.
Domyslnie wylaczone. Duzy zysk jest na masowym odczycie/zapisie plikow; przy
drobnych komendach katalogowych dominuje narzut protokolu.

Od wersji 2.4 sterownik jest **podzielony na dwa bloki**: rdzen (~670 B:
trampolina wejscia, warstwa SIO i petle transferu) zostaje w pamieci
glownej ponizej $4000, a reszta (~6,5 KB: logika, parsowanie, bufory)
laduje sie do **pamieci rozszerzonej programu** (indeks $04, banki
PORTB/Axlon $4000-$7FFF). W pamieci podstawowej zostaje wiec tylko
~0,7 KB zamiast ~7 KB. Uwaga: blok zajmuje caly bank rozszerzenia (16 KB),
wiec kosztem jest jeden bank z (zwykle licznej) puli programu - to
oplacalny handel, bo odzyskujemy deficytowa pamiec glowna. Wymaga SDX
4.47+ z pamiecia rozszerzona programu (`USE BANKED`, sprzet PORTB/Axlon);
gdy jej brak, blok wpada z powrotem do pamieci glownej (bez oszczednosci -
sprawdz `MEM /X`: `Main` memlo powinno urosnac tylko o ~0,7 KB, a liczba
wolnych bankow zmalec o 1). Potem wszystko dziala jak na zwyklym dysku:

    SDC1:
    DIR
    CD GRY>RPG
    COPY SDC1:GAME.XEX D1:
    COPY D1:*.DAT SDC1:
    MKDIR NOWY
    DEL *.TMP
    REN STARA.TXT NOWA.TXT
    X SDC1:PROGRAM.XEX

### Nazwy plikow (LFN -> 8.3)

Jadro SDX operuje nazwami 8.3, a karta moze miec nazwy do 39 znakow.
Nazwy niemieszczace sie w 8.3 (za dlugie, ze spacja, z wieloma
kropkami itd.) sa pokazywane jako `NNNN_III.EXT`, gdzie `III` to
pozycja wpisu w katalogu (np. `Very Long File Name 2024.atr` ->
`VERY_001.ATR`). Takich nazw mozna normalnie uzywac we wszystkich
polecen (COPY, X, ...). Uwaga: po skasowaniu/zmianie nazw wpisow
numeracja `_III` moze sie przesunac (to nazwy syntetyczne, nie sa
zapisywane na karcie).

Tworzone pliki dostaja nazwy 8.3. Porownywanie nazw bez rozrozniania
wielkosci liter. `DIR` nie pokazuje dat (API SIO2SD ich nie udostepnia),
a wolne miejsce raportowane jest jako 65535 sektorow (brak zapytania
o wolne miejsce w API); etykieta woluminu to "SIO2SD".

Uwaga: SDX wyswietla jednostki urzadzen o 3-literowych nazwach jako
litery - `SDCA:` = `SDC1:` (ID 0), `SDCB:` = `SDC2:` ... `SDCD:` =
`SDC4:` (ID 3). Obie formy dzialaja w komendach.

### Wspolpraca z panelem SIO2SD

Katalog biezacy urzadzenia jest wspolny z fizycznym panelem SIO2SD.
Sterownik pilnuje wlasnej sciezki (na kazda jednostke) i po kazdej
zmianie z panelu sam przestawia katalog z powrotem (wykrywa to po
statusie urzadzenia), ale **nie nawiguj panelem w trakcie operacji
dyskowych** - pojedyncza operacja moze sie wtedy nie udac.

### Ograniczenia

* pozycja/dlugosc pliku 24-bitowa -> pliki do 16 MB,
* domyslnie 2 otwarte pliki/katalogi naraz na SDC: (opcja `/M<n>`, 1-4;
  jadro SDX i tak ogranicza liczbe uchwytow globalnie do 16),
* atrybuty (+P/+H/+A), daty i etykiety woluminu - nieobslugiwane
  (API SIO2SD ich nie ma); CHMOD/BOOT/CHVOL zwracaja blad 146,
* sterownik dzieli sie na rdzen w pamieci glownej (<$4000) i czesc
  w pamieci rozszerzonej programu (indeks 4); rdzen transferu musi lezec
  ponizej $4000 - ladujcie sterownik wczesnie w AUTOEXEC.BAT. Bez pamieci
  rozszerzonej programu loader umiesci blok w pamieci glownej (fallback,
  bez oszczednosci).

## SDMOUNT.COM - montowanie obrazow pod D1:-D15:

Narzedzie SDX do podpinania plikow z karty jako napedow (API $01-$03):

    SDMOUNT                    lista zamontowanych napedow
    SDMOUNT D2: GRA.ATR        zamontuj plik z biezacego katalogu karty
    SDMOUNT D2: GRY>GRA.ATR    zamontuj plik ze sciezki na karcie
    SDMOUNT D2: /E             podepnij pusty dysk
    SDMOUNT D2: /D             odlacz naped
    SDMOUNT /1 D2: GRA.ATR     uzyj SIO2SD o ID 1

Nazwy plikow podaje sie tak, jak pokazuje `DIR` na `SDC:` (lacznie
z nazwami `NNNN_III.EXT`). Mozna podac sama nazwe z biezacego katalogu
karty albo sciezke z separatorami `>`, `\` lub `/`; sciezka zaczeta od
`>`/`\`/`/` jest liczona od korzenia karty. Zwykla nazwa pliku idzie ta
sama droga co w starszym SDMOUNT; dodatkowe komendy katalogowe sa uzywane
tylko wtedy, gdy podasz sciezke. Na prawdziwym SIO2SD zmiana dziala
natychmiast (to natywna funkcja firmware); w Altirze naped emuluje
sio2sd_server.py (patrz nizej).

## SIO2SD.SYS - handler CIO (F:)

Prostsza alternatywa; szczegoly i XIO w komentarzu naglowka
`SIO2SD.ASM`. Instalacja: `SIO2SD [litera] [/0../3]`. Uzycie przez
`COPY F:PLIK D1:`, `TYPE F:PLIK`, `OPEN #1,6,0,"F:*.ATR"` (listing),
XIO 32/33/37/38/39/42/43/44/48 (rename/delete/point/note/dlugosc/
mkdir/rmdir/chdir/getcwd). Uchwyt tylko jeden naraz. `Y:` jako biezacy
naped i `DIR Y:` **nie** zadzialaja - to ograniczenie architektury CIO,
od tego jest SDCDEV.SYS.

## Pliki

| Plik | Opis |
|---|---|
| `SDCDEV.ASM` / `SDCDEV.SYS` | sterownik jadra SDX (zrodlo MADS / binarka) |
| `SIO2SD.ASM` / `SIO2SD.SYS` | handler CIO (zrodlo MADS / binarka) |
| `tools/sdxasm.py` | zapasowy asembler (podzbior MADS -> format SDX, bloki main+EXTRAM) |
| `tools/verify.py` | weryfikacja binarki (struktura, relokacja, dekodowanie) |
| `tools/simtest.py` | testy funkcjonalne SIO2SD.SYS (symulacja 6502 + SIO2SD) |
| `tools/simtest2.py` | testy funkcjonalne SDCDEV.SYS (symulacja jadra SDX) |
| `tools/simtest2_bank.py` | jw. + model banku EXTRAM (wykrywa dostep przy zlym banku) |
| `tools/simext.py` | walidacja mechanizmu trampolina/EXTRAM (V_setme/V_popme) |
| `tools/simtest3.py` | test integracyjny: sterownik SDX + logika serwera Altirry |
| `tools/test_devproto.py` | test protokolu TCP serwera (klient udaje Altirre) |
| `altirra/sio2sd.atdevice` | urzadzenie SIO2SD dla Altirry (strona emulatora) |
| `altirra/sio2sd_server.py` | serwer: katalog dysku jako karta SD (fw 3.3) |
| `altirra/deviceserver.py` | framework Custom Device Server (Avery Lee, zlib) |
| `SDMOUNT.ASM` / `SDMOUNT.COM` | montowanie ATR/XEX pod D1:-D15: (zrodlo / binarka) |
| `altirra/xexboot.bin` | bootloader XEX dla wirtualnych dyskow (z tools/xexboot.asm) |
| `tools/xexboot.asm` / `tools/build_xexboot.py` | zrodlo i budowanie bootloadera |
| `tools/test_boot.py` | test bootloadera XEX (symulowany boot w py65) |
| `tools/test_sdmount.py` | test SDMOUNT.COM przeciwko logice serwera |

## Budowanie

Kanonicznie MADS-em:

    mads SDCDEV.ASM -o:SDCDEV.SYS
    mads SIO2SD.ASM -o:SIO2SD.SYS
    mads SDMOUNT.ASM -o:SDMOUNT.COM

Zapasowo (dokladnie tak zbudowano dolaczone binarki):

    python3 tools/sdxasm.py SDCDEV.ASM SDCDEV.SYS

Testy lokalnie (Python 3.7+, `pip install py65`, z katalogu projektu):

    python3 tools/simtest2.py SDCDEV.ASM        # logika sterownika
    python3 tools/simtest2_bank.py SDCDEV.ASM   # + poprawnosc bankow EXTRAM
    python3 tools/simtest.py SIO2SD.ASM
    python3 tools/verify.py SDCDEV.ASM SDCDEV.SYS

Zmienna srodowiskowa `HISIO=1` uruchamia testy z obecna sygnatura Hias,
ale `SDCDEV /H` nie skacze juz pod `$CFED`; tryb turbo jest sprawdzany
przez komendy SIO2SD z bitem `$80`.

## Stan weryfikacji

Binarki nie byly jeszcze testowane na sprzecie. Zweryfikowano:

1. strukture plikow SDX wg SDX450 Programming Guide rozdz. 2
   (bloki $FFFA/$FFFE, fix-upy $FFFD, symbole $FFFB; blok relokowalny
   asemblowany kanonicznie od zera) + probna relokacje pod rozne adresy,
2. wszystkie instrukcje obu sterownikow niezaleznym dekoderem py65,
3. pelna symulacje funkcjonalna: emulator protokolu SIO2SD pod SIOV
   + wywolania funkcji jadra kd_0-kd_20 (SDCDEV) / handlera CIO
   (SIO2SD): instalacja, rejestracja urzadzenia, zapis/odczyt,
   dwa pliki naraz (COPY SDC:->SDC:), strumien katalogu dla DIR,
   kd_first/kd_next z maskami, mapowanie _NNN, rename/delete/mkdir/
   rmdir/chdir/sciezki, kody bledow, zmiana katalogu z panelu.

Interfejs jadra wg SDX 4.50 Programming Guide (rozdz. 24); rejestracja
urzadzen jadra wymaga SDX 4.40+. Po pierwszych testach na Altirze
(SDX 4.49/4.50) lub sprzecie warto sprawdzic zwlaszcza: DIR na duzych
katalogach, COPY duzych plikow na karte i zachowanie przy wyjetej karcie.

## Emulacja SIO2SD w Altirze (katalog altirra/)

Poniewaz Altirra nie emuluje protokolu sterujacego SIO2SD, projekt
zawiera wlasne urzadzenie: `altirra/sio2sd.atdevice` + serwer
`altirra/sio2sd_server.py`, ktory udostepnia wskazany katalog dysku
jako karte SD (API firmware 3.3, komendy $00-$27).

**Katalog bazowy karty.** Tak jak prawdziwe SIO2SD, natywne API plikowe
operuje w podkatalogu **`Atari`** udostepnianego katalogu - to on jest
korzeniem karty (`SDC1:` + `DIR` z SDX od razu pokazuje jego zawartosc,
bez wchodzenia w podkatalog). Podkatalog `Atari` jest tworzony przy
starcie, jesli go brak. Rowniez montowanie ATR-ow (`--mount`, konsola
`mount`) szuka plikow wzgledem `<katalog>/Atari`. Pliki umieszczone poza
`Atari` nie sa widoczne z karty.

W glownym katalogu karty, obok podkatalogu `Atari`, serwer obsluguje
oryginalny plik konfiguracji `SIO2SD.CFG`. Przy starcie odczytuje z niego
mapowanie D1:-D15:, a przy montowaniu, podpinaniu pustego dysku i
odmontowaniu aktualizuje odpowiednie sloty, zachowujac pozostale pola
pliku.

Tryb `CFG selector` w GUI emuluje zachowanie wybieraczki z prawdziwego
SIO2SD: po zimnym starcie Atari podpina `SIO2SD.XEX` jako D1:. Plik jest
szukany najpierw w glownym katalogu karty SD, potem w `Atari`, a na koncu
uzywany jest dolaczony `Configurator_35\Sio2SDBootLoaderCfgTools.atr`.
Poniewaz oryginalna wybieraczka bywa ATR-em nazwanym `SIO2SD.XEX`, serwer
rozpoznaje ATR po naglowku, nie tylko po rozszerzeniu.

Uruchomienie (Python 3.7+):

    cd altirra
    python sio2sd_server.py D:\ATARI\KARTA_SD

albo po prostu `sio2sd_server.bat` z katalogu projektu - udostepnia
katalog `sd\` obok skryptu (tworzy go przy pierwszym uruchomieniu);
dodatkowe opcje przechodza dalej, np. `sio2sd_server.bat -v`.

Graficzny panel startowy:

    sio2sd_gui.bat

Budowanie wersji EXE:

    build_exe.bat

Wynikowy program trafia do `dist\SIO2SD-GUI.exe`. Przy pierwszym
uruchomieniu wersja EXE tworzy obok siebie katalog `sd` oraz wypakowuje
pliki `altirra\sio2sd.atdevice` i `altirra\xexboot.bin`, jesli ich tam
jeszcze nie ma.

GUI pozwala wybrac katalog karty, ID urzadzenia, port, tryb tylko do
odczytu oraz montowac/odmontowywac obrazy w slotach D1:-D15: bez konsoli.
Okno jest podzielone na zakladki `Karta SD`, `Napedy`, `Server`, `Log`;
tabela napedow odswieza sie automatycznie po zmianach mapowania.
Zakladka `Karta SD` zawiera wybor katalogu oraz przegladarke plikow
z filtrem typow i szybkim montowaniem wybranego pliku do wskazanego
napedu. Zakladka `Server` zawiera ustawienia serwera i checkliste
Altirry z zielonym ✓ oraz czerwonym ✗.
Dolna linia statusu pokazuje stan serwera, diody `SIOACT`, `SDACT`,
`ERROR` oraz przycisk otwierania mini panelu.
Przycisk `Mini LCD` otwiera kompaktowy panel stylizowany na wyswietlacz
SIO2SD z punktowa matryca znakow, diodami `SIOACT`, `SDACT`, `ERROR`
i przyciskami funkcyjnymi do wyboru napedu, montowania, pustego dysku
i odmontowania. LCD w trybie mini pokazuje wybrany naped i podpięty plik
w pierwszej linii oraz biezacy katalog karty w drugiej. Po wlaczeniu
mini panel chowa pelne okno; `K4 HIDE` przywraca pelny panel. Przycisk
`TOP ON`/`TOP OFF` przelacza trzymanie mini panelu zawsze na wierzchu.
Ustawienia GUI, auto start serwera oraz ostatni tryb okna sa zapisywane
lokalnie w `sio2sd_gui_settings.json`.

(opcje: `--id 0-3` identyfikator urzadzenia, `--read-only`,
`--port 9977`, `-v` logowanie komend)

Nastepnie w Altirze (wymagana wersja 4.0+): System > Configure
System > Peripherals > Devices > Add > (na dole listy) Custom >
wskaz `sio2sd.atdevice`.
Serwer musi dzialac, zanim emulator sie polaczy. Po zimnym starcie
emulowanego Atari mozna uruchomic `SDCDEV` i pracowac na `SDC1:`
(przy domyslnym `--id 0`).

### Wirtualne napedy D1:-D15: w emulacji

Serwer emuluje tez zamontowane napedy (jak prawdziwy SIO2SD):

* z Atari: `SDMOUNT D2: GRA.ATR` (API $02/$03, patrz wyzej),
* z hosta: opcja `--mount 1=GRA.ATR` przy starcie serwera albo
  komendy w konsoli serwera: `mount 1 GRY/GRA.ATR`, `umount 1`,
  `list`, `quit`. Wystarczy sama nazwa pliku - serwer szuka jej
  kolejno: w biezacym katalogu karty, w korzeniu karty, wzgledem
  katalogu uruchomienia, a na koncu w calym drzewie karty (bez
  rozrozniania wielkosci liter). Nazwy ze spacjami mozna podac
  w cudzyslowach albo bez,
* obslugiwane: pliki `.ATR` (odczyt i zapis, SD/DD), `.XEX/.COM/.EXE`
  (dysk rozruchowy z wlasnym bootloaderem `xexboot.bin`), inne pliki
  do 90 KB (surowy zrzut sektorow), pusty dysk (`/E`, w pamieci).

Bootowanie z zamontowanego dysku: w Altirze odepnij wewnetrzny D1:
(File > Detach Disk), wylacz Fast boot (System > Configure System >
Acceleration) i zrestartuj emulowane Atari - dziala to samo, co przy
FujiNet. **Uwaga: numer napedu zamontowany w emulacji SIO2SD musi byc
pusty w samej Altirze** (File > Disk Drives) - jesli np. SDX ladujesz
z obrazu podpietego jako D1: w Altirze, montuj przez SIO2SD pod D2:
lub wyzej. Gdy oba urzadzenia odpowiadaja na ten sam numer, bajty
nakladaja sie na szynie i Atari zglasza `143 SIO checksum error`.

Napedy wymagaja `sio2sd.atdevice` w wersji 1.2+:

* v1.1: odpowiedz ACK wysylana dopiero po opadnieciu linii COMMAND -
  sterownik dyskowy SDX inicjuje odbiornik POKEY pozniej niz SIO
  w OS i wczesniejsza odpowiedz przepadala (`138 Device does not
  respond`, w logu serwera sondy `cmd=$D3` bez reakcji na NAK-i),
* v1.2/v1.3: obsluga trybu high-speed XF551 - komendy z bitem 7
  ($D2/$D3/$D0/$D7/$CE), ktorymi SDX odpytuje naped; COMPLETE
  i dane ida wtedy przy ~38400 bodach (46 cykli/bit = POKEY divisor
  16), ACK/NAK zawsze przy 19200, a COMPLETE jest opozniony o ~2 ms
  po ACK - komputer po ACK dopiero przestawia POKEY na 38400
  i wczesniejsza odpowiedz ginie (objaw: `139 Device NAK`, w logu
  serwera powtorzone `$D2 ACK HS` i fallback do `$52`). Sonda $3F
  (Happy/Speedy) dostaje NAK - tak samo robi prawdziwy XF551.

* v1.4/v1.5: tempo bajtow w ramkach danych jak w prawdziwych napedach
  (1050: 

* v1.8: odbior nastepnej ramki komendy jest uzbrajany z wyprzedzeniem,
  a nie dopiero po wykryciu linii COMMAND. To usuwa wyscig widoczny przy
  szybkich ramkach API/TopDrive: pierwszy bajt potrafil wpasc zanim skrypt
  ustawil bufor odbioru, przez co `SDCDEV /H` oblewal samotest `$00` i
  wracal do 19200.
