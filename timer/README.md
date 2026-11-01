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

## Forth-Treiber

[`forth/timer.fs`](forth/timer.fs) ist im Standard-Dual-Image bereits enthalten.
Nur beim kleineren UART-only-Profil wird die Datei zeilenweise nachgeladen
(UART-Konsole: **Ctrl+U**, dann `timer/forth/timer.fs`). Der Treiber
belegt den Systemtimer exklusiv. Die Audio-Demos verwenden ebenfalls diesen
Treiber: `AUDIO-DEMO-TIMER` ruft `TIMER-INIT` auf, `AUDIO-MS` ruft `TIMER-WAIT`
auf. Zeitgesteuerte Audio-Demos benötigen daher freien Lauf und dürfen nicht
parallel zu einer anderen Timer-Konfiguration laufen. Beim Laden werden nur Wörter
definiert, keine Timerregister verändert. Die Zahlenbasis ist danach dezimal.

```forth
TIMER-INIT
1000 TIMER-WAIT
TIMER-COUNT@ U. CR
250 TIMER-ONCE
: WAIT-DONE BEGIN TIMER-DONE? UNTIL ;
WAIT-DONE
1000 TIMER-PERIOD
TIMER-STOP
```

| Wort | Stackeffekt | Funktion |
|---|---|---|
| `TIMER-INIT` | `( -- )` | COUNT=0, COMPARE=65535, AUTO und ENABLE setzen |
| `TIMER-COUNT@` / `TIMER-COUNT!` | `( -- u )` / `( u -- )` | COUNT atomar lesen/schreiben |
| `TIMER-COMPARE@` / `TIMER-COMPARE!` | `( -- u )` / `( u -- )` | COMPARE lesen/schreiben |
| `TIMER-RESET` | `( -- )` | COUNT und Vorteilerphase auf null setzen |
| `TIMER-STOP` / `TIMER-START` | `( -- )` | Stoppen/fortsetzen, AUTO erhalten, Timer-INTEN löschen |
| `TIMER-ONCE` | `( ticks -- )` | Einmal bis COUNT=ticks zählen; null ist sofort fertig |
| `TIMER-PERIOD` | `( ticks -- )` | AUTO mit Periode ticks; erlaubt 2..65535, sonst ABORT vor Registerzugriff |
| `TIMER-DONE?` | `( -- flag )` | Momentaufnahme COUNT=COMPARE, kein gespeichertes Ereignis |
| `TIMER-WAIT` | `( ticks -- )` | 0..65535 Ticks aktiv warten, benötigt freien Lauf nach TIMER-INIT |

Ein Tick dauert `TIMER_DIVISOR / CLK_HZ` Sekunden; auf dem Olimex-Board mit
25 MHz und Teiler 25000 ist das **1 ms**. Der Teiler ist nicht per Forth
einstellbar. [`forth/demo.fs`](forth/demo.fs) definiert dazu `TIMER-DEMO`.
Die Wartezeit wird ab der ersten COUNT-Abfrage gemessen; sie hat Tick-Auflösung
und zusätzlichen Interpreter-/Aufrufaufwand. `TIMER-WAIT` sammelt aufeinanderfolgende
COUNT-Differenzen über den 16-Bit-Überlauf hinweg; zwischen zwei Abfragen müssen
weniger als 65536 Ticks liegen. Es verändert keine Timerregister. Bei gestopptem
Timer oder einem anderen COMPARE-Wert ist diese Wartefunktion ungeeignet.

Im AUTO-Betrieb folgt der erste Vergleich nach `ticks-1` Ticks, weitere Vergleiche
jeweils nach `ticks` Ticks. COMPARE=0 bleibt bei COUNT=0 stehen; deshalb sind
Perioden von null oder einem Tick ausgeschlossen. `TIMER-DONE?` kann einen
Vergleich im AUTO-Modus verpassen. Es eignet sich vor allem für `TIMER-ONCE`.
`TIMER-START` setzt COUNT nicht zurück: einen fertigen Einmallauf mit
`TIMER-RESET` neu starten.

Der Basistreiber schaltet Timer-IRQs bei der Konfiguration aus. FFF4 wird
ausschließlich byteweise geschrieben; die Basiswörter lassen FFF5 unverändert.

### Konfigurierbarer Timer-Callback (Dual-Konsolenprofil)

Der IRQ-Kernel stellt `TIMER-CALLBACK! ( xt -- )` und `TIMER-POLL ( -- )`
bereit. Das Standard-Image enthält den Basistreiber und `TIMER-EVERY` aus
`timer/forth/callback.fs` bereits; manuelles Nachladen entfällt:

```forth
VARIABLE TICKS
: ON-TIMER 1 TICKS +! ;
100 ' ON-TIMER TIMER-EVERY
: WORK BEGIN TIMER-POLL TICKS @ 10 = UNTIL ;
WORK
0 TIMER-CALLBACK!
```

`TIMER-EVERY ( ticks xt -- )` deaktiviert die alte Registrierung, richtet eine
AUTO-Periode ein und registriert das neue Wort. Auf dem 25-MHz-Board entsprechen
100 Ticks 100 ms; der erste Vergleich erfolgt nach 99 Ticks. Alternativ erst
`TIMER-ONCE` oder `TIMER-PERIOD` konfigurieren, dann mit `' ON-TIMER
TIMER-CALLBACK!` den Callback und den Timer-IRQ aktivieren. XT=0 deaktiviert den
Timer-IRQ; RUN/AUTO und die anderen IRQ-Quellen bleiben erhalten. Registrierung
und Abmeldung löschen alte Software-Ereignisse und quittieren ausschließlich
das Timer-Bit in FFF5. Die API setzt normale Vordergrundausführung mit
freigegebenen CPU-IRQs voraus und kehrt mit freigegebenen CPU-IRQs zurück.

Der ISR quittiert Timer-Ereignisse und setzt ein Flag. `TIMER-POLL` nimmt das Flag
atomar ab und ruft das registrierte Wort **im Vordergrund mit freigegebenen IRQs**
auf. Es gibt keinen automatischen Aufruf während Konsolenleerlauf, `KEY` oder
`TIMER-WAIT`: Anwendungsschleifen müssen `TIMER-POLL` regelmäßig ausführen.
Mehrere IRQs vor einem Poll werden zusammengefasst; dies ist kein Tick-Zähler.
Während eines Callbacks eintreffende Ereignisse bleiben für den nächsten Poll
vorgemerkt. Rekursives `TIMER-POLL` führt keinen weiteren Callback aus.

Das Standard-Image enthält außerdem `MS ( u -- )`, implementiert in
`forth/ms.fs`. Nach `TIMER-INIT` oder `TIMER-EVERY` wartet es u Ticks (auf dem
25-MHz-Board Millisekunden) und ruft dabei `TIMER-POLL` auf. Anders als
`TIMER-WAIT` berücksichtigt es auch kürzere AUTO-Perioden. Der Timer muss bei
u>0 laufen, AUTO muss aktiv und COMPARE ungleich null sein; sonst erfolgt ABORT.
`0 MS` kehrt sofort zurück. Register und Periodenkonfiguration bleiben erhalten.
Zwischen zwei COUNT-Abfragen, einschließlich Callback-Laufzeit, müssen weniger
als COMPARE+1 Ticks liegen; übersehene Umläufe können die Wartezeit verlängern.
Callbacks dürfen den Timer während MS nicht umkonfigurieren.

Das Callback-Wort hat den Stackeffekt `( -- )`, erhält vorhandene Stackwerte
und muss genügend Platz für Kernel und ISR lassen. Es darf sich selbst abmelden
oder ersetzen. Vor `FORGET` eines registrierten Wortes den Callback abmelden.
`ABORT` und Fehler brechen den Callback ab und löschen die Registrierung beim
Neustart der Konsole. Die Basiswörter `TIMER-START`, `TIMER-STOP`, `TIMER-INIT`,
`TIMER-ONCE` und `TIMER-PERIOD` maskieren weiterhin den Timer-IRQ; nach erneuter
Konfiguration bei Bedarf den Callback erneut registrieren.

Ohne Registrierung maskiert der Timer-Handler unerwartete Timer-IRQs weiterhin
und setzt das Diagnosebit. Der ISR beginnt mit INTDI und endet mit INTEI.RET;
verschachtelte ISR sind ausgeschlossen. Das UART-only-Pollingprofil enthält
die Callback-Wörter nicht; dort nur den Basistreiber laden.

`forth/run.py` simuliert keinen Timer: dort kann der Treiber geladen werden,
zeitabhängige Aufrufe benötigen jedoch Hardware oder ein passendes Testmodell.

## Tests

Benötigt werden Python 3 (nur Standardbibliothek), Icarus Verilog und `vvp`:

```sh
python3 timer/tests/test_timer.py
python3 forth/tests/test_timer.py -v
```

Der zweite Aufruf prüft den Forth-Treiber im CPU-Modell: Laden in beiden
Konsolenprofilen, Registerzugriffe, Grenzwerte und Wartezeiten mit vorgegebenen
COUNT-Abfragen einschließlich Überlauf. Er prüft keine FPGA-Zeitgenauigkeit.
Diese Prüfungen sind auch in `python3 forth/test.py` enthalten.

Der RTL-Test ist auch außerhalb dieses Repositorys ausführbar, wenn das komplette
Verzeichnis `timer/` kopiert wird. Toolpfade lassen sich über `--iverilog` und
`--vvp` angeben. Die Tests prüfen Register-/Bytezugriffe, Schreibpriorität,
Einmal-/Automatikbetrieb, Interrupts, Reset, Pause/Neustart, 16-Bit-Grenzen und
deterministische Zufallsfolgen. Die Teilung wird separat für kleine und große
Faktoren sowie Faktoren an Zweierpotenzgrenzen geprüft. Kleine Teilerfaktoren
beschleunigen die umfangreichen Verhaltenstests einschließlich des vollständigen
Überlaufs. Null und negative Teilerfaktoren werden als ungültig zurückgewiesen.
