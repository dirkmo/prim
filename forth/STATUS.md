# Eigenständiges Forth für Prim – Arbeitsstand und Arbeitspakete

Stand: 31. Oktober 2026. Dieses Dokument dient als Übergabe an weitere Chats.

## Auftrag und aktueller Stand

Ein kleines, eigenständiges Forth unter `forth/` im Projekt-Root entwickeln.
Es verwendet normale Forth-Syntax und einen vollständig auf der Prim-CPU
laufenden Textinterpreter und Compiler. Standardkonformität ist kein Ziel.

**AP 1 und AP 2 sind abgeschlossen. Kernel-Build und Boot sind implementiert;
noch kein Forth-Interpreter oder Laufzeitcompiler.** Der Nutzer hat zuletzt
mit „nun ap2“ AP 2 beauftragt. AP 3 wurde nicht begonnen.
Die konkrete Architektur steht in [ARCHITECTURE.md](ARCHITECTURE.md).

AP 3–10 sind offen. Dieses Dokument bei späterer Arbeit knapp aktuell halten:
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
Interruptfreigaben; anschließend endlose JP-Warteschleife. Keine öffentlichen
Forth-Wörter oder Wörterbuchheader vorhanden, kernel_latest=0.

Befehle und Simulatorverfahren: [README.md](README.md). Artefakte unter
build/forth/: kernel.bin (65520 Bytes, ohne MMIO), kernel.map.json,
kernel.disasm. Aktuell idle=0487, KERNEL_END=048B, USER_START=048C.
Variablenzellen 0100..0125; genaue Namen/Adressen in kernel/boot.py und Map.
Alle übrigen in AP 1 reservierten Bereiche bleiben bestehen.

Validierung: ` .venv/bin/python forth/tests/test_boot.py --rtl -v `:
4 Tests erfolgreich; darin Bootvergleich in 3 SRAM-Timingkonfigurationen
mit UART-MMIO. Je 69 Instruktionen bis idle, maximal 2 Datenstackzellen,
keine Returnstack-Einträge. Reproduzierbarkeit, schmutziger RAM und erneuter
Kaltstart geprüft. Nur Testkopie erhält BREAK bei idle. Kein Boardtest.

### AP 3 – Grundwörter und UART

Status: offen. Abhängigkeiten: AP 2.

Stackoperationen, Arithmetik, Vergleiche, Speicherzugriffe, `KEY`, `EMIT` und
`CR` bereitstellen. Fehlende Rechenoperationen in Software ergänzen, soweit
für die folgenden APs benötigt. Returnstackzugriffe mit Aufrufkonvention
abgleichen; vorhandene CPU-Mnemonics nicht blind als Forth-Wörter übernehmen.

Ergebnis: grundlegende Operationen und UART-Ein-/Ausgabe funktionieren.

### AP 4 – Texteingabe und Parser

Status: offen. Abhängigkeiten: AP 3.

Zeilenpuffer, einfache Eingabekorrektur, Wortzerlegung, Kommentare und
Zahlenkonvertierung mit `BASE`, `DECIMAL` und `HEX` umsetzen.

Ergebnis: gewöhnlicher Forth-Text wird vollständig auf der CPU eingelesen
und in Wörter/Zahlen zerlegt; Puffergrenzen werden berücksichtigt.

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

- AP 2 vollständig unter forth/ umgesetzt; CPU, TokenForth und bestehende
  Simulationshelfer unverändert. Tests siehe AP 2 und README.md.
- Nächster AP: AP 3, Grundwörter und UART. Emitterschnittstelle: Image.define,
  org, op, push(Ref(...)/Zahl), emit, resolve. Kernelaufbau in emit_kernel;
  USER_START und Bootinitialisierung folgen derzeit direkt dem Bootcode.
  Beim Hinzufügen von Wörtern Kernelende und kernel_latest entsprechend
  nach hinten verlegen und Boottests auf das neue Wörterbuch anpassen.
- Budget von acht temporären Datenzellen für weitere Kernelpfade nachweisen;
  bisher ist nur Boot mit maximal zwei belegt. Keine stillschweigende
  Stackvergrößerung. Falls nötig Architekturentscheidung explizit überarbeiten.
