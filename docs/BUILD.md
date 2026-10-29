# Projektabläufe mit Make

Das Makefile im Projekt-Root bündelt Compiler, Simulation, FPGA-Build und
UART-Host. Es delegiert an `src/Makefile`, CMake und das vorhandene Hostskript.
Alle folgenden Aufrufe erfolgen im Projekt-Root. `make` und `make help` zeigen
die verfügbaren Targets, ohne etwas zu bauen oder Hardware anzusprechen.

## Einrichtung und Einstellungen

```sh
make setup
make check-tools
cp config.local.mk.example config.local.mk
```

`setup` führt `setup.sh` aus und installiert zusätzlich `pyserial` in `.venv`.
Standardmäßig verwenden die Targets `.venv/bin/python`; Aktivieren der Umgebung
ist nicht erforderlich. Ein anderes installiertes Environment lässt sich mit
`PYTHON=/pfad/zum/python` auswählen. `SYSTEM_PYTHON` (Standard `python3`) wird
für die Hilfsfunktionen zur Werkzeugprüfung, Ressourcenanzeige und Bereinigung
verwendet. `check-tools` prüft Python-Pakete sowie Compiler-, Simulations- und
FPGA-Werkzeuge. Die Systemwerkzeuge müssen bereits installiert sein.

In der nicht versionierten `config.local.mk` können etwa `PORT`, `PROGRAM`,
`JOBS`, `TIMEOUT` und die Programmiererauswahl stehen. Kommandozeilenwerte haben
Vorrang. `PORT` bezeichnet den separaten USB-UART-Adapter, vorzugsweise über
`/dev/serial/by-id/...`. `ICEPROG_DEVICE` und `ICEPROG_INTERFACE` (Standard `A`)
bezeichnen dagegen den UM-FT2232H-Programmer.

## Software und Simulation

```sh
make software
make image PROGRAM=src/examples/hello.cf
make asm ASM=cpu/tests/test.asm
make disasm IMAGE=build/software/test.asm.bin
make sim
make test
```

`software` baut alle bisherigen Ausgaben von `src/Makefile` nach `build/src`;
`base` baut nur die Basisbibliothek einschließlich ihrer Voraussetzungen.
`image` baut die Basisbibliothek und übersetzt `PROGRAM` über Tokenisierung und
Kompilierung in ein vollständiges 64-KiB-Speicherabbild. Standardprogramm ist
`src/examples/hello.cf`. Ausgaben liegen unter `build/software/<name>` mit den
Endungen `.tok.toml`, `.tf.toml` und `.bin`. Das Programm muss seinen Reset-Einstieg
selbst setzen, beispielsweise mit `[ 'main boot! ]`.

`asm` erzeugt standardmäßig `build/software/<name>.asm.bin`; `ASM_IMAGE` wählt
einen anderen Ausgabepfad. **`IMAGE` wählt eine vorhandene Eingabedatei für
`upload` und `disasm`**, nicht den Ausgabepfad von `image`.

`sim` baut den eigenständigen CPU-Simulator unter `build/sim`.
`test-python` prüft die Python-Komponenten und Makefile-Abläufe; `test-rtl` baut
den Simulator und führt alle CTest-Suites aus. `test` führt beide Targets aus.
`make test-rtl TEST_ARGS='-R debug_uart --verbose'` filtert die CTest-Auswahl.
`test-makefile` prüft gezielt die neuen Abläufe in temporären Projektkopien;
Programmer und UART werden dabei durch Testprogramme ersetzt.

## FPGA

```sh
make bitstream
make resources
make flash
```

Unterstützt wird `BOARD=olimex_ice40hx8k_evb` (Standard, Rev.B). `bitstream`
konfiguriert und baut das vorhandene CMake-Target `fpga_bitstream`, einschließlich
Timingprüfung. Die Ausgabe ist `build/olimex_ice40hx8k_evb/prim.bin`.
`resources` baut bei Bedarf und zeigt Ressourcenbelegung und Timing aus
`prim.json` und `timing.json`. LUTs, Flipflops und Carry-Zellen sind Bestandteile
der Logic Cells; die Zahlen dürfen nicht addiert werden.

**`flash` programmiert die Hardware:** Es baut bei Bedarf und ruft
`fpga_program` auf, das mit `iceprog -b` den SPI-Konfigurationsflash löscht,
beschreibt und verifiziert. `make all` baut Software, Programmabbild und Bitstream;
es programmiert nichts. Details zu Pins, PLL und Programmer stehen in der
[Board-Dokumentation](../boards/olimex_ice40hx8k_evb/README.md).

## UART und CPU-Steuerung

```sh
make status PORT=/dev/serial/by-id/your-uart-adapter
make halt
make pc
make step
make reset-halt
make run
make uart-status
make sram-check
```

Die verkürzten Aufrufe setzen `PORT` in `config.local.mk` oder als
Umgebungsvariable voraus. `stop` ist ein Alias für `halt`. Es gelten die
Voraussetzungen des Hostskripts: `step` und `pc` verlangen bestätigten Halt.
`TIMEOUT` setzt den Host-Timeout in Sekunden (Standard 2).

```sh
make upload IMAGE=build/software/test.asm.bin
make load-run PROGRAM=src/examples/hello.cf SKIP_UART_MMIO=1
make uart-console
make console-help
```

`upload` lädt ein **vorhandenes** binäres CPU-Abbild nach
RESET-HALT und lässt die CPU angehalten. Es kompiliert und flasht nichts.
`load-run` baut zuerst das durch `PROGRAM` gewählte Abbild, lädt es und startet
die CPU erst bei Erfolg. Hier wird `IMAGE` nicht verwendet.

Der Loader sendet im dauerhaften 16-Bit-Modus fortlaufend, ohne zwischen Wörtern
auf OK zu warten. Ein paralleler Empfänger zählt die Bestätigungen. Ein einzelnes
Restbyte wird als Byte geschrieben. Rücklesen ist standardmäßig ausgeschaltet.
`VERIFY=1` aktiviert die Prüfung für `upload` und `load-run`; direkt in der Konsole
lautet die Option `--verify`, beispielsweise:

```text
load build/software/hello.bin --skip-uart-mmio --verify --run
```

Die Prüfung liest Wörter über den automatisch erhöhten Pointer und gegebenenfalls
ein Restbyte. Bei einem Prüfungsfehler wird die CPU nicht gestartet.

Bei fehlenden oder falschen Bestätigungen meldet der Loader einen Fehler und
startet weder automatisch erneut noch die CPU. Nach einem Streamingfehler die
Konsole neu öffnen und das gesamte Abbild manuell erneut laden. Mit
`--write-delay 0.001` in der Konsole beziehungsweise `WRITE_DELAY=0.001` bei Make
lassen sich 1 ms Pause nach jedem gesendeten Wort einfügen (Standard 0).
Die Bestätigungszahl ersetzt keine Inhaltsprüfung; dafür dient `--verify`.

Compilerabbilder umfassen auch die MMIO-Adressen `FFFE` und `FFFF`. Dafür ist
`SKIP_UART_MMIO=1` ausdrücklich erforderlich: Der Loader überspringt und meldet
diese Adressen. Ohne diese Einstellung lehnt er solche Abbilder vor dem Öffnen
der Verbindung ab. Kleine Binärdateien bis 65534 Bytes benötigen sie nicht.

`uart-console` hält eine Verbindung für CPU-Daten und Debug-Kommandos offen.
Ctrl+B öffnet den lokalen Debug-Prompt, Ctrl+D beendet die Konsole, Ctrl+V sendet
das nächste Zeichen wörtlich. `help` im Prompt und `make console-help` zeigen
alle Befehle und Tastenkürzel; letzteres benötigt keinen Port. Während die
Konsole läuft, werden Debug-Kommandos dort eingegeben, damit ein Prozess den
Port besitzt. CPU-Ausgabe und BREAK-Meldungen werden laufend empfangen.
Siehe auch die [Konsolenbeschreibung](../boards/olimex_ice40hx8k_evb/README.md#interactive-console-posix--arch-linux).

## Ausgabeverzeichnisse und Aufräumen

`JOBS` bestimmt die Parallelität der CMake-Builds (Standard 2).
`BUILD_DIR` ist standardmäßig `build`. Die Unterverzeichnisse sind separat
konfigurierbar: `SRC_BUILD_DIR`, `SOFTWARE_DIR`, `SIM_BUILD_DIR`, `FPGA_BUILD_DIR`.
Buildpfade sollten keine Leerzeichen enthalten.

`make clean` entfernt ausschließlich diese vier ausgewählten Buildverzeichnisse.
Quellen, `.venv`, lokale Einstellungen und andere Dateien unter `build` bleiben
erhalten. Zur Absicherung akzeptiert `clean` nur Unterverzeichnisse des
projektlokalen `build/`; externe Ausgabeverzeichnisse müssen selbst bereinigt
werden. Es führt keinen Hardwarezugriff aus.
