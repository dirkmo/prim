# Forth für Prim – kompakte Übergabe und Arbeitspakete

Stand: 31. Oktober 2026. AP 1–7 abgeschlossen; AP 8–10 offen.
Letzter Nutzerauftrag: AP 7 und 8 umsetzen, jeweils committen. Dieser Stand wird mit dem
Commit dieser Übergabe festgehalten. AP 8 nicht begonnen.
AP-5-Commit: `d0ff968`, AP 4: `cf739a7`.
Weitere Historie: AP 3 `1e77c88`, AP 1/2 `b620a9e`.

## Aktueller Stand und Leitplanken

Eigenständiges Text-Forth unter forth/, vollständig auf der CPU; kein TokenForth-
Umbau, keine Hosttokenisierung. Nicht standardkonform, bewusst kleiner Umfang.
CPU/ISA, Stackgrößen und bestehende Tests/Simulationshelfer unverändert.
Multiplikation/Division/variable Schiebeweiten in Software. Keine beschlossenen
Hardware-Erweiterungen. Return-Bit-Folding und Tail-CALL→JP sind implementiert.

79 Kernelwörter, interaktiver Interpreter und Laufzeitcompiler für `:`/`;`.
Kontrollstrukturen implementiert; Daten-Definitionswörter folgen in AP 8.
Start: ` .venv/bin/python forth/run.py ` (Prim-Modell mit Terminal-UART).
Build: ` .venv/bin/python forth/build.py `; reproduzierbare kernel.bin/map.json/
disasm unter build/forth/. Image: 65520 RAM-Bytes 0000..FFEF, Einstieg 0.
[README.md](README.md): Bedienung, aktuelle Wortliste, APIs und Testbefehle.
[ARCHITECTURE.md](ARCHITECTURE.md): vollständige Architektur/Zielsemantik.

## Technische Arbeitsreferenz

- Byteadressen, 16-Bit-Zellen Little Endian. Boot 0000..00FF, Variablen
  0100..01FF, Eingabe 0200..027F (127+1), Stringpuffer 0280..02FF,
  Kontrollstack 0300..037F (32 Einträge à vier Bytes), Scratch 0380..03FF,
  Kernel ab 0400, Benutzerbereich ab align2(KERNEL_END) bis exklusiv F000.
  F000..FFEF Reserve, FFF0..FFFF MMIO. Keine Speicherisolation.
- AP 6: idle=053B, console_start=2587, console_next=259F,
  KERNEL_END=USER_START=2BC6, kernel_latest=2B9A. Boot bis idle: 159 Instruktionen,
  maximal zwei Datenzellen, kein Returnframe. Generierte Map ist maßgeblich.
- Boot setzt BASE=10, STATE/DEPTH/Metadaten=0, HERE=USER_START, LATEST=Kernelende
  der Headerkette; Interrupts CPU/UART aus. idle springt zu console_start.
  Dort `ok`/CRLF, danach read_line; jeder erfolgreiche Zeilenabschluss ebenfalls
  `ok`/CRLF bzw. `compiled`/CRLF bei offener Definition. Kein äußerer CALL-Rahmen.
- Header +0 Link16, +2 Flags8, +3 Namenslänge8, +4 XT16, +6 Klasse8,
  +7 Inline-Opcode8, +8 ASCII-Name; Padding gerade. Flags 1 immediate,
  2 compile-only, 4 hidden. Alle aktuellen Klassen 0. Namen 1..31,
  Suche ASCII-case-insensitive, neueste zuerst, HIDDEN überspringen.
- image.words: name, header-/xt-Symbol, need/give, flags. Map löst Adressen auf.
  Code und emit_word in kernel/primitives.py sind gemeinsame Codegeneratoren.
  imageweiter Labelzähler; Image: define/org/op/push/cell/emit/resolve.
- Composition in kernel/boot.py: Boot+idle, emit_primitives, emit_parser,
  emit_console, emit_compiler, kernel_end/user_start. Routinen vor kernel_end
  einfügen, Headerkette am letzten image.words-Eintrag verankern.
- DEPTH zählt nur Benutzerzellen, maximal acht. Geprüfte Wörter/Inline-Emitter
  müssen Bedarf und Wachstum vor Eingriff prüfen. Interne Stackwerte nicht zählen.
  Hardwarestacks je 16; Returnstack ohne allgemeinen Überlaufschutz.
- Scratch exklusiv: 0380..038D Arithmetik (a,b,q,rem,count,qsign,rsign),
  038E..039D Ziffernpuffer, 03A0..03AF .S-Sicherung; Rest frei. Nicht reentrant.
- private read_line/parse_name/parse_number/find_word haben keinen Benutzer-
  stackeffekt. Ergebnisse in Verwaltungszellen. raw_key `( -- c )`, raw_emit
  `( c -- )` und is_space/fold_ascii `( c -- flag/c' )` sind rohe Stackroutinen.
  Öffentliche KEY/EMIT zählen dagegen Benutzerwerte. Siehe README-API-Tabelle.
- read_line: Echo, BS/DEL, CR/LF/CRLF, max.127 Bytes, Abschlussbyte. TAB/VT/FF
  erlaubt, andere C0-Zeichen außer Editing/EOL verwerfen die Zeile bis EOL.
  KEY liefert NUL. skip_lf bleibt über Zeilen und Fehler erhalten.
- parse_name konsumiert ein folgendes Trennzeichen; token_addr/length, Länge0
  am Ende. Tokens bis127, Namensgrenze erst bei Headern. Kommentare `\`/`(`
  sind Immediate-Wörter, nicht automatisch im Scanner verschluckt.
- parse_number: Wörterbuchsuche muss zuerst erfolgen! BASE2..36, Vorzeichen
  vor optionalem $/#, positive0..65535, negative Beträge bis32768.
  number_status0 Syntax/kein Zahlentoken,1 Erfolg,2 Überlauf. number_value sonst0.
  Invalides BASE ist Fehler. Zahlkonvertierung nutzt eigene Verwaltungszellen.
- find_word: Token nach found_header/xt/flags (0 bei Misserfolg); keine Ausführung.
  STATE=0: COMPILE_ONLY ablehnen, sonst XT ausführen. STATE=1: nicht-immediate
  Wörter kompilieren, Immediate ausführen. Zahlen nach erfolgloser Suche entweder
  mit Code.guard(0,1) interpretieren oder als geprüfte Laufzeitliterale übersetzen.
- . signed, U. unsigned, BASE2..36, nachfolgendes Leerzeichen. .S zeigt `<n> `
  plus Werte unten→oben und stellt alle Zellen wieder her; auch n in BASE.
  WORDS sichtbar/neueste zuerst. DEPTH liefert Tiefe vor Ablegen des Ergebnisses.
- /MOD: signed, Quotient gegen null, Rest wie Dividend. unsigned_divide ist
  private Hilfsroutine: arith_a=0..65535, b=1..32768, q/rem als Resultate.
  Gemeinsamer Rechenkern für signed Division und Zahlenausgabe, kein UM/MOD.
- Fehler: Grund/ggf.Token ausgeben, restliche Zeile/Stack verwerfen, über
  error_exit→idle neue logische Basis etablieren. Hardwarezeiger bleiben beliebig;
  alte Frames niemals zurückkehren lassen. Bei offener Definition vorher
  HERE/LATEST auf saved_here/saved_latest zurückrollen, sonst erhalten.
  ABORT analog ohne Fehlertext, last_error bleibt stehen.
- last_error0126: 1 Unterlauf,2 Überlauf,3 Shift,4 Division0,5 Divisionsüberlauf,
  6 Eingabelänge,7 Kommentar,8 BASE,9 Steuerzeichen,10 Zahlüberlauf,
  11 unbekannt,12 compile-only,13 Compilerkontext,14 Name,15 Speicher,
  16 kein Benutzerwort für IMMEDIATE,17 offener Kontrollstack,18 EOF bei offener
  Definition (nur Simulator). Token erst nach Fehlerausgabe löschen.
- Neue Variablen AP5: find_header0142,find_index0144,found_header0146,
  found_xt0148,found_flags014A,print_addr014C,print_left014E,format_count0150,
  dump_count0152,dump_index0154,word_cursor0156. number_status013E,
  number_value0140. Vollständige Zuordnung in boot.py und Map.
- Neue AP6-Zellen: last_kind0158 (1 CALL,2 Literal), emit_value015A,
  compiler_needed015C,compile_value015E,compiler_index0160. last_opcode/last_end
  und fold_safe aus der ursprünglichen Variablenliste verfolgen Instruktionsgrenzen.
- kernel/compiler.py: compiler_reserve nutzt compiler_needed und prüft
  USER_START<=HERE<=F000 sowie Platz ohne Adressüberlauf; compile_byte/cell
  verbrauchen je einen rohen Wert. Header-/Tokenblöcke vorab reservieren.
  compile_word nutzt found_xt; compile_literal nutzt compile_value. Beides ohne
  Benutzerstackeffekt. Literale erzeugen PUSH16 literal_guard;CALL;PUSH8/16 Wert.
  literal_guard prüft/zählt die neue Benutzerzelle vor dem eigentlichen PUSH.
- `:` IMMEDIATE, Header verborgen, alte gleichnamige Definition weiter sichtbar.
  `;` IMMEDIATE/COMPILE_ONLY, nur STATE=1+definition_open+leerer Kontrollstack.
  `[`, LITERAL und `[']` ebenfalls Flags3; `]` Flags1, braucht offene Definition.
  STATE als Adresse lesbar; direktes STATE! nicht unterstützt. IMMEDIATE nur
  für das letzte fertige Benutzerwort. `'` parst zur Laufzeit, `[']` kompiliert XT.
  EXECUTE: geprüfter XT-Verbrauch und tail JP auf Ziel, kein eigener Zusatzframe.
- Abschluss: sicheres letztes CALL→JP, letztes Literal-PUSH mit Bit7; übrige
  Fälle NOP.RET. Adresse muss im aktuellen Körper liegen und last_end=HERE sein.
  Immediate-Ausführung außer `;` invalidiert fold_safe für die ganze Definition.
  Alle Header Klasse0; keine ungeprüften Inline-Opcodes. Leere Wörter NOP.RET.
- rollback_definition erhält Benutzerwerte, stellt bei offener Definition
  HERE/LATEST wieder her, dann Zustandsfelder zurück. Fehler und ABORT rufen
  dies vor dem Löschen von definition_open auf. Keine Rücknahme beliebiger
  Immediate-Seiteneffekte. EOF im Simulator führt bei offener Definition über
  error_incomplete zum CPU-Rollback und Exitcode1; Hardware wartet auf UART.

## Arbeitspakete

1. **AP 1 – Architektur/Sprachumfang: abgeschlossen.** Speicher, Header,
   Stacks, Zahlen-/Fehlersemantik, Zielwortliste und Optimierungsregeln in
   ARCHITECTURE.md. Eigenständiges Forth, bestehende ISA.
2. **AP 2 – Build/Boot: abgeschlossen.** build.py, image.py und kernel/boot.py;
   reproduzierbares Image/Map/Disassembly, Python/RTL-Bootprüfung.
3. **AP 3 – Grundwörter/UART: abgeschlossen.** kernel/primitives.py; 50 Wörter,
   Stackprüfungen, Software-Arithmetik, KEY/EMIT/CR/SPACE. Wörterbuchheader schon
   hier erzeugt. UART- und Arithmetiktests.
4. **AP 4 – Texteingabe/Parser: abgeschlossen.** kernel/parser.py; rohe Eingabe,
   Scanner, Zahlen, Kommentare, BASE/DECIMAL/HEX; fünf zusätzliche Wörter.
5. **AP 5 – Wörterbuch/Interpreter: abgeschlossen.** kernel/console.py;
   Namenssuche, äußere Schleife, . U. .S DEPTH WORDS ABORT, sechs zusätzliche
   Wörter. run.py führt den echten Kernel im CPU-Modell aus, keine Hostauswertung.
6. **AP 6 – Compiler: abgeschlossen.** kernel/compiler.py. `: name ... ;`, STATE, IMMEDIATE,
   `[ ] LITERAL ' ['] EXECUTE`; neue Definitionen auf CPU kompilieren, Header
   bis Abschluss verstecken, HERE/LATEST bei Fehler/ABORT zurückrollen.
   Fehler/ABORT zuerst Rollback, danach definition_open löschen. Konservative
   Return-Bit-/Tail-CALL→JP-Optimierung mit geprüften Wortaufrufen/Literalen.
   Keine Opcode-Inline-Klasse notwendig. Zehn neue Kernelwörter.
7. **AP 7 – Kontrollstrukturen: abgeschlossen.** Abhängig AP6. IF ELSE THEN BEGIN UNTIL
   AGAIN WHILE REPEAT, getrennter RAM-Kontrollstack, Typ-/Grenzprüfung.
   Maximal ein offenes WHILE pro BEGIN. DO/LOOP nicht im ersten Umfang.
8. **AP 8 – Daten/Alltagswörter: offen.** Abhängig AP6/teilweise7. HERE ALLOT ,
   C, CREATE VARIABLE CONSTANT TYPE S" ."; Stringsyntax/Lebensdauer gemäß
   Architektur. Interne Emitter werden bereits AP6 benötigt. Kein DOES>.
9. **AP 9 – Integration/Regression: offen, begleitet laufend.** Nach AP8 abschließen.
   Textsessions/CPU-Kompilierung, unabhängige Sollwerte, Python/RTL/UART,
   Fehler-/Speichergrenzen. Vorhandene Regressionen erhalten; echte Hardware
   getrennt ausweisen.
10. **AP 10 – Anleitung/Beispiele: offen, begleitet laufend.** Nach AP9
    abschließen. README/Wortliste/Grenzen aktuell halten, examples/ ergänzen,
    diese Übergabe pflegen. lib/ und examples/ erst bei Bedarf anlegen.

## Verifikation und nächste Schritte

```sh
.venv/bin/python forth/build.py
.venv/bin/python forth/tests/test_boot.py --rtl -v
.venv/bin/python forth/tests/test_primitives.py --rtl -v
.venv/bin/python forth/tests/test_parser.py --rtl -v
.venv/bin/python forth/tests/test_console.py --rtl -v
.venv/bin/python forth/tests/test_compiler.py --rtl -v
.venv/bin/python forth/tests/test_control.py --rtl -v
```

AP7: alle 50 Testmethoden bestanden (4+9+8+9+13+7). Darin 57 instruktionsweise
Python/CPU/SRAM-Vergleiche über drei Timings, gerichtete KEY-/Eingabeprüfung
sowie 22 komplette UART-Puffer-Konsolensitzungen. Alle Basen, alle .S-Tiefen,
Puffergrenzen, versteckte/überschriebene/compile-only Einträge, Suche vor Zahl,
Fehler-/ABORT-Wiederaufnahme und zyklisches Zeiger-Wraparound geprüft.
Strukturell maximal 12 Datenzellen (vier temporäre) und fünf Returnframes; .S separat
315 Tiefen/Basenfälle, maximal elf Datenzellen und drei Returnframes. Keine seriellen
RX- oder Boardtests. Konsolen-RTL speist Bytes vor uart_buffers ein.

AP6 zusätzlich: Multiline, Immediate, Tick/EXECUTE, Neudefinitionen, Header-Hiding,
Namen bis31, Speicherende/Wraparound und atomare Fehler, Operanden mit Bit7,
40er Tail-Kette, kontrollierter zusätzlicher Returnframe ohne Optimierung.
EXECUTE separat geprüft (dynamisches Ziel, aus struktureller Prüfung ausgenommen).
Kompilierung/Ausführung und Rollback im physischen SRAM-Modell bei allen drei
Timings geprüft, keine Hosttokenisierung. CPU und bestehende Infrastruktur unverändert.

AP7: kernel/control.py, 32 typisierte Einträge (IF=1, ELSE=2, BEGIN=3,
WHILE=4), Push/Peek geprüft. control_addr/type/slot/patch sind neue Zellen.
branch_guard prüft/vermindert DEPTH vor JZ, lässt das physische Flag stehen.
Vorwärts-Fixups auf HERE begrenzt, falsche Verschachtelung Fehler17, voll Fehler19.
USER_START=3066, Boot171 Instruktionen. Exakte Adressen in generierter Map.
Alle acht Kontrollwörter Flags3. Eine WHILE-Ebene pro BEGIN. Returnfolding wird
über Immediate-Pfad deaktiviert, gemeinsames NOP.RET bleibt stehen.
Tests prüfen beide Zweige, Schleifen/Nesting, Flags/Stackgrenzen, 32/33 Fixups,
Rollback, acht Benutzerdaten während Kompilierung und SRAM-Codeausführung.
forth/tests/forth_sram.py erweitert nur den Watchdog in einer temporären Kopie
auf 1.000.000 Takte; keine Änderung an CPU, Timing oder vorhandenen Helfern.

Nächstes AP8 noch nicht begonnen. Datenwörter und Strings gemäß Architektur,
mit Bounds/Transaktionen und korrekten Laufzeit-Stackprüfungen ergänzen.
