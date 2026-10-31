# Eigenständiges Forth für Prim

Stand AP 6: **interaktives Forth mit Laufzeitcompiler und 71 Kernelwörtern**.
Parser, Namenssuche, Übersetzung neuer Definitionen und Ausführung laufen auf Prim.
Kontrollstrukturen und Daten-Definitionswörter folgen in AP 7/8.
CPU und TokenForth wurden nicht verändert.

Architektur: [ARCHITECTURE.md](ARCHITECTURE.md).
Kompakte Übergabe und Arbeitspakete: [STATUS.md](STATUS.md).

## Ausprobieren und bauen

Vom Projekt-Root mit Python 3.11+:

```sh
.venv/bin/python forth/run.py
```

Der Simulator baut den aktuellen Kernel und führt ihn im Python-Modell der
Prim-CPU aus. Der Host transportiert Bytes, er interpretiert keinen Forth-Text.
Im POSIX-Terminal übernimmt der Kernel Echo und Backspace; Ctrl+C beendet den
Simulator und stellt den Terminalmodus wieder her. Eine Pipe mit abgeschlossenen
Zeilen ist ebenfalls möglich; EOF beendet den Simulator, sobald der Kernel
wieder auf ein Zeichen wartet. Eine nicht abgeschlossene letzte Zeile wird
nicht ausgeführt. Bei noch offener Definition führt der Kernel am EOF Rollback
und Fehlerausgabe aus; der Simulator endet mit Status 1. Auf dem FPGA gibt es
kein UART-EOF: mehrzeilige Definitionen warten dort weiter auf Eingabe.
Der Adapter simuliert RAM/UART, keine Timer- oder FPGA-Zyklen.

Beispielsitzung (erste Zeile ist die Bereitschaftsmeldung):

```text
ok
2 3 + .
5 ok
: quadrat dup * ;
ok
7 quadrat .
49 ok
1 2 .s
<2> 1 2 ok
```

Kernel-Artefakte erzeugen:

```sh
.venv/bin/python forth/build.py
```

Ohne Paketinstallation und ohne TokenForth-Kompilation. Absolute Skriptpfade
funktionieren aus fremden Arbeitsverzeichnissen. `--output DIR` überschreibt das
Standardziel `build/forth/`; relative Ziele beziehen sich auf das Arbeitsverzeichnis.

| Artefakt | Inhalt |
| --- | --- |
| kernel.bin | SRAM 0000..FFEF, 65520 Bytes, Einstieg 0, kein MMIO |
| kernel.map.json | Symbole, Variablen, Speicherbereiche, Header/XT und Stackeffekte |
| kernel.disasm | Instruktionsdisassembly mit Codelabels; Daten ausgelassen |

Builds sind byteweise reproduzierbar, ohne Zeitstempel/Buildpfade. Unbenutzter
RAM im Image ist null. Das Image ab Adresse 0 laden; erneutes vollständiges Laden
überschreibt den Benutzerbereich. Es wurde noch kein Boardtest durchgeführt.

## Bedienung und Wortschatz

```text
DUP DROP SWAP OVER ROT -ROT NIP 2DUP 2DROP
+ - * / MOD /MOD 1+ 1- NEGATE ABS 2* 2/
AND OR XOR INVERT LSHIFT RSHIFT
= <> < > U< 0= 0< 0<> MIN MAX TRUE FALSE
@ ! C@ C! +! CELL+ CELLS KEY EMIT CR SPACE
BASE DECIMAL HEX \ (
. U. DEPTH .S WORDS ABORT
: ; STATE IMMEDIATE [ ] LITERAL ' ['] EXECUTE
```

Namen werden ohne Unterscheidung von ASCII-Groß-/Kleinschreibung gesucht;
neuere Einträge überschreiben ältere, HIDDEN-Einträge werden übersprungen.
Suche erfolgt vor Zahlenerkennung. Im Interpretationsmodus werden COMPILE_ONLY-
Einträge abgewiesen, andere über ihre XT ausgeführt. Im Kompiliermodus werden
gewöhnliche Wörter übersetzt, IMMEDIATE-Wörter sofort ausgeführt.

Zellen rechnen modulo 65536; wahr ist FFFF, falsch 0. Vergleiche und `.` sind
signed, U< und U. unsigned. /MOD liefert `( n1 n2 -- rest quotient )` mit Quotient
gegen null und Restvorzeichen des Dividenden; null als Divisor und -32768/-1
sind Fehler. * liefert die unteren 16 Bits. 2/ ist arithmetisch, RSHIFT logisch;
Schiebeweiten 0..15. Alle Rechenoperationen verwenden die bestehende ISA.

BASE liefert die Adresse der Basiszelle; zulässig sind 2..36. DECIMAL/HEX setzen
10/16. Zahlen erlauben ein Vorzeichen vor optionalem `$` (Hex) oder `#` (Dezimal),
Ziffern 0..9/A..Z/a..z, positive 0..65535, negative Beträge bis 32768. Überlauf
ist Fehler. . und U. verbrauchen einen Wert und geben ein nachfolgendes Leerzeichen
aus. .S bewahrt den Stack und zeigt `<Tiefe> ` gefolgt von Werten von unten nach
oben; auch die Tiefe wird in BASE ausgegeben. WORDS zeigt sichtbare Namen,
neueste zuerst, mit abschließendem CRLF. DEPTH liefert die bisherige Benutzertiefe.

Der Interpreter antwortet beim Start und nach erfolgreicher Zeile mit `ok`/CRLF,
bei noch offener Definition mit `compiled`/CRLF.
Fehler verwerfen die restliche Zeile und den logischen Datenstack, drucken den
Grund und kehren mit `ok` zur Eingabe zurück. Unbekannte/compile-only Wörter
werden im Fehlertext genannt. ABORT tut dasselbe ohne Fehlermeldung. HERE/LATEST
bleiben für abgeschlossene Definitionen erhalten; offene Definitionen werden
vollständig aus der Wörterbuchkette zurückgenommen.

read_line erlaubt 127 Nutzbytes plus Abschlussbyte. CR oder LF beendet die
Zeile, CRLF zählt einmal. BS/DEL löscht ein Byte und gibt BS SPACE BS aus;
Löschen bei leerer Zeile wird ignoriert. TAB/VT/FF sind erlaubt, andere
Steuerzeichen (auch NUL) machen die Textzeile ungültig. KEY liefert NUL trotzdem
regulär. Ungültige/überlange Zeilen werden vor der Fehlermeldung bis EOL verworfen;
Backspace kann eine bereits überlange Zeile nicht mehr retten. Sender müssen
RXAVAIL-Kredit berücksichtigen oder ausreichend gepacet senden: kein RX-FIFO
und keine verlustfreie Paste-Garantie. FPGA-UART überträgt sieben Bit.

`\` ignoriert den Zeilenrest, `(` bis zum nächsten `)` derselben Zeile, ohne
Verschachtelung. Beide benötigen eine Wortgrenze. Tokens dürfen 127 Bytes lang
sein; die Namensgrenze von 31 Bytes gilt für Wörterbucheinträge.

## Kernel-Schnittstellen und Grenzen

Alle öffentlichen Wörter haben geprüfte aufrufbare Stubs und Header der
Kompilierklasse 0. Auch der Laufzeitcompiler verwendet geprüfte Aufrufe statt
ungeprüfter Opcode-Inlines. An Wortgrenzen maximal acht
Benutzerzellen, DEPTH zählt nur diese. Acht Hardwarezellen sind als temporäre
Reserve vorgesehen. Returnstack unverändert 16 Zellen, ohne Überlaufschutz.

Boot initialisiert BASE=10, STATE/DEPTH=0, Parser-/Compilerzustand=0,
HERE=USER_START und LATEST auf den letzten Kernelheader. Er maskiert CPU- und
UART-Interrupts, erhält Benutzer-RAM und konsumiert kein RX. Einstieg über idle
nach console_start, kein äußerer CALL-Rahmen. Kaltstart vergisst Benutzerwörter;
Fehler/ABORT etablieren an den aktuellen Hardwarezeigern eine neue logische
Stackbasis, statt durch verworfene Frames zurückzukehren.

| Private Routine | Vertrag ohne Änderung von DEPTH |
| --- | --- |
| raw_key / raw_emit | `( -- c )` / `( c -- )`, Bytezugriffe mit RXAVAIL/Bus-ACK |
| is_space / fold_ascii | `( c -- flag )` / `( c -- c' )`, ASCII |
| read_line | `( -- )`, input_buffer/input_length, setzt Parserposition zurück |
| parse_name | `( -- )`, token_addr/token_length, Länge 0 bei Zeilenende; konsumiert ein Trennzeichen |
| skip_line / skip_paren | `( -- )`, verschieben input_pos |
| parse_number | `( -- )`, number_status 0=ungültig, 1=Erfolg, 2=Überlauf; number_value sonst 0 |
| find_word | `( -- )`, Token nach found_header/xt/flags, jeweils 0 bei Misserfolg |
| print_signed / print_unsigned | `( n/u -- )`, kein nachfolgendes Leerzeichen |
| unsigned_divide | `( -- )`, arith_a/b nach arith_q/rem; b=1..32768, kein öffentliches UM/MOD |

Metadaten-Routinen bewahren Benutzerwerte, nutzen gemeinsame Zellen und sind
nicht reentrant. raw_key/raw_emit/is_space/fold_ascii arbeiten dagegen mit
expliziten temporären Stackwerten. Ungültige BASE löst auch in parse_number
direkt Fehler aus. Status 0/2 wertet der Interpreter nach erfolgloser Suche aus.

Scratch: 0380..038D Arithmetik; 038E..039D Ziffernpuffer (max. 16 Bytes);
03A0..03AF Stackanzeige (max. acht Zellen); 039E..039F und 03B0..03FF frei.
Keine dieser Daten darf einen sie überschreibenden Hilfsaufruf überleben.
Exakte Variablen-/Codeadressen stehen in der Map; wesentliche globale Verträge
stehen in STATUS.md. Arbiträre !/C!/EXECUTE-Adressen sind nicht isoliert;
Kernelkorruption und Returnstacküberlauf sind nicht sicher abfangbar.

last_error (0126), 0 nach Reset, danach zuletzt gemeldeter Fehler:
1 Unterlauf, 2 Überlauf, 3 Schiebeweite, 4 Division null, 5 Divisionüberlauf,
6 Zeile zu lang, 7 Kommentar offen, 8 BASE, 9 Text-Steuerzeichen,
10 Zahlüberlauf, 11 unbekanntes Wort, 12 compile-only Wort, 13 Compilerkontext,
14 Name, 15 Wörterbuch voll, 16 kein Benutzerwort für IMMEDIATE, 17 offener
Kontrollstack, 18 unvollständige Definition bei Simulator-EOF. ABORT lässt ihn stehen.

## Compiler (AP 6)

`: name ... ;` erzeugt einen eigenen Header und nativen Prim-Code im SRAM.
Definitionen dürfen mehrere Zeilen umfassen. Bis `;` ist der Header HIDDEN;
bei einer Neudefinition kann der alte Name weiterhin aufgerufen werden.
Ein verschachteltes `:` ist Fehler. `;` erfordert Kompiliermodus und leeren
Kontrollstack. Leere Definitionen sind erlaubt. IF/Schleifen kommen erst in AP 7.

STATE liefert eine lesbare Variablenadresse: 0 interpretiert, 1 kompiliert.
Direkte Zustandsänderungen mit ! sind nicht unterstützt. `[` interpretiert
innerhalb einer Definition, `]` setzt dort das Übersetzen fort. Beispiel:

```forth
: antwort [ 20 22 + ] LITERAL ;
antwort .
```

IMMEDIATE markiert das letzte abgeschlossene Benutzerwort. Keine Kernelwörter
oder offenen Definitionen markieren. `:` und `]` sind unmittelbare Kontextwörter;
`;`, `[`, LITERAL und `[']` sind IMMEDIATE und COMPILE_ONLY. Die Kommentarwörter
bleiben IMMEDIATE. Beispiel einer auf der CPU ausgeführten Compiler-Erweiterung:

```forth
: zahl 42 ; IMMEDIATE
: antwort zahl LITERAL ;
```

`' name` liest zur Ausführungszeit den nächsten Namen und legt dessen XT ab.
In einer Definition wird dieser Parseraufruf übersetzt. `['] name` kompiliert
dagegen das XT als Literal; EXECUTE verbraucht ein XT und führt es aus.
Beispiel: `3 ' DUP EXECUTE .S` zeigt `<2> 3 3 `.

Kompilierte Aufrufe: PUSH16 xt; CALL. Literale: PUSH16 literal_guard; CALL;
PUSH8/16 wert. Der Guard prüft und zählt die Benutzerzelle zur Laufzeit, bevor
der Wert abgelegt wird. Die Kompilierung selbst legt Zahlen nicht auf den
Benutzerstack. Alle Wörter behalten ihre Stackprüfungen; keine neue ISA.

Am sicheren Wortende ersetzt der Compiler CALL durch JP oder setzt Bit 7 am
abschließenden PUSH-Opcode. Er merkt Opcodeadresse, Art und Ende, prüft die
Adresse gegen den aktuellen Definitionskörper und verändert keine Operandbytes.
Leere/unsichere Enden erhalten NOP.RET. Jede Immediate-Ausführung außer `;`
deaktiviert konservativ die Optimierung für die ganze Definition, auch Kommentare
und `[ ]`. Dadurch bleibt ein gemeinsamer Rücksprung für spätere Kontrollwörter
erhalten. CALL.RET wird nicht verwendet; CALL ignoriert das Return-Bit.

Der Compiler prüft HERE gegen USER_START..F000 und reserviert Header-/Codeblöcke
vor dem ersten Schreiben; einzelne Byte-/Zellemitter prüfen zusätzlich ihre
Grenzen. Fehler oder ABORT stellen HERE/LATEST der begonnenen Definition wieder
her, bevor der offene Zustand gelöscht wird. Abgeschlossene Wörter bleiben
erhalten. Beliebige Seiteneffekte von Immediate-Wörtern werden nicht rückgängig
gemacht. Der Compiler verwendet nur Klasse 0, keine Opcode-Inline-Klasse.

Private APIs für weitere APs: compiler_reserve nutzt compiler_needed (Bytes),
compile_byte/compile_cell verbrauchen einen rohen Wert, compile_word nutzt
found_xt, compile_literal nutzt compile_value. rollback_definition bewahrt den
Benutzerstack. literal_guard ist ein spezieller Laufzeit-Guard, der DEPTH um
eins erhöht; der anschließende generierte PUSH liefert die eigentliche Zelle.

## Prüfungen

```sh
.venv/bin/python forth/tests/test_boot.py --rtl -v
.venv/bin/python forth/tests/test_primitives.py --rtl -v
.venv/bin/python forth/tests/test_parser.py --rtl -v
.venv/bin/python forth/tests/test_console.py --rtl -v
.venv/bin/python forth/tests/test_compiler.py --rtl -v
```

Ohne `--rtl` entfallen die entsprechenden RTL-Tests. Dafür mit `--rtl` werden
iverilog und vvp im PATH benötigt; Simulatoren entstehen in temporären Verzeichnissen.
Vorhandene Helfer aus tests/support/ bleiben unverändert.

Stand AP 6: 43 Testmethoden bestanden. Enthalten sind 54 instruktionsweise
CPU/SRAM/Python-Vergleiche in drei SRAM-Timings (1/1/3 ns, 2/2/12 ns, 3/4/19 ns),
gerichtete UART-Puffer-Tests für KEY und Zeileneingabe sowie 14 komplette
Konsolensitzungen mit RX-Pacing, TX-Rückstau und verzögertem ACK. Erwartete Ausgabe
und Stackwerte werden unabhängig vorgegeben. Serielle TX-Dekodierung wird in
den SRAM-Tests geprüft, serielle RX-Leitung und echte Hardware hier nicht.

Zahlenausgabe in allen Basen 2..36 und .S bei jeder Tiefe 0..8 sind geprüft,
einschließlich Puffergrenzen und Stackwiederherstellung. Strukturelle Prüfung
aller übrigen Wort-/Parser-/Such-/Compilerpfade: maximal 12 physische Datenzellen,
höchstens vier zusätzlich zur Eingabetiefe, fünf Returnframes einschließlich
Wortaufruf. .S hat zählerabhängige Stack-Schleifen: separat alle Tiefen/Basen,
maximal elf Datenzellen und drei Returnframes. Fehlerwiederaufnahme ist auch
über mehrfaches zyklisches Wraparound der Hardwarezeiger geprüft. Weitere
Benutzeraufrufe sind zusätzlich zu budgetieren. EXECUTE hat ein dynamisches
Ziel und wird separat mit gültigen XT, Stackgrenzen und übersetzten Zielen
geprüft. Eine Kette von 40 Tail-Aufrufen läuft ohne tiefen Returnstack. Der
optimierte Wrapper benötigt direkt ausgeführt zwei Returnframes, der
äquivalente unoptimierte drei. SRAM-Tests kompilieren und führen ein Literal
mit Operandbyte 80 auf der CPU aus und prüfen Rollback nach unbekanntem Wort.
Wörterbuchgrenzen, verborgene Header, Immediate-Ausführung und Opcode-/
Operandgrenzen sind ebenfalls geprüft.
