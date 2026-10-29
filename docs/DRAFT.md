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

Empfangene Zeichen des normalen Ausgabekanals werden ignoriert. Im Folgenden
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
| `?` | Status und Neustart des Eingabeparsers | `T` + eine Hexziffer |
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
und Debug-Controller zurück; die SRAM-Zellen besitzen auch dann keinen Reset.

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

Schreiben auf Byteadresse FFFF erzeugt normale UART-Ausgabe; Lesen dort liest
SRAM. Wortschreiben bei FFFE schreibt den niedrigen Teil in SRAM und den
hohen Teil auf UART. Bei FFFF geht der niedrige Teil an UART und der hohe
nach SRAM-Adresse 0000. Dies gilt auch für den Debug-Master.

Der vorhandene TX hat valid/ready und keinen zusätzlichen FIFO. Debug-Antworten
und BREAK haben an Bytegrenzen Vorrang. Ein bereits gestarteter Frame wird
vollständig gesendet. CPU-MMIO wartet bei Bedarf im Bus-Handshake. Ein Debug-
Schreibzugriff auf UART-MMIO wartet ebenfalls auf die Annahme des Ausgabebytes;
erst dessen Bus-ACK erzeugt das `K`. Dadurch kann die Antwort nicht die eigene
MMIO-Ausgabe blockieren. Eine unabhängige BREAK-Meldung darf vorher senden.

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

Weitere Methoden: `run`, `reset_halt`, `set_address`, `read8`, `write_words`.
Adressargumente sind optional; ohne sie wird der aktuelle Hardwarepointer
verwendet. `set_address` überträgt immer alle vier Nibbles. Schreibfolgen
verwenden ein einziges Präfix und warten auf jedes `K`. Ein Aufrufer zur Zeit;
die Bibliothek prüft nicht alle CPU-Zustandsvorbedingungen automatisch.

Kanal-0-Ausgabe wird in `output` gesammelt und optional an `on_output(bytes)`
weitergereicht. BREAK erhöht `break_events` und ruft optional `on_break()` auf.
Die Auswertung geschieht beim Lesen von Antworten. Ein `B` hinter dem letzten
Antwortzeichen wird spätestens beim nächsten Aufruf, beispielsweise `status()`,
verarbeitet. Es gibt keinen Hintergrundthread. Nach einem Hosttimeout muss der
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

Alle zwölf CTest-Suiten bestanden nach der Trennung der Komponenten. Die
bestehenden SRAM-, ISA-, Compiler- und UART-Tests bleiben enthalten.
Ergebnisprotokoll: `build/restructure/ctest.log`.

Synthese mit Yosys 0.68+136, `synth_ice40 -top prim_system`, gleicher Standardtakt,
Vergleich mit dem ursprünglichen Stand vor Einführung der Debug-UART und
dem Stand direkt vor der Verzeichnis-/Komponententrennung:

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
yosys -p 'read_verilog -Icpu/rtl cpu/rtl/prim.v system/rtl/memory.v debug_uart/rtl/uart_tx.v debug_uart/rtl/uart_rx.v debug_uart/rtl/debug_uart.v system/rtl/memory_io.v system/rtl/bus_mux.v debug_uart/rtl/uart_arbiter.v debug_uart/rtl/debug_uart_link.v system/rtl/prim_system.v; synth_ice40 -top prim_system; stat'
```

Dies ist ein Synthesevergleich, keine Platzierungs-, Routing- oder Frequenzzusage.
Board-Pins, Hardware-UART, reale Metastabilitäts-/Baudtoleranz und SRAM-Timing
nach Place-and-Route wurden nicht auf physischer Hardware geprüft.
