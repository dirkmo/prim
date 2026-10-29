# 16-Bit-Timer

Eigenständiges, synthetisierbares Verilog-Modul in `rtl/timer.v`, ohne
Abhängigkeiten zum übrigen Repository. Es verwendet ausschließlich `i_clk`.
Die konkrete Prim-Systemanbindung ist separat unter
[`system/docs/timer_mmio.md`](../system/docs/timer_mmio.md) beschrieben.
Der Instanziierungsparameter `DIVISOR` (Default: 50_000) legt die Anzahl der
Systemtakte pro Zählfreigabe fest. Er muss eine positive Ganzzahl sein;
`DIVISOR=1` zählt bei jedem Systemtakt. Es gibt keine zusätzliche Clock-Domain.
Bei einer Systemtaktfrequenz `f_clk` gilt:

```text
Zählfrequenz = f_clk / DIVISOR
Zählintervall T = DIVISOR / f_clk
```

Beispiel: `timer #(.DIVISOR(12500)) my_timer (...)` zählt bei 12,5 MHz alle
1 ms, bei 25 MHz alle 0,5 ms. Der Faktor ist zur Synthese festgelegt und kein
Software-Register. Der Vorteiler benötigt nur `ceil(log2(DIVISOR))` Bits;
bei `DIVISOR=1` wird er durch die Synthese entfernt. Die Zeitgenauigkeit
entspricht der Genauigkeit der Taktquelle.

Das Modul speichert nur COUNT (16 Bit), COMPARE (16 Bit), CSR (3 Bit), den
Vorteiler und den IRQ-Ausgang. Eine beispielhafte Yosys-iCE40-Synthese mit
`DIVISOR=50000` ergibt 52 Flipflops, 162 LUT4 und 28 Carry-Zellen, ohne RAM oder DSP.
Das ist ein Syntheseergebnis, keine Platzierungs- oder Timingprüfung.
Reproduzierbarer Aufruf: `yosys -p 'read_verilog timer/rtl/timer.v; synth_ice40 -top timer; stat'`.

## Signale

| Signal | Richtung | Bedeutung |
|---|---|---|
| `i_clk` | Eingang | Systemtakt |
| `i_reset` | Eingang | Synchroner, aktiver High-Reset; setzt alle Register, Vorteiler und IRQ auf null |
| `i_cs` | Eingang | Modul ausgewählt |
| `i_we` | Eingang | Schreiben bei 1, Lesen bei 0 |
| `i_addr[1:0]` | Eingang | **Registerindex**, keine Byteadresse |
| `i_be[1:0]` | Eingang | Schreibfreigabe: Bit 0 für Bits 7:0, Bit 1 für Bits 15:8 |
| `i_wdata[15:0]` | Eingang | Schreibdaten |
| `o_rdata[15:0]` | Ausgang | Kombinatorische Lesedaten; null bei `i_cs=0` oder ungültigem Index |
| `o_irq` | Ausgang | Aktiver High-Interruptimpuls von einem Systemtakt |

Alle Eingänge müssen synchron zu `i_clk` sein. Schreiben erfolgt an jeder
steigenden Taktflanke mit `i_cs && i_we` und mindestens einem gesetzten
Byte-Enable. Für ein einzelnes Schreiben muss der Busadapter genau eine solche
Flanke erzeugen. Es gibt keine Wartezyklen und kein ACK-Signal. Lesen hat keine
Nebenwirkungen und liefert das vollständige Wort unabhängig von `i_be`/`i_we`.
Adressdekodierung, Basisadresse und Umsetzung eines CPU-Busprotokolls übernimmt
der Benutzer außerhalb des Moduls. Nicht ausgerichtete Zugriffe erfordern
ebenfalls einen externen Adapter.

## Software-Interface

| Registerindex | Üblicher Byteoffset | Register | Zugriff |
|---|---|---|---|
| 0 | `+0x00` | `COUNT`: aktueller Zählerstand, 16 Bit | R/W |
| 1 | `+0x02` | `COMPARE`: Vergleichswert, 16 Bit | R/W |
| 2 | `+0x04` | `CSR`: Steuerregister | R/W |
| 3 | — | Reserviert | Liest null, Schreiben ignoriert |

CSR: Bit 0 `ENABLE`, Bit 1 `AUTO`, Bit 2 `INTEN`. Bits 15:3 lesen null;
Schreiben dieser Bits wird ignoriert. Das Modul verändert CSR niemals selbst.
Ein ausgeschalteter Timer behält `COUNT` und `COMPARE` bei.

Bei jeder Zählfreigabe gilt:

| Bedingung | Neuer Zählerstand |
|---|---|
| `ENABLE=0` | unverändert |
| `ENABLE=1`, `COUNT!=COMPARE` | `COUNT+1`, mit 16-Bit-Überlauf |
| `ENABLE=1`, `COUNT==COMPARE==0` | null, unabhängig von `AUTO` |
| `ENABLE=1`, `COUNT==COMPARE!=0`, `AUTO=0` | unverändert |
| `ENABLE=1`, `COUNT==COMPARE!=0`, `AUTO=1` | null |

Es gibt keinen internen Stoppzustand. Schreibt Software einen abweichenden
Zähler- oder Vergleichswert, kann der aktivierte Timer wieder zählen.
Bei `COMPARE=0` und `COUNT>0` zählt er bis zum Überlauf weiter und bleibt
anschließend auf null stehen.

Bei `AUTO=1`, `COMPARE=3` ist die Folge `0, 1, 2, 3, 0, 1, …`.
Der Vergleichswert bleibt also ein volles Zählintervall sichtbar. Die periodische
Umlaufzeit beträgt `(COMPARE+1) * T`; vom Start bei null bis zum ersten Erreichen
des Vergleichswerts vergehen dagegen `COMPARE * T`. Die maximale Umlaufzeit
beträgt `65536 * T`.

## Priorität, Zeitbasis und Interrupt

Reset hat höchste Priorität. Danach hat ein gültiger Registerschreibzugriff
Vorrang vor Zählen und Interrupt; eine gleichzeitig anstehende Zählfreigabe
verfällt. Ungültiger Index oder `i_be=0` beeinflussen das Zählen nicht.

Solange `ENABLE=0` ist, wird der Vorteiler auf null gehalten. Nach Aktivierung
vergehen somit `DIVISOR` Systemtakte bis zum ersten Zählschritt. Auch ein
COUNT-Schreibzugriff, dessen resultierender 16-Bit-Wert null ist, setzt den
Vorteiler zurück. Andere Schreibzugriffe ändern seine Phase nicht. Bytezugriffe
erhalten das jeweils andere Byte; getrennte Bytezugriffe sind nicht atomar.
Zum sicheren Konfigurieren: `ENABLE=0`, `COMPARE` und `COUNT=0` schreiben,
danach CSR mit den gewünschten Steuerbits schreiben.

Ein Zählschritt, der `COUNT` auf `COMPARE` erhöht, erzeugt bei `INTEN=1` einen
IRQ-Impuls. Das gilt auch für den Überlauf von 65535 auf `COMPARE=0`.
Software-Schreibzugriffe, automatisches Rücksetzen auf null und Stehenbleiben
auf dem Vergleichswert erzeugen keinen Interrupt. Nachträgliches Setzen von
`INTEN` meldet keinen vergangenen Treffer. Lesen und Schreiben quittieren
keinen gespeicherten Interrupt: Es gibt kein Pending-Bit.

Ein nachgeschalteter Interruptcontroller muss den einzelnen Systemtaktimpuls
sicher erfassen. CPU-Halt oder CPU-Reset haben ohne Ansteuerung von `i_reset`
keine Wirkung auf den Timer.

## Tests

Benötigt werden Python 3 (nur Standardbibliothek), Icarus Verilog und `vvp`:

```sh
python3 timer/tests/test_timer.py
```

Der Test ist auch außerhalb dieses Repositorys ausführbar, wenn das komplette
Verzeichnis `timer/` kopiert wird. Toolpfade lassen sich über `--iverilog` und
`--vvp` angeben. Die Tests prüfen Register-/Bytezugriffe, Schreibpriorität,
Einmal-/Automatikbetrieb, Interrupts, Reset, Pause/Neustart, 16-Bit-Grenzen und
deterministische Zufallsfolgen. Die Teilung wird separat für kleine und große
Faktoren sowie Faktoren an Zweierpotenzgrenzen geprüft. Kleine Teilerfaktoren
beschleunigen die umfangreichen Verhaltenstests einschließlich des vollständigen
Überlaufs. Null und negative Teilerfaktoren werden als ungültig zurückgewiesen.
