# Eigenständiges Forth für Prim – Arbeitsstand und Arbeitspakete

Stand: 31. Oktober 2026. Dieses Dokument dient als Übergabe an weitere Chats.

## Auftrag und aktueller Stand

Ein kleines, eigenständiges Forth unter `forth/` im Projekt-Root entwickeln.
Es verwendet normale Forth-Syntax und einen vollständig auf der Prim-CPU
laufenden Textinterpreter und Compiler. Standardkonformität ist kein Ziel.

**AP 1–4 sind abgeschlossen. Kernel-Build, Boot, 55 Wörter und private
CPU-Routinen für Eingabe/Parser/Zahlen sind implementiert; noch kein
Textinterpreter oder Laufzeitcompiler.** Der Nutzer hat zuletzt AP 3 committen
und das nächste AP beginnen lassen. AP-3-Commit: `1e77c88`; AP-4-Änderungen
liegen noch uncommittet vor. AP 5 wurde nicht begonnen.
Die konkrete Architektur steht in [ARCHITECTURE.md](ARCHITECTURE.md).

AP 5–10 sind offen. Dieses Dokument bei späterer Arbeit knapp aktuell halten:
Entscheidungen, betroffene Dateien, Prüfungen und nächste Schritte festhalten.

## Verbindliche Leitplanken aus dem Gespräch

- Bestehendes TokenForth ist eine andere Sprache, kein klassisches Forth.
  Die neue Implementierung bleibt eigenständig; TokenForth nicht umbauen.
- Eingabe ist gewöhnlicher Forth-Quelltext über UART. Keine Tokenisierung
  oder Namensauflösung durch den Host im laufenden Betrieb voraussetzen.
- Interpretation und das Kompilieren neuer Definitionen laufen auf der CPU.
- Die CPU ist bewusst minimal. Mit der bestehenden ISA planen, keine neuen
  Opcodes voraussetzen. Multiplikation, Division und variable Schiebeweiten
  zunächst in Software implementieren; keine iterativen Hardware-Rechenwerke.
- Allenfalls sehr kleine Hardwareergänzungen später separat untersuchen:
  arithmetisches Rechtsschieben um eins, Carry-Addition, Schieben durch Carry
  oder Nullvergleich. Keine davon ist beschlossen. Vor einer Empfehlung
  zusätzliche Ressourcen durch einen Synthesevergleich bestimmen.
- Stackvergrößerungen sind ebenfalls nicht beschlossen.

Beispiel der gewünschten Bedienung:

```forth
2 3 + .
: quadrat dup * ;
7 quadrat .
: betrag dup 0< if negate then ;
```

## Technische Ausgangslage und Architekturvorschlag

Aus dem bestehenden Repository geprüft:

- Prim: 16-Bit-Daten und -Adressen, byteadressierter Speicher, 8-Bit-Opcodes.
- Byte-/Wortzugriffe, indirekte CALL/JP/JZ, Daten- und Returnstack vorhanden.
- Addition, Subtraktion, signed/unsigned Kleinervergleich, Bitoperationen,
  logische Schiebeoperationen um 1 und 8 Bit und Carry-/Borrow-Abfrage vorhanden.
- Multiplikation und Division fehlen als Opcodes. Logisches SR ersetzt nicht
  das arithmetische Rechtsschieben für Forth `2/` bei negativen Zahlen.
- Standardmäßig je 16 Stackzellen (`DSS=4`, `RSS=4`), zyklische Zeiger,
  keine Hardwareprüfung auf Stacküberlauf. Returnstack wird auch für Aufrufe
  und Interrupts verwendet; dies bei Compiler und Schleifen berücksichtigen.
- Code liegt im beschreibbaren Speicher; CPU kann neue Definitionen erzeugen.
- UART: CSR an 0xFFFE, Daten an 0xFFFF. FPGA-CPU-Ausgabe ist auf sieben Bit
  beschränkt. Statusbits und Zugriffseffekte vor Implementierung nachlesen.
- System-MMIO liegt an 0xFFF0..0xFFFF; nicht als Wörterbuchspeicher verwenden.

In AP 1 festgelegte Architektur (Details im Architekturdokument):

- Subroutine-Threaded Code: Aufrufe als `PUSH16 adresse; CALL`, geeignete
  Primitive direkt als Opcode; Definitionsende mit Return-Semantik der CPU.
- Eigenes verkettetes Wörterbuch mit Name, Flags (u. a. Immediate), vorherigem
  Eintrag und Ausführungsadresse; 8-Byte-Header plus ASCII-Name, Suche ohne
  Unterscheidung von Groß-/Kleinschreibung.
- Äußerer Interpreter: Wort lesen, suchen, ausführen/kompilieren oder Zahl
  erkennen. Immediate-Wörter auch im Kompiliermodus ausführen.
- Ein Buildwerkzeug darf das initiale Kernel-Image erzeugen. Danach braucht
  der laufende Interpreter keinen Hostcompiler.
- Fehler führen zurück zur Konsole. Unvollständige Definitionen verwerfen;
  abgeschlossene Wörter bleiben erhalten.
- Native Datenstacks mit softwaregeprüfter Benutzergrenze von 8 Zellen und
  8 temporären Kernelzellen. Hardware-Returnstack bleibt bei 16 Zellen ohne
  allgemeinen Überlaufschutz. Kernelbudgets in folgenden APs verifizieren.
- Speicher: Boot/Variablen/Puffer unter 0400, Kernel ab 0400, Benutzerbereich
  hinter dem Kernel bis exklusiv F000. Kein öffentliches >R/R>/R@ in Version 1.
- Return-Bit-Folding und Tail-CALL→JP in AP 6 konservativ implementieren.

Wichtige vorhandene Referenzen (keine fertige Forth-Implementierung):

| Pfad | Zweck |
| --- | --- |
| `cpu/rtl/prim.v` | Tatsächliche CPU-, ALU-, Stack- und Return-Semantik |
| `src/prim/isa.py` | Opcodewerte |
| `src/prim/assembler.py` | Vorhandener Prim-Assembler |
| `cpu/README.md` | CPU, Debugsteuerung, Interrupts |
| `system/docs/registers.md` | Registerübersicht |
| `system/docs/uart_mmio.md` | UART-Vertrag |
| `system/README.md` | System und Simulationsinfrastruktur |
| `tests/support/` | Wiederverwendbare Simulationshilfen |
| `src/prim/cpu.py` | Python-Instruktionsmodell |
| `src/interpreter.cf` | Unfertiger TokenForth-Tokeninterpreter, kein Text-Forth |
| `src/base.cf`, `src/bootstrap.cf` | TokenForth-Codegeneratoren, keine unverändert übernehmbare klassische Forth-Basis |

## Arbeitspakete

### AP 1 – Architektur und Sprachumfang

Status: abgeschlossen (31. Oktober 2026). Abhängigkeiten: keine.

Speicheraufteilung, Boot, Wörterbuchformat, Stackkonventionen und Grenzen,
Ausführungsmodell sowie unterstützte Syntax dokumentieren. Zahlenbereiche,
Vorzeichen-/Divisionssemantik, Namensvergleich und Fehlerverhalten festlegen.
Den unten geplanten Wortschatz auf einen sinnvollen ersten Umfang eingrenzen.

Ergebnis: [ARCHITECTURE.md](ARCHITECTURE.md) legt Speicher, Header, Stacks,
Interpreter, Zahlen-/Divisionssemantik, Wortumfang, Compilertransaktionen,
Return-Optimierungen und Fehlergrenzen als Grundlage für AP 2–8 fest.

### AP 2 – Kernel-Build und Boot

Status: abgeschlossen (31. Oktober 2026). Abhängigkeiten: AP 1.

Reproduzierbares initiales Kernel-Image erzeugen. Startadresse, Initialisierung
und Simulatoranbindung umsetzen. Bestehende Prim-Werkzeuge verwenden, soweit
sie ohne Abhängigkeit von TokenForth-Sprachsemantik geeignet sind.

Ergebnis: [build.py](build.py), [image.py](image.py) und
[kernel/boot.py](kernel/boot.py) erzeugen ein RAM-Image, Symbol-/Speicherkarte
und Instruktionsdisassembly. Boot initialisiert Kernelzustand und UART-
Interruptfreigaben; anschließend endlose JP-Warteschleife. Im damaligen
AP-2-Stand noch keine öffentlichen Forth-Wörter oder Header, kernel_latest=0;
durch AP 3 inzwischen erweitert (aktueller Stand unten).

Befehle und Simulatorverfahren: [README.md](README.md). Artefakte unter
build/forth/: kernel.bin (65520 Bytes, ohne MMIO), kernel.map.json,
kernel.disasm. Im AP-2-Stand idle=0487, KERNEL_END=048B, USER_START=048C.
Variablenzellen damals 0100..0125; aktuelle Adressen in kernel/boot.py und Map.
Alle übrigen in AP 1 reservierten Bereiche bleiben bestehen.

Validierung: ` .venv/bin/python forth/tests/test_boot.py --rtl -v `:
4 Tests erfolgreich; darin Bootvergleich in 3 SRAM-Timingkonfigurationen
mit UART-MMIO. Je 69 Instruktionen bis idle, maximal 2 Datenstackzellen,
keine Returnstack-Einträge. Reproduzierbarkeit, schmutziger RAM und erneuter
Kaltstart geprüft. Nur Testkopie erhält BREAK bei idle. Kein Boardtest.

### AP 3 – Grundwörter und UART

Status: abgeschlossen (31. Oktober 2026). Abhängigkeiten: AP 2.

Stackoperationen, Arithmetik, Vergleiche, Speicherzugriffe, `KEY`, `EMIT` und
`CR` bereitstellen. Fehlende Rechenoperationen in Software ergänzen, soweit
für die folgenden APs benötigt. Returnstackzugriffe mit Aufrufkonvention
abgleichen; vorhandene CPU-Mnemonics nicht blind als Forth-Wörter übernehmen.

Ergebnis: [kernel/primitives.py](kernel/primitives.py) erzeugt alle 50 Wörter
des AP-3-Zielumfangs mit Stackprüfungen, verketteten Headern und aufrufbaren XT.
Alle Header derzeit Kompilierklasse 0; gleichwertige Inline-Emitter folgen in
AP 6. Details und Wortliste: [README.md](README.md).

Software-Multiplikation und gemeinsame signed Division mit 16 Rechenschritten;
keine neuen CPU-Instruktionen. Private Fehlerausgänge geben den Grund über
UART aus, setzen logischen Stack-/Compilerzustand zurück und springen über
error_exit nach idle. Kein Zeilenhandling oder Definitionsrollback vorgezogen.

Im AP-3-Stand idle=048D, KERNEL_END=1131, USER_START=1132, kernel_latest=0C7C.
Variablen bis 0127; neue Zelle last_error an 0126. Arithmetik-Scratch exklusiv
0380..038D (a,b,q,rem,count,qsign,rsign), Rest ab 038E frei. Nicht reentrant.
Beim Weiterentwickeln sind generierte Map und Variablenzuordnung maßgeblich.

Validierung (alle erfolgreich):

```sh
.venv/bin/python forth/build.py
.venv/bin/python forth/tests/test_boot.py --rtl -v
.venv/bin/python forth/tests/test_primitives.py --rtl -v
```

4 Boottests und 9 Grundworttests. Darin 3 Boot- und 27 Grundwortvergleiche
CPU/SRAM/UART gegen Python sowie ein gerichteter KEY-Test mit uart_buffers,
verzögertem ACK und NUL-Empfang. Python prüft alle Wörter, Grenz-/Zufallswerte,
alle zu kleinen Eingabetiefen, alle wachsenden Wörter an der Stackgrenze,
Fehlerfälle und Wiederaufnahme nach Fehler. Echte Hardware nicht geprüft.

Strukturelle Stackprüfung aller Verzweigungen/Schleifen/Hilfsaufrufe bei
zulässigen Eingabetiefen: maximal 10 physische Datenzellen, höchstens 2
zusätzlich zur Eingabetiefe, maximal 2 Returnstack-Einträge einschließlich
Aufruf des öffentlichen Wortes. Dynamische Tests bestätigen diese Budgets.
Boot im AP-3-Stand 72 Instruktionen, maximal 2 Datenzellen und 0 Returnframes.
Spätere Interpreter-/Compilerframes müssen zusätzlich berücksichtigt werden.

### AP 4 – Texteingabe und Parser

Status: abgeschlossen (31. Oktober 2026). Abhängigkeiten: AP 3.

Zeilenpuffer, einfache Eingabekorrektur, Wortzerlegung, Kommentare und
Zahlenkonvertierung mit `BASE`, `DECIMAL` und `HEX` umsetzen.

Ergebnis: gewöhnlicher Forth-Text wird vollständig auf der CPU eingelesen
und in Wörter/Zahlen zerlegt; Puffergrenzen werden berücksichtigt.

[kernel/parser.py](kernel/parser.py): private read_line, parse_name,
parse_number, skip_line/skip_paren, raw_key/raw_emit und is_space.
Neue öffentliche Wörter BASE/DECIMAL/HEX und Immediate-Kommentare `\`/`(`.
Noch keine Konsolenschleife oder automatische Wortsuche/Ausführung.

read_line hat keinen Benutzerstackeffekt, Echo und BS/DEL-Korrektur,
127-Byte-Grenze, CR/LF/CRLF. Ungültige Steuerzeichen (außer TAB/VT/FF und
Editier-/EOL-Zeichen) und Überlänge werden bis EOL verworfen, dann Fehler.
parse_name konsumiert ein folgendes Trennzeichen und liefert token_addr/length;
Tokens bis 127 Bytes, Definitionen-Namensgrenze 31 erst in späteren APs.
Kommentare werden durch expliziten Aufruf ihrer Wörter verarbeitet.

parse_number erhält das aktuelle Token, bewahrt alle Benutzerwerte und liefert
number_status: 0 ungültig/kein Zahlentoken, 1 Erfolg, 2 Zahlenüberlauf.
number_value nur bei Status 1 gültig, sonst 0. Basis 2..36, +/-, Präfix $/#
nach Vorzeichen, positive 0..65535, negative Beträge bis 32768. Invalides BASE
ist Fehler; Syntax/Überlauf werden als Status zurückgegeben, damit AP 5 zuerst
im Wörterbuch suchen kann. Bounded repeated addition mit Carry-Prüfung, kein
Aufruf der öffentlichen Rechenwörter. Konvertierung nutzt eigene Variablen.

Neue Fehlercodes: 6 Eingabe zu lang, 7 offener Kommentar, 8 ungültige BASE,
9 Text-Steuerzeichen, 10 Zahlüberlauf (Ausgang für AP 5 vorbereitet).
Alle Fehlerausgänge löschen zusätzlich Eingabe-/Tokenmetadaten; skip_lf
bleibt für CRLF erhalten. Definitionstransaktionen weiterhin erst ab AP 6.

Aktuell idle=04DB, KERNEL_END=1A9D, USER_START=1A9E, kernel_latest=1A8E.
Variablen nun 0100..0141, neue Zellen ab 0128; number_status=013E,
number_value=0140. Kernel wächst, generierte Map ist maßgeblich.
Boot 111 Instruktionen, weiterhin 2 Datenzellen und kein Returnframe.

Validierung: Build sowie test_boot.py, test_primitives.py und test_parser.py
jeweils mit `--rtl -v` bestanden: 4+9+8 Testmethoden. Neue Prüfungen: alle
Zahlenbasen und Grenzwerte, Kommentare, Eingabekorrektur, Zeilenverwerfen und
Wiederaufnahme, 9 Parser-/Zahlenvergleiche mit physischem SRAM sowie gerichtete
CPU/UART-Puffer-Prüfung für zwei editierte Zeilen unter TX-Rückstau/ACK-Wartezeit.
Strukturelle Stackprüfung umfasst alle öffentlichen Wörter und die privaten
read_line/parse_name/parse_number: maximal 11 Datenzellen, höchstens 3 zusätzlich
zur Eingabetiefe und 2 Returnframes einschließlich Routineaufruf. Kein Boardtest.

### AP 5 – Wörterbuch und äußerer Interpreter

Status: offen. Abhängigkeiten: AP 4.

Namen auf der CPU suchen, Wörter ausführen, Zahlen auf den Stack legen und
unbekannte Eingaben behandeln. Interaktive Konsole mit `ok`, `.` und `.S`
bereitstellen. Fehlerbehandlung und Wiederaufnahme der Eingabe umsetzen.

Ergebnis: z. B. `2 3 + .` funktioniert ohne Hosttokenizer oder Hostcompiler.

### AP 6 – Compiler für neue Definitionen

Status: offen. Abhängigkeiten: AP 5.

`: name ... ;`, `STATE`, `IMMEDIATE`, `[`, `]`, `LITERAL`, `'` und `EXECUTE`
umsetzen. Aufrufe und Literale auf der CPU kompilieren. Unvollständige
Definitionen bei Fehlern verwerfen und Wörterbuch-/Speicherkollisionen abfangen.
Konservatives Return-Bit-Folding und Tail-Aufrufe per CALL→JP ergänzen;
Instruktionsgrenzen und gemeinsame Rücksprungziele erhalten.

Ergebnis: neue Definitionen lassen sich über UART eingeben und ausführen;
Interpretations- und Kompiliersemantik sind geprüft.

### AP 7 – Kontrollstrukturen

Status: offen. Abhängigkeiten: AP 6.

`IF ELSE THEN`, `BEGIN UNTIL`, `AGAIN` und `WHILE REPEAT` als Compilerwörter
implementieren. Fehlerhafte Verschachtelungen erkennen. Weitergehende
Schleifen wie `DO LOOP` sind bisher nicht Bestandteil des ersten Umfangs.

Ergebnis: bedingte und wiederholte Ausführung funktioniert auch verschachtelt.

### AP 8 – Datenwörter und Alltagswortschatz

Status: offen. Abhängigkeiten: AP 6; für manche Hilfswörter AP 7.

`HERE`, `ALLOT`, `,`, `C,`, `CREATE`, `VARIABLE`, `CONSTANT`, Stringausgabe
und benötigte Hilfswörter ergänzen. Interne Speicheremitter werden bereits in
AP 6 benötigt; hier ihre öffentliche Forth-Semantik vervollständigen.
Stringsyntax und Lebensdauer gemäß ARCHITECTURE.md umsetzen.

Ergebnis: kleine Programme mit veränderlichen Daten und Textausgabe möglich.

### AP 9 – Integration und Regressionstests

Status: offen. Begleitend ab AP 2; Abschluss nach AP 8.

Interaktive Eingaben und auf der CPU kompilierte Definitionen im Python-Modell
und in der RTL-Systemsimulation prüfen. UART, Compiler, Kontrollstrukturen,
Fehlerbehandlung und Speichergrenzen abdecken. Erwartete Ergebnisse unabhängig
festlegen; nicht nur Modell und RTL miteinander vergleichen.

Ergebnis: reproduzierbare Tests mit dokumentierten Befehlen und Ergebnissen.

### AP 10 – Anleitung und Beispiele

Status: offen. Begleitend; Abschluss nach AP 9.

Build-, Start- und Konsolenanleitung, Wortliste, Grenzen und kleine Beispiele
unter `forth/` ablegen. Dieses Übergabedokument auf den tatsächlichen Stand
bringen und nächste Schritte klar benennen.

Ergebnis: Nutzung und Weiterentwicklung ohne Kenntnis des ursprünglichen Chats.

## Letzte Prüfung und nächster Schritt

- AP 4 vollständig unter forth/ umgesetzt; CPU, TokenForth und bestehende
  Simulationshelfer unverändert. Alle oben genannten Tests bestanden.
- Nächster AP: AP 5, Wörterbuchsuche und äußerer Interpreter plus Ausgabe/
  Stackanzeige. Parser-ABI in README.md nutzen: read_line, dann parse_name,
  Suche vor parse_number. Kommentare haben Immediate-Flag. Roh-I/O raw_key/
  raw_emit verändert DEPTH nicht, öffentliche KEY/EMIT dagegen schon.
- Code und emit_word in kernel/primitives.py sind gemeinsame Codegeneratoren;
  Code.label verwendet einen imageweiten Zähler. Stackeffekte prüfen bevor
  Literalwerte auf den Benutzerstack gelegt werden, z. B. Code.guard(0,1).
- Image bietet define/org/op/push/cell/emit/resolve. image.words enthält
  Name, Header-/XT-Symbol, need/give und flags; Map löst Symbole auf Adressen auf.
  Kernelaufbau: Boot+idle, emit_primitives (Header, Wörter, Hilfsroutine,
  Fehlerausgänge), emit_parser, danach kernel_end/user_start. Routinen vor kernel_end
  einfügen; kernel_latest derzeit auf letzten Eintrag von image.words gesetzt.
- error_exit führt derzeit nach idle. Zeilenverwerfen ab AP 5 und Rollback
  ab AP 6 ergänzen; beim Fehler keine Rückkehr durch verworfene Frames.
- Budget weiterer Kernelpfade einschließlich zusätzlicher Aufrufrahmen prüfen.
  Keine stillschweigende Stackvergrößerung; Architekturänderungen dokumentieren.
