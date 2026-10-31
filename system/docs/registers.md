# Registerübersicht des Prim-Systems

Diese Referenz fasst alle softwareseitig sichtbaren Register des integrierten
[`prim_system`](../rtl/prim_system.v) sowie die CPU-Register zusammen.
Die Adressdekodierung liegt in [`memory_io.v`](../rtl/memory_io.v).
R bedeutet Lesen, W Schreiben; Resetwerte gelten nach einem Systemreset.

## Speicher- und Registerkarte

Der Bus verwendet 16-Bit-**Byteadressen** und Little Endian. Bei 16-Bit-Registern
liegt das niederwertige Byte an der kleineren Adresse.

| Byteadresse | Register/Bereich | Breite | Zugriff | Resetwert | Bedeutung / Nebenwirkung |
|---|---|---|---|---|---|
| `0x0000..0xFFEF` | SRAM | 65520 Bytes | R/W | Nicht initialisiert | Programmspeicher und Daten |
| `0xFFF0..0xFFF1` | Timer COUNT | 16 Bit | R/W | `0x0000` | Aktueller Zählerstand; Schreiben mit Ergebnis null setzt auch die Vorteilerphase zurück |
| `0xFFF2..0xFFF3` | Timer COMPARE | 16 Bit | R/W | `0x0000` | Vergleichswert |
| `0xFFF4..0xFFF5` | Timer CSR | 16 Bit, davon 3 genutzt | R/W | `0x0000` | Timersteuerung; ungenutzte Bits lesen null, Schreibwerte dort werden ignoriert |
| `0xFFF6..0xFFF9` | VGA CONTROL / ROW_OFFSET / CURSOR_X / CURSOR_Y | 8 bits each | R/W | `0x00` | Optional with VGA_ENABLE=1; see [VGA bit fields](../../vga/README.md#cpu-register-and-memory-contract) |
| `0xFFFA` | VGA STATUS | 8 bits | R | Raster-dependent | Bit 0 blank, bit 1 vertical blank; writes ignored |
| `0xFFFB..0xFFFC` | Reserviert | 2 Bytes | R/W | `0x00` je Byte | Lesen liefert null, Schreiben ohne Wirkung |
| `0xFFFD` | LEDs | 8 Bit, davon 2 genutzt | R/W | `0x00` | LED1/LED2; ungenutzte Bits lesen null und werden beim Schreiben ignoriert |
| `0xFFFE` | UART CSR | 8 Bit, davon 4 genutzt | R; W für Bits 2/3 | `0x02` | Empfangs-/Sendestatus und Interruptfreigaben |
| `0xFFFF` | UART RX DATA | 8 Bit, davon 7 genutzt | R | `0x00` | Letztes Empfangsbyte; Lesen löscht RXAVAIL bei ACK, behält aber das Datenbyte |
| `0xFFFF` | UART TX DATA | 8 Bit, davon 7 genutzt | W | Puffer leer | Byte zum Senden einreihen; wartet bei vollem Puffer; Bit 7 wird ignoriert |

RX und TX teilen dieselbe Adresse und werden über die Zugriffsrichtung gewählt.
With `VGA_ENABLE=0`, `0xFFF6..0xFFFA` remain reserved (reads return zero,
writes are ignored). The Olimex board wrapper enables VGA. CONTROL bit 0
maps 4 KiB of video RAM at `0xE000..0xEFFF`, preserving the underlying SRAM.
See the [VGA reference](../../vga/README.md) for register and banking semantics.
Die physischen SRAM-Zellen hinter `0xFFF0..0xFFFF` sind über diesen Bus nicht
zugänglich. CPU und Debug-Master sehen dieselben Register und Nebenwirkungen.
Beim Laden eines vollständigen Speicherabbilds muss der Board-Host mit
`load --skip-mmio` den gesamten MMIO-Bereich aussparen.

## TokenForth-Speicherbelegung und Scratchpad

Innerhalb des SRAM definiert die Software zusätzliche Bereiche und
Verwaltungszellen. Die Konstanten stehen in
[`src/prim/isa.py`](../../src/prim/isa.py), ihre Verwendung in
[`src/prim/compiler.py`](../../src/prim/compiler.py).

| Byteadresse | Name | Verwendung |
|---|---|---|
| `0x0000..0x0009` | Startbereich | Platz für Startcode |
| `0x000A..0x000B` | H / HERE | 16-Bit-Zeiger auf das nächste freie Code-/Datenbyte |
| `0x000C..0x000D` | LATEST | 16-Bit-Zeiger auf die nächste freie Dictionaryzelle |
| Ab `0x000E` aufwärts | Code und Daten | Wachsen in Richtung Dictionary |
| Ab `0xFEFE` abwärts | Dictionary / `Consts.DICT` | Wortadressen; Eintrag i steht an `0xFEFE - 2*i` |
| `0xFEFC..0xFEFD` | Dictionaryeintrag 1 | Enthält die Adresse `0x000C` von LATEST |
| `0xFEFE..0xFEFF` | Dictionaryeintrag 0 | Enthält die Adresse `0x000A` von H |
| `0xFF00..0xFFEF` | Scratchpad / `Consts.AREA` | 240 Bytes SRAM für temporären Immediate-Code |

`AREA = DICT + 2 = 0xFF00`. `execute()` kopiert den Immediate-Code samt
abschließendem BREAK dorthin und startet die Python-CPU an dieser Adresse.
Die aktuelle Längenprüfung erlaubt höchstens 238 Codebytes plus ein BREAK,
also 239 belegte Bytes bis einschließlich `0xFFEE`.

Diese Aufteilung ist eine Softwarekonvention innerhalb des SRAM; die Hardware
schützt die Bereiche nicht gegeneinander. HERE/LATEST werden vom Compiler
initialisiert, nicht vom Hardware-Reset. Die ausführliche Erklärung mit
Dictionarybeispiel steht in
[Code und Architektur](../../docs/CODE.md#symbolindex-dictionary-und-speicheradresse).

## Bitbelegung der Steuerregister

### Timer CSR (`0xFFF4`, 16 Bit)

| Bit | Name | Zugriff | Reset | Bedeutung bei 1 |
|---|---|---|---|---|
| 0 | ENABLE | R/W | 0 | Zählen freigegeben |
| 1 | AUTO | R/W | 0 | Nach erreichtem Vergleichswert ungleich null beim nächsten Zählintervall auf null zurücksetzen |
| 2 | INTEN | R/W | 0 | IRQ beim Hochzählen auf COMPARE erzeugen |
| 15:3 | Reserviert | R/ignoriertes W | 0 | Lesen immer null |

CSR wird ausschließlich durch Software geändert. Im Einmalbetrieb bleibt COUNT
auf COMPARE stehen; ENABLE bleibt gesetzt. Ein gültiger Registerschreibzugriff
hat Vorrang vor Zählen und IRQ-Erzeugung. Timerlesezugriffe haben keine
Nebenwirkungen. Es gibt kein Timer-Pending- oder Quittierungsregister.

Der IRQ dauert einen Systemtakt. Automatisches Rücksetzen und Software-Schreiben
erzeugen keinen IRQ. Im Automatikbetrieb beträgt die Periode
`(COMPARE + 1) * TIMER_DIVISOR / CLK_HZ`; bei COUNT=COMPARE=0 bleibt der Zähler
auf null. `TIMER_DIVISOR` ist ein Syntheseparameter, kein Register: Standard
50000, beim Olimex-Wrapper 25000 für 1 ms bei 25 MHz.
Details: [Timer-MMIO](timer_mmio.md), [Timer-Verhalten](../../timer/README.md).

### LEDs (`0xFFFD`, 8 Bit)

| Bit | Name | Zugriff | Reset | Bedeutung bei 1 |
|---|---|---|---|---|
| 0 | LED1 | R/W | 0 | LED1 eingeschaltet |
| 1 | LED2 | R/W | 0 | LED2 eingeschaltet |
| 7:2 | Reserviert | R/ignoriertes W | 0 | Lesen immer null |

### UART CSR (`0xFFFE`, 8 Bit)

| Bit | Name | Zugriff | Reset | Bedeutung bei 1 |
|---|---|---|---|---|
| 0 | RXAVAIL | R | 0 | Ungelesenes CPU-Empfangsbyte vorhanden |
| 1 | TXFREE | R | 1 | Pending-TX-Puffer frei; ein serieller Frame kann noch laufen |
| 2 | RXIE | R/W | 0 | IRQ bei jedem CPU-Empfang aktivieren |
| 3 | TXIE | R/W | 0 | IRQ beim Freiwerden des Pending-TX-Puffers aktivieren |
| 7:4 | Reserviert | R/ignoriertes W | 0 | Lesen immer null |

Ein CSR-Schreiben ersetzt nur RXIE/TXIE; es quittiert keine Statusbits.
CSR-Lesen verbraucht kein Empfangsbyte. DATA-Lesen liefert auch ohne RXAVAIL das
behaltene Byte; NUL ist gültige Eingabe. Ein neuer Empfang überschreibt den
Ein-Byte-RX-Puffer und gewinnt gegenüber gleichzeitigem Verbrauch.

RXIE/TXIE erzeugen Ereignisimpulse von einem Systemtakt. Freigeben meldet keine
vergangenen Ereignisse nach. TXIE signalisiert die Übernahme des gepufferten
Bytes durch den Sender, bevor dessen Frame abgeschlossen ist. Debug-Verkehr
erzeugt keine UART-IRQs. Es gibt kein zusätzliches UART-Pending-Register.
Details: [LED/UART-MMIO](uart_mmio.md),
[UART-Puffer und Handshake](../../debug_uart/docs/register_interface.md).

## Byte-, Wortzugriffe und Reset

- Bytezugriffe wählen genau ein Byte. Bei Timerregistern bleibt das andere
  Byte beim Schreiben erhalten. Unabhängige LED-/UART-Zugriffe sollten byteweise
  erfolgen (`c@`, `c!`); ausgerichtete Timerzugriffe wortweise (`@`, `!`).
- Ein Wort an A greift auf A und `(A+1) mod 65536` zu. BS=01 wählt A als
  unteres Datenbyte, BS=10 A+1 als oberes, BS=11 beide. Nicht gewählte Bytes
  haben keine Nebenwirkung.
- Ausgerichtete Timerwörter sind atomar. Wörter an `0xFFF1` und `0xFFF3`
  durchlaufen zwei Timerregister in zwei Phasen, kleinere Adresse zuerst;
  der erste Schreibeffekt erfolgt bereits vor dem abschließenden ACK.
- Ein Wort an `0xFFFC` kombiniert reserviert/LEDs, an `0xFFFD` LEDs/UART-CSR,
  an `0xFFFE` UART-CSR/DATA. Ein Wortlesen an `0xFFFE` verbraucht RX und liefert
  den CSR-Wert vor diesem Verbrauch.
- Ein Wort an `0xFFFF` kombiniert UART-DATA mit SRAM an `0x0000`.
  Gemischte SRAM/MMIO-Zugriffe erledigen die SRAM-Seite zuerst.
  LED-/UART-Nebenwirkungen erfolgen einmalig beim abschließenden ACK.
- Systemreset setzt CPU, Timer, LEDs und UART zurück. CPU-only RESET-HALT
  setzt die CPU zurück und hält sie an; Timer, LEDs, UART-Puffer und UART-
  Interruptfreigaben bleiben erhalten. HALT und STEP pausieren den Timer nicht.

## CPU-Register ohne MMIO-Adresse

Prim ist eine Stack-CPU. Diese Register liegen innerhalb der
[`CPU`](../../cpu/rtl/prim.v) und belegen keine zusätzlichen Speicheradressen.
Die Resetwerte gelten für Systemreset und CPU-only Debug-Reset.

| Register / RTL-Name | Breite | Reset | Funktion / Zugriff |
|---|---|---|---|
| PC / `r_pc` | 16 Bit | `0x0000` | Programmzähler; durch Kontrollfluss verändert, als `o_pc` am Debug-Interface verfügbar |
| T, N | Je 16 Bit | `0x0000` | Zwischengespeicherte oberste zwei Datenstackzellen; durch Stackoperationen verändert |
| DSP / `r_dsp` | DSS Bit, Standard 4 | 0 | Umlaufender Datenstackindex |
| RSP / `r_rsp` | RSS Bit, Standard 4 | 0 | Umlaufender Rücksprungstackindex |
| Datenstack / `r_dstack` | `2**DSS` × 16 Bit | Nicht zurückgesetzt | Standard 16 Zellen; T an DSP, N an DSP−1 |
| Rücksprungstack / `r_rstack` | `2**RSS` × 16 Bit | Nicht zurückgesetzt | Standard 16 Zellen; R ist die Zelle an RSP, kein separates Register |
| Carry / `r_carry` | 1 Bit | 0 | ADD, SUB und Schiebeoperationen ändern es; `CARRY` legt 0 oder 1 auf den Datenstack |
| ISR-Adresse / `r_int_addr` | 16 Bit | `0x0000` | `<addr> INTAD` übernimmt die oberste Stackzelle; Ziel von Hardware-IRQ und Software-INT |
| Interruptfreigabe / `r_int_enable` | 1 Bit | 0 | `INTEI` setzt, `INTDI` löscht die globale Hardware-Interruptfreigabe |
| IRQ-Pending / `r_irq_pending` | 1 Bit | 0 | Sammelt zusammengefasste IRQ-Anfragen auch bei Maskierung/HALT; bei Annahme verbraucht, kein direkter Softwarezugriff |

Die Stackindizes laufen ohne Über-/Unterlaufprüfung um. Unbenutzte Stackzellen
sind nach Reset undefiniert. Interrupt-Eintritt sichert den PC auf dem
Rücksprungstack; Carry, Datenstack und globale Interruptfreigabe bleiben erhalten.
Timer- und UART-IRQ sind per ODER mit dem CPU-Eingang verbunden. Die CPU speichert
keine getrennte Herkunftskennung. Weitere Regeln und Opcodewerte stehen in der
[CPU-Interruptreferenz](../../cpu/README.md#interrupts).

Zur Ablaufsteuerung besitzt die CPU außerdem `r_ir` (8 Bit, Reset 0),
`r_mem_data` (16 Bit, Reset 0), `r_phase` (2 Bit, Reset FETCH), `stepping`
(1 Bit, Reset 0), `o_halted`, `o_break_reason` und `o_break_event` (je 1 Bit).
BREAK-Grund und -Ereignis werden beim Reset gelöscht. Systemreset startet
abhängig vom Parameter START_HALTED laufend oder angehalten; Debug-Reset hält
immer an. Diese Zustände haben keine MMIO-Adressen. Debug-Kommandos zur
Steuerung und Beobachtung sind im [Protokoll](../../docs/DRAFT.md) beschrieben.
Interne Bus-, SRAM- und UART-Protokollzustände sind Implementierungsdetails;
ihre RTL-Deklarationen sind keine weiteren Software-Register.
