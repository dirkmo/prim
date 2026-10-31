# Eigenständiges Forth für Prim

Stand AP 5: **interaktiver Textinterpreter mit 61 Wörtern**. Parser,
Namenssuche, Zahlenkonvertierung und Ausführung laufen vollständig auf Prim.
Neue Definitionen mit `:`/`;` folgen in AP 6; momentan sind diese Wörter unbekannt.
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
nicht ausgeführt. Der Adapter simuliert RAM/UART, keine Timer- oder FPGA-Zyklen.

Beispielsitzung (erste Zeile ist die Bereitschaftsmeldung):

```text
ok
2 3 + .
5 ok
7 dup * .
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
```

Namen werden ohne Unterscheidung von ASCII-Groß-/Kleinschreibung gesucht;
neuere Einträge überschreiben ältere, HIDDEN-Einträge werden übersprungen.
Suche erfolgt vor Zahlenerkennung. COMPILE_ONLY-Einträge werden mit Fehler
abgewiesen; die übrigen gefundenen Wörter werden über ihre XT aufgerufen.
Die Kommentarwörter sind IMMEDIATE und werden später auch im Compiler gebraucht.

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

Der Interpreter antwortet beim Start und nach erfolgreicher Zeile mit `ok`/CRLF.
Fehler verwerfen die restliche Zeile und den logischen Datenstack, drucken den
Grund und kehren mit `ok` zur Eingabe zurück. Unbekannte/compile-only Wörter
werden im Fehlertext genannt. ABORT tut dasselbe ohne Fehlermeldung. HERE/LATEST
bleiben erhalten. Definitionstransaktionen kommen erst in AP 6.

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
Kompilierklasse 0. Inline-Emitter folgen in AP 6. An Wortgrenzen maximal acht
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
10 Zahlüberlauf, 11 unbekanntes Wort, 12 compile-only Wort. ABORT lässt ihn stehen.

## Prüfungen

```sh
.venv/bin/python forth/tests/test_boot.py --rtl -v
.venv/bin/python forth/tests/test_primitives.py --rtl -v
.venv/bin/python forth/tests/test_parser.py --rtl -v
.venv/bin/python forth/tests/test_console.py --rtl -v
```

Ohne `--rtl` entfallen die entsprechenden RTL-Tests. Dafür mit `--rtl` werden
iverilog und vvp im PATH benötigt; Simulatoren entstehen in temporären Verzeichnissen.
Vorhandene Helfer aus tests/support/ bleiben unverändert.

Stand AP 5: 30 Testmethoden bestanden. Enthalten sind 48 instruktionsweise
CPU/SRAM/Python-Vergleiche in drei SRAM-Timings (1/1/3 ns, 2/2/12 ns, 3/4/19 ns),
gerichtete UART-Puffer-Tests für KEY und Zeileneingabe sowie sechs komplette
Konsolensitzungen mit RX-Pacing, TX-Rückstau und verzögertem ACK. Erwartete Ausgabe
und Stackwerte werden unabhängig vorgegeben. Serielle TX-Dekodierung wird in
den SRAM-Tests geprüft, serielle RX-Leitung und echte Hardware hier nicht.

Zahlenausgabe in allen Basen 2..36 und .S bei jeder Tiefe 0..8 sind geprüft,
einschließlich Puffergrenzen und Stackwiederherstellung. Strukturelle Prüfung
aller übrigen Wort-/Parser-/Suchpfade: maximal 12 physische Datenzellen,
höchstens vier zusätzlich zur Eingabetiefe, drei Returnframes einschließlich
Wortaufruf. .S hat zählerabhängige Stack-Schleifen: separat alle Tiefen/Basen,
maximal elf Datenzellen und drei Returnframes. Fehlerwiederaufnahme ist auch
über mehrfaches zyklisches Wraparound der Hardwarezeiger geprüft. Weitere
Benutzer-/Compileraufrufe sind später zusätzlich zu budgetieren.
