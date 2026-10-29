# Implementierte FPGA-Debug-UART

Stand: 28. Oktober 2026. Diese Beschreibung ist das implementierte Protokoll,
kein alternativer Protokollvorschlag. Die Quellen sind in `cpu/rtl/`, `debug_uart/rtl/` und `system/rtl/` getrennt.
`system/rtl/prim_system.v` instanziiert die CPU, den Bus-Multiplexer, den
Speicher/MMIO-Controller und `debug_uart_link`. RX, TX und TX-Arbiter liegen
vollständig in `debug_uart/rtl/`. Der CPU-Kern enthält keine Systemintegration.

## Leitung und Kanäle

Eine UART-Verbindung, 115200 Baud, 8N1, Datenbits LSB zuerst, idle high.
`prim_system.CLK_HZ` beschreibt den FPGA-Takt. Der konstante Baudteiler ist
`(CLK_HZ + 57600) / 115200`, standardmäßig 868 bei 100 MHz. Der reale Baudwert
ist CLK_HZ/Teiler. Der Teiler muss ausreichend groß für Bitmittenabtastung und
die externe Baudtoleranz sein; RX ist mit 8, 9, 17 und 868 Takten/Bit getestet.
Der RX synchronisiert den Eingang über zwei Flipflops, prüft das Startbit in
seiner Mitte und tastet danach einmal je Bit ab. Kein 16-faches Oversampling,
kein Empfangs-FIFO. Die RX-Leitung muss im unbenutzten Zustand high sein.

Bit 7 trennt die Kanäle:

| Auf der Leitung | Bedeutung |
|---|---|
| 0xxxxxxx | normale CPU-Ausgabe, sieben Nutzbits |
| 1xxxxxxx | Debug-ASCII-Zeichen, Bit 7 zusätzlich gesetzt |

Empfangene Zeichen des normalen Kanals aktualisieren ein separates CPU-RX-Register.
Bit 7 wird ausschließlich zur Kanaltrennung verwendet; CPU-Daten haben sieben Bits. Im Folgenden
stehen alle Debug-Zeichen ohne das zusätzliche Bit 7. Bit 6 hat keine separate
Steuerbedeutung. CPU-MMIO-Ausgaben maskieren Bit 7; UTF-8 bleibt dadurch nicht
unverändert erhalten. Die Python-CPU/der lokale Softwaredebugger können weiterhin
8-Bit-UART-Daten modellieren; das ist nicht das FPGA-Leitungsprotokoll.

Adressen und Daten verwenden ausschließlich lowercase Hex `0`–`9`, `a`–`f`.
Das niedrigste Nibble kommt zuerst: `12` = 0x21, `1234` = 0x4321,
`12ab` = 0xba21. Antworten verwenden dieselbe Reihenfolge mit fester Breite.

## Kommandos und Antworten

| Kommando | Bedeutung | Antwort |
|---|---|---|
| `H` | HALT, auf bestätigten Halt warten | `K` |
| `G` | RUN am aktuellen PC | `K` |
| `S` | STEP, nur bei Halt, genau eine Instruktion | `K` nach erneutem Halt |
| `Z` | RESET-HALT, ausschließlich CPU zurücksetzen | `K` nach Halt am Reset-PC |
| `P` | READ-PC, nur bei Halt | `K` + vier Hexziffern |
| `?` | CPU-Status und Neustart des Eingabeparsers | `T` + eine Hexziffer |
| `q` | UART-Status, auch bei laufender CPU und ohne Buszugriff | `K` + eine Hexziffer |
| `A` + 1–4 Hexziffern | Adresspointer teilweise setzen | keine |
| `r` | READ8 am Pointer | `K` + zwei Hexziffern |
| `R` | READ16 am Pointer | `K` + vier Hexziffern |
| `w` | dauerhaften Byte-Schreibmodus beginnen | keine für das Präfix |
| `W` | dauerhaften Wort-Schreibmodus beginnen | keine für das Präfix |

`r`, `R`, `w` und `W` benötigen bestätigten CPU-Halt. Der Host stellt diese
Vorbedingung sicher. Nach jedem abgeschlossenen Schreibzugriff folgt `K`.
Es gibt keine Echozeichen. RUN bestätigt die Wiederaufnahme, nicht einen
späteren Halt. Das Statusnibble enthält Bit 0 = CPU angehalten, Bit 1 =
gespeicherter BREAK-Grund; Bits 3:2 sind null.

Ein BREAK sendet asynchron genau ein `B`. Es ist kein Kommando und keine
Antwort auf HALT. STEP auf BREAK erzeugt sowohl `K` als auch `B`. Der Host
verarbeitet `B` auch beim Warten auf eine Antwort. Ein BREAK-Zeichen wird
vollständig vor oder nach einer Debug-Antwort gesendet, niemals zwischen
Präfix und Zahlenziffern. CPU-Ausgabe darf zwischen Debug-Zeichen erscheinen.

### Pointer und Eingabemodi

Der 16-Bit-Pointer wird nur beim Reset des Debug-Controllers auf 0x0000
initialisiert. `Z` erhält ihn. `A` schreibt ab dem niedrigsten Nibble nur die
angegebenen Nibbles, die höheren bleiben erhalten. `A12ab` setzt 0xba21;
anschließend setzt `Aa` 0xba2a und `A4c` 0xbac4. Ein vollständiges Setzen muss
immer vier Nibbles übertragen. `A0010` setzt unabhängig vom alten Pointer 0x0100.

Die Adresseingabe endet durch ein neues Kommando. Es gibt weder Abschluss
durch Pause noch Empfangstimeout. `A` selbst löst keinen Buszugriff und keine
Antwort aus. `A001r` ist eine zulässige teilweise Adresseingabe mit folgendem
Byte-Lesekommando. Jeder Lesezugriff benötigt ein eigenes `r` oder `R`.

Im Modus `w` bilden je zwei, bei `W` je vier Hexziffern einen Datenwert. Sobald
der Wert vollständig ist, beginnt ein Buszugriff am Pointer. Erst bei ACK
wird der Pointer um eins beziehungsweise zwei erhöht, modulo 65536. Das gilt
für Lesen und Schreiben. Ein Wort wird als vorhandene Wort-Busoperation
angefordert, auch an ungeraden oder überlaufenden Adressen.

Der Schreibmodus bleibt nach ACK aktiv. Beispielsweise schreibt `w12`,
Warten auf `K`, `34`, Warten auf `K`, `ab`, Warten auf `K` die Bytes 0x21,
0x43, 0xba. Entsprechend schreibt `W1234`, Warten auf `K`, `abcd`, Warten auf
`K` die Wörter 0x4321 und 0xdcba. Der Host darf die Daten für den nächsten
Wert erst nach dessen vorherigem `K` senden.

Jedes neue Kommando beendet den vorherigen Adress- oder Schreibmodus und
verwirft einen unvollständigen Datenwert. Nach `A` muss `w` oder `W` erneut
aktiviert werden. `w1?` verwirft beispielsweise das einzelne Datennibble und
liefert Status. Unbekannte Zeichen werden ignoriert. Unvollständige Eingaben
dürfen beliebig lange bestehen bleiben.

Ein bereits gestarteter Buszugriff wird nicht abgebrochen. Während ausstehender
Operationen werden keine weiteren Kommandos angenommen. Insbesondere ist `?`
kein Abbruch eines hängenden Buszugriffs. Der korrekte Host sendet während
solcher Operationen keine neuen Kommandos.

## CPU und Bus

HALT beendet die laufende Instruktion einschließlich Fetch, Operanden- und
Speicherwartezyklen und hält an der Instruktionsgrenze vor dem nächsten Fetch.
Ein bereits bestätigter Halt wird ebenfalls mit `K` quittiert. Im Halt ist der
CPU-Bus inaktiv (BS=00). Register und Zustand verwenden ausschließlich synchrone
Enables; kein gegateter oder abgeleiteter CPU-Takt.

STEP hebt den Halt für genau eine vollständige Instruktion auf. READ-PC liefert
bei Halt die Adresse der nächsten auszuführenden Instruktion. RUN setzt dort
fort. RESET-HALT fordert zunächst Halt an, um einen laufenden SRAM-Auftrag
ordnungsgemäß abzuschließen, setzt dann nur die CPU zurück und hält sie bei
0x0000. UART, Debug-Controller, dessen Pointer und SRAM werden nicht zurückgesetzt.
Ein externer `i_reset` setzt dagegen das gesamte System einschließlich UART
und Debug-Controller zurück. Mit `prim_system.START_HALTED=1` bleibt die CPU
dabei vor dem ersten Fetch bei PC 0000 angehalten (Standardwert 0 startet
die Ausführung). `o_halted` meldet den bestätigten Halt an den Board-Wrapper;
die SRAM-Zellen besitzen auch dann keinen Reset.

BREAK (auch mit gesetztem Return-Bit) verändert keinen Stack und hat keinen
Return-Effekt. Der PC rückt auf die Folgeinstruktion vor. BREAK setzt den
Haltgrund bis RUN oder RESET-HALT. Ein separater Pending-Zustand merkt die
Benachrichtigung vor, bis der TX sie übernimmt. Das Senden von `B` löscht nicht
den Haltgrund. Ein bereits wartendes Ereignis bleibt auch bei CPU-Reset
vorgemerkt. Der kooperative Host und die seriellen Antwortwartebedingungen
verhindern mehrere ungesendete BREAK-Ereignisse gleichzeitig; eine Ereignis-FIFO
ist daher nicht nötig.

CPU und Debug-Master verwenden einen Multiplexer vor dem vorhandenen Bus.
Nur bestätigter CPU-Halt schaltet zum Debug-Master. Adresse, Schreibdaten,
BS und WE bleiben bis ACK stabil. Der Pointer ändert sich erst nach ACK.
Byte-, Wort-, unaligned- und Wrapping-Semantik des vorhandenen Controllers
bleiben erhalten. MMIO-Zugriffe haben ihre normalen Seiteneffekte.

### CPU-UART und Puffer

| Adresse | Lesen | Schreiben |
|---|---|---|
| FFFD | LED1/LED2 in Bit 0/1; Bits 7:2 null | Bit 0/1 setzen LEDs (1 = an), Bits 7:2 ignoriert |
| FFFE | Bit 0: RX empfangen; Bit 1: TX-Puffer frei; Bits 7:2: null | ignoriert |
| FFFF | zuletzt empfangenes CPU-Zeichen, Bit 7 null | CPU-TX-Puffer übernehmen, sieben Nutzbits |

CPU-Empfang besitzt ein Datenregister und ein Received-Flag. Lesen von FFFF
löscht das Flag erst bei Bus-ACK, erhält aber den Datenwert. Ohne neuen Empfang
wird weiter das zuletzt empfangene Byte geliefert. Neuer Empfang gewinnt gegen
zeitgleiches Lesen. Bei Überlauf überschreibt das neue Byte den alten Inhalt;
der korrekte Host vermeidet Überlauf über die UART-Statusabfrage `q`.

CPU-TX besitzt einen Ein-Byte-Puffer zusätzlich zum UART-Schieberegister.
Schreiben erhält ACK bei Pufferübernahme, bei vollem Puffer wartet der Bus.
Statusbit 1 beschreibt den freien Puffer, nicht die physisch ruhende TX-Leitung.
Systemreset initialisiert RX-Daten/Flags und TX-Puffer. RESET-HALT setzt nur
die CPU zurück; UART-Puffer und letztes RX-Byte bleiben dabei erhalten.

Wortzugriffe sind little-endian, auch über MMIO-Grenzen: Lesen bei FFFE liefert
Status unten und RX-Daten oben und quittiert den RX-Verbrauch bei ACK. Bei FFFD
wird das LED-Register unten mit Status oben kombiniert; bei FFFC SRAM unten
mit dem LED-Register oben. Systemreset schaltet die LEDs aus, CPU-Reset erhält sie. Bei FFFF wird RX unten mit SRAM an
0000 oben kombiniert. Schreiben bei FFFE ignoriert die Status-Lane und übernimmt
die hohe Lane in TX; bei FFFF geht die niedrige Lane in TX und die hohe nach
SRAM-Adresse 0000. Gemischte Zugriffe schließen zuerst die SRAM-Lane ab; RX-Verbrauch und TX-
Übernahme erfolgen erst beim abschließenden Bus-ACK. Dies gilt auch für den
Debug-Master. Andere Wortzugriffe
bleiben unveränderte SRAM-Wortoperationen.

Debug-Antworten und BREAK haben an Bytegrenzen Vorrang vor CPU-TX. Ein bereits
begonnener Frame wird beendet. CPU-Empfang ist vom Debug-Parser unabhängig;
ein volles RX-Register blockiert keine Debug-Kommandos. Ein Debug-MMIO-Schreiben
quittiert die Übernahme in den CPU-TX-Puffer und erzeugt danach `K`. Der TX-Puffer
kann während der Debug-Antwort warten; es entsteht kein gegenseitiger Deadlock.

## Python-Hostbibliothek

`prim_debug_uart.DebugUART` (kompatibel auch `prim.debug_uart.DebugUART`) benötigt ein Byte-Transportobjekt mit `read(size)`
und `write(bytes)`, etwa pyserial. `connect()` öffnet optional pyserial fest mit
115200/8N1. pyserial muss dafür separat installiert sein. Ein vorhandenes
`timeout`-Attribut wird auf höchstens 0,1 Sekunden gesetzt. Andere Transports
müssen selbst begrenzte Lesezeiten gewährleisten. Antworttimeouts verwenden
eine monotone Uhr und werfen `DebugTimeout`; unerwartete Antworten erzeugen
eine verständliche Exception. Der Transport wird vom Aufrufer geschlossen.

```python
from prim_debug_uart import DebugUART

uart = DebugUART.connect('/dev/ttyUSB0', timeout=2.0)
try:
    uart.halt()
    pc = uart.read_pc()
    uart.write_bytes([0x21, 0x43, 0xba], address=0x1000)
    word = uart.read16(address=0x1000)
    uart.step()
    status = uart.status()
finally:
    uart.transport.close()
```

Weitere Methoden: `run`, `reset_halt`, `set_address`, `read8`, `write_words`,
`uart_status` (RX-Flag und TX-Puffer-frei).
Adressargumente sind optional; ohne sie wird der aktuelle Hardwarepointer
verwendet. `set_address` überträgt immer alle vier Nibbles. Schreibfolgen
verwenden ein einziges Präfix und warten auf jedes `K`. Ein Aufrufer zur Zeit;
die Bibliothek prüft nicht alle CPU-Zustandsvorbedingungen automatisch.

Kanal-0-Ausgabe wird in `output` gesammelt und optional an `on_output(bytes)`
weitergereicht. BREAK erhöht `break_events` und ruft optional `on_break()` auf.
Die Auswertung geschieht beim Lesen von Antworten. Ein `B` hinter dem letzten
Antwortzeichen wird spätestens beim nächsten Aufruf, beispielsweise `status()`,
verarbeitet. Diese blockierende Basisklasse hat keinen Hintergrundthread;
die unten beschriebene UARTSession der Konsole liest dagegen kontinuierlich. Nach einem Hosttimeout muss der
Aufrufer den Zustand prüfen; ein Timeout bedeutet keinen Hardware-Abbruch.

## Bewusst ausgelassene Prüfungen

Keine Checksummen, Wiederholungen, Empfangs-/Bus-Timeouts, Fehlerantworten,
Empfangs-FIFO oder Kommandowarteschlange. Keine Behandlung zu schneller Hosts
während laufender Operationen, falscher Kommandofolgen, zu vieler Adressnibbles,
verlorener/doppelter/verfälschter Zeichen oder UART-Framing-Fehlermeldungen.
Keine gesonderte Prüfung von unaligned-Adressen oder Überlauf. Verhalten bei
Protokollverletzungen ist, abgesehen vom definierten Modusneustart und
Nichtabbruch laufender Buszugriffe, undefiniert.

## Prüfung und Ressourcen

Die Tests sind ihren Komponenten zugeordnet:

- `python debug_uart/tests/test_rtl.py`: RX einschließlich Startglitch,
  Phasenversatz/Jitter, Reset und aller 256 Leitungsbytes; TX; Priorisierung und
  Rückstau im TX-Arbiter; Parser und Debug-Master ohne CPU oder Systemmodule.
- `python cpu/tests/test_debug_cpu.py`: stabile Busaufträge bei Wartezyklen,
  HALT/STEP einschließlich Speicherzugriffen und BREAK.RET mit belegten Stacks.
- `python system/tests/test_debug_uart.py`: vollständiger serieller Debugpfad,
  Kanaltrennung, Teiladressen, Schreibmodi, Pointerinkrement/Überlauf,
  BREAK bei belegtem TX und während mehrstelliger Antwort, RESET-HALT mit
  erhaltenem SRAM/Pointer und UART-MMIO ohne Deadlock.
- `python debug_uart/tests/test_host.py`: Hostkodierung, Antwortwartebedingungen,
  Kanaltrennung, BREAK-Verarbeitung und Fehler-/Timeoutmeldungen.

Die aktuelle Regression umfasst 15 CTest-Suiten, einschließlich UART-Puffern,
CPU-Echo mit Debugverkehr, Session-/PTY-Konsole und Board-Host-CLI. Die
bestehenden SRAM-, ISA-, Compiler- und UART-Tests bleiben enthalten.
Aktuelles Ergebnisprotokoll: `build/uart-duplex-validation/ctest.log`.

Synthese mit Yosys 0.68+136, `synth_ice40 -top prim_system`, gleicher Standardtakt,
Historischer Vergleich vor der aktuellen RX/TX-Puffererweiterung: ursprünglicher
Stand vor Einführung der Debug-UART, danach vor und nach der Komponententrennung.
Die aktuellen Board-Ressourcen und das Timing stehen in der Board-README.

| Ressource | Ohne Debug | Vor Trennung | Nach Trennung |
|---|---:|---:|---:|
| SB_LUT4 | 2311 | 2674 | 2693 |
| SB_DFF* gesamt | 651 | 750 | 750 |
| SB_CARRY | 109 | 187 | 191 |
| Zellen einschließlich Scopeinfo/TBUF | 3091 | 3633 | 3659 |

Die Trennung verwendet keine zusätzlichen Register oder FIFOs. Die Synthese
der getrennten Module ergibt 19 zusätzliche LUT4 und vier Carry-Zellen.
Logs: ursprüngliche Synthesen unter `build/debug-uart/`; aktuelle Synthese unter
`build/restructure/synth.log`. Reproduzierbar über den Root-CMake-Target `yosys`
oder `yosys -s system/synth.ys` vom Projekt-Root aus.

```sh
yosys -p 'read_verilog -Icpu/rtl cpu/rtl/prim.v system/rtl/memory.v debug_uart/rtl/uart_tx.v debug_uart/rtl/uart_buffers.v debug_uart/rtl/uart_rx.v debug_uart/rtl/debug_uart.v system/rtl/memory_io.v system/rtl/bus_mux.v debug_uart/rtl/uart_arbiter.v debug_uart/rtl/debug_uart_link.v system/rtl/prim_system.v; synth_ice40 -top prim_system; stat'
```

Dies ist ein Synthesevergleich, keine Platzierungs-, Routing- oder Frequenzzusage.
Der Benutzer hat den laufenden Board-Bitstream, LED2-Heartbeat, Debug-Kommunikation
und erfolgreiches SRAM-Streaming-Laden am 29. Oktober 2026 bestätigt.
Metastabilitäts-/Baudtoleranz und externe SRAM-Timingreserven sind dadurch nicht
vermessen; nicht jede Loader-Option wurde auf Hardware geprüft.

Der Olimex-Rev.B-Board-Wrapper verwendet nach ausdrücklicher Freigabe eine
FPGA-PLL von 100 auf 25 MHz. CPU, UART und SRAM nutzen gemeinsam diesen globalen
Systemtakt; der UART-Teiler ist dort 217. Die PLL-Ausnahme ist auf den Board-Wrapper
beschränkt. Reset wird erst nach synchronisiertem PLL-Lock freigegeben.
Siehe [Board-Flow](../boards/olimex_ice40hx8k_evb/README.md).

Das Board-Hostskript stellt `halt`, `run`, `step`, `reset-halt`, `pc` und
`uart-status` separat bereit. `step` und `pc` prüfen vorab den Haltstatus.
Images, die FFFD, FFFE oder FFFF enthalten, benötigen `load --skip-uart-mmio`.
Jede enthaltene MMIO-Adresse wird gemeldet und beim Schreiben und Verifizieren
ausgelassen. Ein vollständiges Image schreibt damit 65.534 SRAM-Bytes;
die optionale Prüfung ist auf dieselben Bytes begrenzt.
Der SRAM-Loader verwendet dauerhafte 16-Bit-Schreibzugriffe mit OK pro Wort und
einen Bytezugriff für ein ungerades Restbyte. Rücklesen ist standardmäßig aus;
`--verify` aktiviert Wort-Lesezugriffe mit automatischem Pointer-Inkrement und
gegebenenfalls einen letzten Bytezugriff. `--run` startet nach erfolgreichem
Laden und, falls angefordert, erfolgreicher Verifikation. Das vollständige
Speicherabbild wird weiterhin übertragen; eine Verkleinerung ist noch offen.

Auf Wunsch wird beim SRAM-Laden die Wartebedingung pro Wert bewusst gelockert:
Der Host sendet Wörter fortlaufend und zählt OKs parallel. Der Controller erhält
keinen RX-FIFO und verwirft weiterhin RX-Zeichen während BUS. Fehlende/falsche
Bestätigungen brechen den Ladevorgang mit Fehlermeldung ab; kein automatischer
Neustart und kein RUN. Nach einem Streamingfehler wird die Verbindung geschlossen
und der Benutzer kann das gesamte Abbild erneut laden. `--write-delay` setzt eine
optionale Pause in Sekunden zwischen Wörtern. Streaming ist auf SRAM-Laden
beschränkt; normale `write_words`/`write_bytes` warten weiterhin auf jedes OK.
Bestätigungszählung allein erkennt keine beliebige Datenverfälschung; `--verify`
bleibt die optionale Inhaltsprüfung. Ein hängender Buszugriff wird nicht abgebrochen.

## Interaktive Konsole

`host.py --port PORT console` hält den Port über Laden, RUN und den Dialog mit
der CPU geöffnet. Ein zentraler Reader trennt Debug-Antworten, asynchrone BREAKs
und CPU-Ausgabe; ein separater Sender nutzt `q` als RX-Flusskontrolle. Bei vollem
CPU-RX-Register warten Tastatureingaben hostseitig, Debug-Steuerung bleibt möglich.
Der Host sendet höchstens ein CPU-Byte je freiem Register. Statusabfragen werden
nicht zwischen die Zeichen oder Werte einer laufenden Debug-Operation geschoben.
SRAM-Debugzugriffe benötigen weiterhin CPU-Halt; Transport beider Kanäle bleibt
auch dann aktiv. Nicht-ASCII/UTF-8-Eingaben werden als CPU-Daten abgewiesen.

Ctrl+B öffnet den lokalen Debug-Prompt, Ctrl+D beendet die Konsole ohne HALT oder
RESET. Ctrl+V überträgt das nächste Byte wörtlich, auch Ctrl+B oder Ctrl+D.
Leeres Enter im Prompt kehrt in den CPU-Modus zurück. Im CPU-Modus wird Enter
übertragen. `help`, `?` und `console --help` zeigen alle Befehle und Keybindings.
Der Prompt bietet `halt`/`stop`, `step`, `reset-halt`, `run`, `pc`, `status`,
`uart-status`, `sram-check`, `load DATEI [--skip-uart-mmio] [--run]` und `quit`. CPU-Ausgabe und
BREAK bleiben auch während Hilfe, Eingabe und ausstehender Antworten aktiv.
