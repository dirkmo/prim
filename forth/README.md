# Eigenständiges Forth für Prim

Stand AP 2: reproduzierbarer Kernel-Build und Kaltstart. **Noch kein
Forth-Interpreter, keine öffentlichen Wörter und keine UART-Konsole.**
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
| `kernel.map.json` | Symbole, Variablenadressen und Bereiche mit exklusiven Endadressen |
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

- HERE auf das erste freie, gerade Byte nach dem Kernel, LATEST auf null
  (noch keine Kernelwörter).
- BASE auf 10, STATE und logische Stacktiefe auf 0.
- Eingabe-, Parser-, Definitions- und Compilerzustand auf 0.
- Erstes Byte von Eingabe- und temporärem Stringpuffer auf 0.

Danach läuft `idle` als endlose JP-Schleife ohne CALL, BREAK, UART-Ausgabe oder
RX-Lesezugriff. Der spätere Interpreter ersetzt diese Schleife. Im AP-2-Image:
idle=0487, KERNEL_END=048B, USER_START=048C; die Speicherkarte ist bei späteren
Änderungen maßgeblich. Boot benötigt 69 Instruktionen, maximal 2 Datenstack-
zellen und 0 Returnstack-Einträge. Er hinterlässt beide Stacks logisch leer.

CPU-Reset startet erneut bei 0 und initialisiert HERE/LATEST neu. Boot selbst
löscht keine Bytes im Benutzerbereich und konsumiert kein vorhandenes UART-RX.

## Prüfung im Simulator

Schnelle Build- und Python-CPU-Prüfungen:

```sh
.venv/bin/python forth/tests/test_boot.py -v
```

Zusätzlich CPU mit physischem SRAM-Modell und UART-MMIO in Icarus:

```sh
.venv/bin/python forth/tests/test_boot.py --rtl -v
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

Weitere Prüfungen: bytegleiche Builds aus fremdem Arbeitsverzeichnis, lückenlose
Speicherkarte, Schutz des Emitters vor Überlappung/MMIO-Grenzüberschreitung,
undefinierte Symbole, Kaltstart auf bereits benutztem RAM, erhaltene Benutzer-
bytes und stabile Warteschleife ohne Stackwachstum. Keine Forth-Sprachtests
oder Hardwaretests in AP 2.
