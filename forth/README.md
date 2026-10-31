# Eigenständiges Forth für Prim

Stand AP 3: reproduzierbarer Kernel-Build, Kaltstart und 50 aufrufbare
Forth-Grundwörter mit Stackprüfungen. **Noch kein Textinterpreter oder
Laufzeitcompiler und keine interaktive UART-Konsole.**
Architektur: [ARCHITECTURE.md](ARCHITECTURE.md), Übergabe: [STATUS.md](STATUS.md).

## Build

Vom Projekt-Root mit Python 3.11 oder neuer:

```sh
.venv/bin/python forth/build.py
```

Es ist keine Installation des Python-Pakets und keine TokenForth-Kompilation
erforderlich. Das Skript findet die lokalen Prim-Module selbst. Alternativ
`python3` verwenden. Andere Arbeitsverzeichnisse sind mit absolutem Skriptpfad
unterstützt. Ein abweichendes Ausgabeziel wird mit `--output /pfad/zum/ziel`
angegeben; relative Ausgabeziele beziehen sich auf das aktuelle Verzeichnis.

Standardmäßig entstehen unter `build/forth/`:

| Datei | Inhalt |
| --- | --- |
| `kernel.bin` | Rohes SRAM-Image für 0000..FFEF, exakt 65520 Bytes, Einstieg bei 0 |
| `kernel.map.json` | Symbole, Variablen, Bereiche und Wörter mit XT, Header und Stackeffekt |
| `kernel.disasm` | Disassembly der erzeugten Instruktionen mit Codelabels |

Reservierte und unbenutzte RAM-Bytes sind im Image null. Keine MMIO-Bytes im
Image; keine TokenForth-TOML-Datei oder vorverarbeitete Tokenfolge. Die Ausgabe
enthält keine Zeitstempel oder absoluten Buildpfade und ist byteweise
reproduzierbar. Buildartefakte bleiben im ohnehin ignorierten build-Verzeichnis.

Das Image ist ab Adresse 0 zu laden; es benötigt die bestehende Prim-CPU und
Systemspeicherkarte, kein geändertes FPGA-Bitstream. Diese AP hat keine
Board-Übertragung oder Hardwareprüfung vorgenommen. Ein erneutes Laden des
vollständigen Images überschreibt auch den Benutzerspeicher.

## Bootverhalten

Ein JP ab 0000 startet `cold_start` bei 0400. Der Kernel maskiert CPU-Interrupts,
löscht die UART-Interruptfreigaben per Bytezugriff und initialisiert seine
Verwaltungszellen unabhängig vom bisherigen SRAM-Inhalt:

- HERE auf das erste freie, gerade Byte nach dem Kernel, LATEST auf den
  neuesten der 50 Kernelheader.
- BASE auf 10, STATE und logische Stacktiefe auf 0.
- Eingabe-, Parser-, Definitions- und Compilerzustand auf 0.
- Erstes Byte von Eingabe- und temporärem Stringpuffer auf 0.

Danach läuft `idle` als endlose JP-Schleife ohne CALL, BREAK, UART-Ausgabe oder
RX-Lesezugriff. Der spätere Interpreter ersetzt diese Schleife. Die generierte
Speicherkarte enthält die jeweils aktuellen Adressen. Boot benötigt ab AP 3
72 Instruktionen, maximal 2 Datenstack-
zellen und 0 Returnstack-Einträge. Er hinterlässt beide Stacks logisch leer.

CPU-Reset startet erneut bei 0 und initialisiert HERE/LATEST neu. Boot selbst
löscht keine Bytes im Benutzerbereich und konsumiert kein vorhandenes UART-RX.

## Prüfung im Simulator

Schnelle Build- und Python-CPU-Prüfungen:

```sh
.venv/bin/python forth/tests/test_boot.py -v
.venv/bin/python forth/tests/test_primitives.py -v
```

Zusätzlich CPU mit physischem SRAM-Modell und UART-MMIO in Icarus:

```sh
.venv/bin/python forth/tests/test_boot.py --rtl -v
.venv/bin/python forth/tests/test_primitives.py --rtl -v
```

Dafür müssen `iverilog` und `vvp` im PATH stehen. Vorhandene Helfer aus
`tests/support/` werden unverändert wiederverwendet. Der Test baut seine
Simulatoren selbst in einem temporären Verzeichnis; kein vorheriger CMake-
Build erforderlich. Drei SRAM-Konfigurationen werden geprüft: Read/Write-
Zyklen und SRAM-Verzögerung 1/1/3 ns, 2/2/12 ns und 3/4/19 ns.

Der Produktionskernel hält absichtlich nicht an. Nur die Testkopie ersetzt
die erste Instruktion bei idle durch BREAK. Der Bootcode bis dorthin bleibt
unverändert. Die RTL-Prüfung vergleicht jede abgeschlossene Instruktion mit
dem Python-Modell sowie die Initialisierungswrites mit unabhängig festgelegten
Sollwerten. RAM-Verwaltungsbereiche werden vorher mit A5 vergiftet.

Weitere Bootprüfungen: bytegleiche Builds aus fremdem Arbeitsverzeichnis, lückenlose
Speicherkarte, Schutz des Emitters vor Überlappung/MMIO-Grenzüberschreitung,
undefinierte Symbole, Kaltstart auf bereits benutztem RAM, erhaltene Benutzer-
bytes und stabile Warteschleife ohne Stackwachstum. Kein Test auf echter Hardware.

## Grundwörter (AP 3)

Die folgende Liste ist implementiert; die spätere Namenssuche ist noch AP 5.
Wörter werden derzeit in Prim-Testprogrammen über die XT aus der Speicherkarte
aufgerufen. Die Tests legen Literale auf den Hardwarestack, setzen die private
DEPTH-Zelle passend und erzeugen `PUSH16 xt; CALL`. Das ist ein Testaufbau,
kein hostseitiger Forth-Interpreter. Der Produktionskernel wartet weiterhin.

```text
DUP DROP SWAP OVER ROT -ROT NIP 2DUP 2DROP
+ - * / MOD /MOD 1+ 1- NEGATE ABS 2* 2/
AND OR XOR INVERT LSHIFT RSHIFT
= <> < > U< 0= 0< 0<> MIN MAX TRUE FALSE
@ ! C@ C! +! CELL+ CELLS KEY EMIT CR SPACE
```

Jedes Wort besitzt einen verketteten Header gemäß ARCHITECTURE.md und eine
aufrufbare, geprüfte Implementierung. Noch keine Inline-Kompilierklasse;
deren gleichwertige Stackprüfungen gehören in AP 6. Grundwörter prüfen ihren
minimalen Bedarf und bei Wachstum die Grenze von acht Benutzerzellen, bevor
sie Benutzerdaten verändern. Interne Operationen zählen nicht zu DEPTH.

Multiplikation arbeitet in Software per Schieben/Addieren. Division verwendet
eine gemeinsame private Software-Routine mit 16 Divisionsschritten. /MOD
liefert Rest, dann Quotient; Quotient gegen null gerundet, Rest mit Vorzeichen
des Dividenden. Beispiel: -7 3 /MOD ergibt -1 -2. / und MOD verwenden dieselbe
Routine. 2/ ist arithmetisch, RSHIFT logisch, gültige Schiebeweiten 0..15.
Alle übrigen Rechenkonventionen stehen in ARCHITECTURE.md.

KEY prüft ausschließlich RXAVAIL (CSR-Bit 0), wartet bei fehlendem Zeichen
und konsumiert anschließend genau einmal DATA. NUL ist ein gültiges Zeichen.
EMIT nutzt einen Byte-Schreibzugriff; bei vollem TX-Puffer wartet die CPU auf
Bus-ACK. CR gibt CRLF aus, SPACE ein Leerzeichen. Keine Interrupts erforderlich.

Fehler erzeugen `error: <Grund>` und CRLF. Die private Zelle last_error an
0126 hält den Fehlercode (0 nach Kaltstart, nach erfolgreichem Wort unverändert):
1 Stack-Unterlauf, 2 Stack-Überlauf, 3 ungültige Schiebeweite, 4 Division durch
null, 5 -32768/-1. Danach werden DEPTH, STATE, Kontrollstacktiefe und offener
Definitionszustand logisch gelöscht; JP über error_exit nach idle verwirft
Aufrufrahmen, ohne durch sie zurückzukehren. HERE/LATEST bleiben erhalten.
Zeilenbehandlung und Transaktionsrollback folgen erst mit Interpreter/Compiler.

### Nachgewiesene Grenzen und Prüfungen

- Python-Tests prüfen alle 50 Wörter, Rechengrenzen und reproduzierbare
  Zufallswerte gegen unabhängige Sollwerte. Unterlauf wird für jede zu kleine
  Eingabetiefe jedes Wortes geprüft, Überlauf für alle wachsenden Wörter.
- Eine zusätzliche strukturelle Kontrollflussprüfung untersucht beide Seiten
  aller bedingten Sprünge, Schleifen, Hilfsaufrufe und Fehlerausgänge für alle
  zulässigen Eingabetiefen. Ergebnis: maximal zehn physische Datenstackzellen,
  davon höchstens zwei zusätzlich zur Eingabetiefe, und zwei lebende
  Rücksprungadressen einschließlich des Wortaufrufs. Damit bleibt die geplante
  Reserve von acht temporären Zellen eingehalten. Das Budget gilt für AP 3;
  spätere Interpreter-/Compileraufrufe müssen dazugezählt werden.
- Neun repräsentative Programme laufen in drei SRAM-Timingkonfigurationen
  mit instruktionsweisem Python/RTL-Vergleich, erwarteten Stackwerten und
  echter serieller TX-Dekodierung: 27 Vergleiche, einschließlich Fehlerausgaben.
- Ein zusätzlicher gerichteter RTL-Test führt KEY mit realen uart_buffers
  und verzögertem Bus-ACK aus. TXFREE ist bereits gesetzt, RXAVAIL bleibt
  zunächst null; nach mehreren Polls kommt NUL. Geprüft werden einmaliger
  Verbrauch, gelöschtes RXAVAIL, Rückkehr und korrekte DEPTH. Dieser Test
  speist Bytes am Eingang der UART-Puffer ein, nicht über eine serielle RX-Leitung.

Arithmetik belegt exklusiv Scratch 0380..038D: a, b, q, rem, count, qsign,
rsign (je eine Zelle). Sie ist bei deaktivierten Interrupts nicht reentrant.
Spätere Anzeige-/Konvertierungsroutinen dürfen dort keine Werte halten, die
einen Arithmetikaufruf überleben müssen. Scratch ab 038E bleibt frei.
