# Kleines Forth auf Prim – Architekturentscheidung (AP 1)

Stand: 31. Oktober 2026. Zielarchitektur; AP 2 implementiert Build und Boot,
alle weitergehenden Sprachfunktionen sind noch geplant. Änderungen hier begründen.
Arbeitsstand und APs: [STATUS.md](STATUS.md).

## Ziel und Abgrenzung

Eigenständiges interaktives Text-Forth im Verzeichnis `forth/`. Parser,
Wörterbuchsuche, Interpreter und Compiler laufen auf Prim. Der Host baut und
lädt lediglich das initiale Image und transportiert Konsolentext. TokenForth,
seine Tokens und sein Wörterbuch sind keine Laufzeitabhängigkeit.

Bestehende ISA und je 16 Hardware-Stackzellen bleiben unverändert. Keine neue
Hardware, keine Stackvergrößerung. Kein Anspruch auf Standardkonformität.
Erste Version: eine Konsole, ein Wörterbuch, keine Interruptbenutzung, keine
Dateien, kein Multitasking, kein Persistieren selbst kompilierter Wörter.

## Speicher und Boot

Alle Bereiche sind Byteadressen; Zellen sind 16 Bit Little Endian.

| Bereich | Verwendung |
| --- | --- |
| `0000..00FF` | Bootsprung und reservierter Startbereich |
| `0100..01FF` | Kernelvariablen und Scratchzellen |
| `0200..027F` | Eingabepuffer, maximal 127 Zeichen plus Abschlussbyte |
| `0280..02FF` | Temporärer Stringpuffer, 128 Bytes |
| `0300..037F` | Compiler-Kontrollstack: 32 Einträge zu je 4 Bytes |
| `0380..03FF` | Scratch für Stackanzeige, Zahlenausgabe, Rechenroutinen |
| `0400..KERNEL_END-1` | Initialer Kernel einschließlich Wörterbuch |
| `USER_START..EFFF` | Benutzerwörterbuch, Code und Daten, aufwärts wachsend |
| `F000..FFEF` | Reserve, nicht durch ALLOT/Compiler belegen |
| `FFF0..FFFF` | System-MMIO, kein normaler RAM |

`USER_START = align2(KERNEL_END)`; Buildfehler, wenn der Kernel keinen
Benutzerspeicher vor F000 lässt. Kein fester, ungemessener Kernelgrößenanspruch.
Compiler/Allocator rechnen Überläufe vor dem Schreiben nach und erlauben
`HERE` höchstens F000 (exklusives Speicherende, kein weiteres Byte verfügbar).

Boot ab Adresse 0 per Sprung, nicht als aufgerufene Konsole. Kaltstart setzt
BASE=10, STATE=0, logische Stacktiefe=0, Eingabe-/Compilerzustand zurück,
HERE=USER_START und LATEST auf den letzten Kernelheader. Interrupts mit INTDI
maskieren, UART-Interruptfreigaben per Bytezugriff auf FFFE löschen. Kein
automatischer RAM-Test und keine Timerprogrammierung.

Neustart über Reset ist Kaltstart: Benutzerdefinitionen werden vergessen,
auch wenn ihre Bytes noch im SRAM stehen. Fehler-Neustart erhält dagegen die
bereits abgeschlossenen Benutzerdefinitionen.

## Wörterbuch und Ausführungstoken

Verkettete Header, neuester zuerst; Null-Link beendet die Suche. Namen sind
ASCII, 1..31 Zeichen, ohne Leerraum. Suche ohne Unterscheidung von ASCII-Groß-
und Kleinschreibung. Neuere Definition überschattet ältere; keine Warnpflicht.

| Offset | Inhalt |
| --- | --- |
| +0 | Link zum vorherigen Header, 16 Bit |
| +2 | Flags, 8 Bit |
| +3 | Namenslänge, 8 Bit |
| +4 | Ausführungsadresse XT, 16 Bit |
| +6 | Kompilierklasse, 8 Bit |
| +7 | Inline-Opcode, 8 Bit, nur bei Inline-Klasse benutzt |
| +8 | Name, anschließend ggf. ein Paddingbyte bis zur geraden Adresse |

Flags: Bit 0 IMMEDIATE, Bit 1 COMPILE_ONLY, Bit 2 HIDDEN; andere Bits null.
Kompilierklasse 0 erzeugt normalen Aufruf, Klasse 1 einen geprüften Inline-
Primitiv-Emitter. Klasse 1 ist Kernelwörtern vorbehalten. Name hinter dem
Header, Code normalerweise direkt hinter Name/Padding; XT bleibt ausdrücklich
gespeichert, damit Kernelheader auch separate Routinen bezeichnen können.

XT ist immer eine ausführbare Prim-Codeadresse, kein Header oder Tokenindex.
Jedes öffentliche Wort hat eine aufrufbare Implementierung, auch bei Inline-
Kompilierung. EXECUTE führt ein XT aus. Bei normalem Forth-Programmieren
werden niemals Rücksprungadressen als Daten verwendet.

CREATE erzeugt einen Stub `PUSH16 body; NOP.RET`, danach beginnt body ohne
Padding hinter dem Stub; HERE zeigt darauf. VARIABLE reserviert dort eine
mit null initialisierte Zelle. CONSTANT erzeugt einen Stub für den Wert.
Keine DOES>-Semantik in Version 1. Alle Wortzugriffe dürfen ungerade Adressen
verwenden; Header werden nur zur Übersicht ausgerichtet.

## Ausführung und Stacks

Subroutine-Threaded Code: `PUSH16 xt; CALL`. Literale als PUSH8 für 0..255,
sonst PUSH16. Primitive soweit sinnvoll inline, mit gleicher Forth-Semantik
wie ihr aufrufbarer Stub. Kein separater innerer Thread-Interpreter.

Der Forth-Datenstack liegt auf dem Hardware-Datenstack. Version 1 garantiert
an öffentlichen Wortgrenzen **maximal 8 Benutzerzellen**; die übrigen 8 sind
für Kernel-Zwischenwerte, Aufrufadressen und Prüfungen reserviert. Eine RAM-
Variable DEPTH zählt ausschließlich Benutzerzellen. Interne Routinen ändern
sie nicht; ihre Werte liegen vorübergehend oberhalb der Benutzerwerte.

Öffentliche Primitive prüfen ihren Bedarf und ihre resultierende Tiefe vor
dem Eingriff und aktualisieren DEPTH. Inline-Emitter müssen dieselben Prüfungen
erzeugen. Ausführung über XT umgeht diese Prüfungen nicht. Jeder Kernelpfad
muss nachweislich höchstens acht zusätzliche Datenzellen beanspruchen;
CALL-Ziel und Prüfcode zählen dazu. Das ist ein Abnahmekriterium, keine bereits
verifizierte Eigenschaft. Colon-Wörter erhalten keinen festen Gesamteffekt;
ihre ausgeführten Primitive prüfen den jeweiligen aktuellen Stackzustand.

Hardware-Returnstack für Aufrufe, nicht für Parser oder Compiler-Kontrollwerte.
**Kein allgemeiner Laufzeitschutz gegen Returnstacküberlauf** in Version 1:
höchstens 16 gleichzeitig lebende Rücksprungadressen einschließlich Kernel.
Kernel-Aufruftiefe messen, danach verbleibendes Benutzerbudget dokumentieren.
Gezielte tiefe Rekursion ist nicht unterstützt; Überschreitung ist ein
Programmierfehler mit möglichem Kontrollflussverlust, kein sicher abfangbarer
Forth-Fehler. Tail-Sprünge reduzieren den Bedarf. Keine Behauptung, dass
beliebige Fehler nach einem bereits eingetretenen Stacküberlauf reparierbar sind.

`>R R> R@`, DO/LOOP und allgemeine Rücksprungadressmanipulation werden zunächst
nicht öffentlich angeboten. Insbesondere ist ein normales CALL zu einem
Stub mit CPU-R> semantisch falsch: oben liegt dessen eigene Rücksprungadresse.
Eine spätere Erweiterung braucht dafür gesonderte Compiler-/Aufrufregeln.

.S kopiert die DEPTH Benutzerwerte vorübergehend in Scratch-RAM und stellt
sie wieder her; Ausgabe von unten nach oben mit Tiefe. Keine Stackzeiger-
Inspektion durch Debug-MMIO voraussetzen.

## Interpreter, Eingabe und Zahlen

Zeilenweiser äußerer Interpreter mit getrennten Parserpositionen für Puffer
und String-/Namensparser. ASCII-Leerraum (09..0D und 20) trennt Wörter.
KEY liefert ein Zeichen nach Prüfung von RXAVAIL (FFFE Bit 0); DATA per C@
an FFFF lesen. EMIT schreibt per C! nach FFFF; Bus wartet bei vollem TX-Puffer.
NUL ist kein Zeichen für „keine Eingabe“. Keine Wortzugriffe auf UART-Register.

CR oder LF beendet eine Eingabezeile; CRLF zählt einmal. Echo, Backspace und
DEL zum Löschen des letzten Zeichens. Überlange Zeile vollständig bis zum
Zeilenende verwerfen und Fehler melden; keinen abgeschnittenen Text ausführen.
127 Zeichen Nutztext pro Zeile. Sender wartet auf die Antwort der Konsole,
bevor er die nächste Zeile sendet; RX hat keinen Mehrzeichen-FIFO. Zeichenweise
Übertragung muss RXAVAIL-Kredit über das bestehende Debugprotokoll beachten
oder ausreichend gepaced sein; die Konsole garantiert kein verlustfreies Paste.

Nach jeder erfolgreichen Zeile außerhalb einer offenen Definition `ok` und
CRLF, innerhalb einer Definition `compiled` und CRLF. Definitionen können
mehrere Zeilen umfassen. Kein automatischer Abbruch bei leerer Folgezeile.

Wörterbuchsuche vor Zahlenerkennung. Zahlen: optionales + oder -, dann Ziffern
in BASE (2..36), ASCII A..Z/a..z als 10..35. Zusätzlich $ für Hex und # für
Dezimal unmittelbar nach dem Vorzeichen. Positiver Bereich 0..65535, negativer
Betrag höchstens 32768; Überlauf ist Fehler, keine stille Modulo-Konvertierung.
BASE außerhalb 2..36 wird bei Konvertierung/Ausgabe abgewiesen. HEX setzt 16,
DECIMAL 10. Keine Doppelzahlen, Gleitkommazahlen oder Zeichenzahlliterale.

Forth-Zellen rechnen modulo 65536. Wahr = FFFF, falsch = 0000; Bedingungen
akzeptieren jeden Wert ungleich null. `<` und `>` sowie `.` sind signed,
U< und U. unsigned. `2/` ist arithmetisches Rechtsschieben (Abrunden gegen
minus unendlich), RSHIFT logisch. Schiebeweiten 0..15 erlaubt, sonst Fehler.
NEGATE/ABS auf 8000 liefern modulo 16 Bit wieder 8000.

* liefert die unteren 16 Produktbits. /MOD teilt signed, Quotient gegen null
gerundet, Rest hat das Vorzeichen des Dividenden: `( n1 n2 -- rest quotient )`.
/ und MOD sind daraus abgeleitet. Division durch null sowie -32768 / -1 sind
Fehler. UM*, M*, UM/MOD und sonstige Doppelzellwörter sind zurückgestellt.
Zahlenausgabe konvertiert intern unsigned Beträge, damit -32768 darstellbar ist.

Kommentare: `\` als separates Wort ignoriert den Zeilenrest; `(` als separates
Wort ignoriert bis `)` innerhalb derselben Zeile, ohne Verschachtelung.
Fehlendes `)` ist Fehler. Keine TokenForth-Kommentar-/Stringregeln übernehmen.

## Compiler und Transaktionen

STATE ist eine lesbare Systemvariable: 0 interpretiert, 1 kompiliert. Schreiben
beliebiger Werte mit ! ist nicht unterstützt; regulär : ; [ ] verwenden.
STATE und „Definition offen“ sind getrennte Zustände. `[` interpretiert
vorübergehend innerhalb einer offenen Definition; `]` setzt dort Kompilieren
fort. `]` ohne offene Definition ist Fehler.

`: name` nur außerhalb einer Definition: HERE/LATEST sichern, Header anlegen
und verborgen halten; verschachteltes : verbieten. Suche überspringt HIDDEN.
`;` nur bei offener Definition, STATE=1 und leerem Kontrollstack: Rückkehr
erzeugen, Header veröffentlichen und STATE=0 setzen. So bezeichnet ein Name
innerhalb seiner Neudefinition gegebenenfalls noch die alte Definition.
RECURSE bleibt vorerst außerhalb des Wortumfangs.

Im Kompiliermodus: nicht-immediate Wort kompilieren, Immediate-Wort sofort
ausführen, Zahl als Literal kompilieren. Im Interpretationsmodus Wort ausführen,
Zahl ablegen; COMPILE_ONLY ohne zulässigen Compilerkontext ist Fehler.

' liest den nächsten Namen und legt XT ab; es ist ein normales, nicht-immediate
Wort. In einer Definition wird sein Laufzeitaufruf kompiliert. `[']` ist
compile-only/immediate und kompiliert das XT des nächsten Namens als Literal.
LITERAL ist compile-only/immediate und kompiliert die oberste Benutzerzelle.
IMMEDIATE markiert die zuletzt abgeschlossene Benutzerdefinition; keine
Kernelheader oder offene Definition verändern.

Unaufgelöste Sprünge liegen in einem eigenen RAM-Kontrollstack, nicht auf dem
Daten-/Returnstack: 32 Einträge mit 16-Bit-Typ und 16-Bit-Adresse. IF/ELSE/THEN
und BEGIN/UNTIL/AGAIN/WHILE/REPEAT prüfen Typ und Grenzen. Version 1 unterstützt
pro BEGIN höchstens ein offenes WHILE. JZ erhält Flag und Zieladresse auf dem
Datenstack und verbraucht beide; Emitter müssen diese CPU-Semantik beachten.

Rollback bei Fehler innerhalb einer Definition setzt HERE und LATEST auf die
gesicherten Werte zurück und verwirft den Kontrollstack. Dies rollt keine
beliebigen Seiteneffekte von Immediate-Wörtern zurück. CREATE/VARIABLE/CONSTANT
sind nur außerhalb offener Definitionen erlaubt; Größe vor Headerpublikation
prüfen. ALLOT akzeptiert nur nichtnegative Größen. Kein FORGET/MARKER.

### Return-Bit und Tail-Aufrufe

AP 6 implementiert beide Optimierungen ohne ISA-Änderung:

- Sicheres letztes Primitiv/Literal: Return-Bit an dessen Opcode setzen,
  separates NOP.RET entfällt. Laufzeit-Stackprüfungen davor müssen erhalten bleiben.
- Sicherer letzter Wortaufruf: CALL durch JP ersetzen; Callee verwendet den
  bestehenden Rücksprung. CALL.RET ist kein Ersatz, da CALL das Return-Bit ignoriert.
- CALL, JP, JZ, INT und BREAK ignorieren Bit 7. Returnstack-Operationen haben
  besondere Semantik und sind keine allgemeinen Fold-Kandidaten.
- Emitter merkt Opcodeadresse, Art und Ende jeder Instruktion. Niemals HERE-1
  ungeprüft patchen: dort können Operanden oder Daten stehen.
- Sprungziele, Kontrollstrukturen, Strings, rohe Datenemitter und Immediate-
  Ausführung invalidieren konservativ die Optimierung für diese Definition.
  Dann abschließendes NOP.RET beibehalten. Ein Sprung zum Definitionsende muss
  den gemeinsamen Rücksprung weiterhin erreichen. Leere Definition: NOP.RET.
- Kein Rückwärtsdisassemblieren und keine allgemeine Optimierung des
  Kontrollflussgraphen in Version 1.

## Öffentlicher Wortumfang der ersten Version

Dies ist der Zielumfang nach AP 8, nicht die Liste bereits vorhandener Wörter.
Stubs/Inline-Emitter müssen jeweils dieselben dokumentierten Stackeffekte haben.

| AP | Wörter |
| --- | --- |
| 3 | DUP DROP SWAP OVER ROT -ROT NIP 2DUP 2DROP |
| 3 | + - * / MOD /MOD 1+ 1- NEGATE ABS 2* 2/ |
| 3 | AND OR XOR INVERT LSHIFT RSHIFT |
| 3 | = <> < > U< 0= 0< 0<> MIN MAX TRUE FALSE |
| 3 | @ ! C@ C! +! CELL+ CELLS KEY EMIT CR SPACE |
| 4 | BASE DECIMAL HEX |
| 5 | . U. .S DEPTH WORDS ABORT |
| 6 | : ; STATE IMMEDIATE [ ] LITERAL ' ['] EXECUTE |
| 7 | IF ELSE THEN BEGIN UNTIL AGAIN WHILE REPEAT |
| 8 | HERE ALLOT , C, CREATE VARIABLE CONSTANT TYPE S\" .\" |

`\` und `(` als Parserwörter ab AP 4. Parserinterne Wörter wie FIND und
PARSE-NAME benötigen zunächst keine öffentliche Schnittstelle. Kein POSTPONE,
EXIT, DOES>, EVALUATE, ACCEPT, CATCH/THROW oder Benutzer-Returnstack im ersten
Umfang. Spätere Ergänzungen separat festlegen.

`S" text"` und `." text"`: öffnendes Wort wird durch Leerraum getrennt;
genau ein folgendes Leerraumzeichen gehört zur Syntax, restlicher Inhalt
bis zum nächsten Doppelquote wird wörtlich übernommen. Leere Strings erlaubt,
keine Escapes und kein Zeilenwechsel im String, maximal 127 Bytes.
S" interpretiert: `( -- addr len )` im temporären Stringpuffer, gültig bis zum
nächsten S" oder Kaltstart. Kompiliert: Stringdaten im Definitionskörper mit
Sprung darüber und Laufzeit-Literalen für Adresse/Länge. ." führt TYPE aus bzw.
kompiliert dessen Aufruf. Beide sind immediate, in beiden Modi verwendbar.
TYPE `( addr len -- )` gibt Bytes aus; EMIT/UART beschränken auf sieben Bit.

## Fehler und Grenzen

Erkennbare Fehler: unbekanntes Wort, ungültige/überlaufende Zahl, ungültige
BASE, Eingabe-/Namens-/Stringgrenze, Datenstack-Unter-/Überlauf an Wortgrenzen,
Compilerkontext oder Kontrollstruktur falsch, Speicher erschöpft, ungültiges
ALLOT/Shift, Division durch null/Quotientenüberlauf.

Fehlerausgabe `error: <kurzer Grund>` plus ggf. betroffenem Wort und CRLF.
Aktuelle Zeile verwerfen, ggf. Definition zurückrollen, STATE=0, Kontrollstack
und logischen Datenstack leeren, per JP zum äußeren Eingabeschleifenkopf.
ABORT nimmt denselben Weg ohne Fehlermeldung. Der Schleifenkopf hat keinen
zurückkehrenden Aufrufer. Bestehende physische Daten-/Returnstackzeiger müssen
dabei nicht null sein: verworfene Frames gelten als frei, neue Stackbasis ist
die aktuelle Zeigerposition. Keine Rückkehr durch alte Frames nach ABORT.

Keine Speicherisolation: @ ! C@ C! und EXECUTE sind mächtige rohe Operationen.
Schreiben auf Kernel, Verwaltungszellen oder MMIO kann das System beschädigen;
ungültige XT, Endlosschleifen und Hardware-Returnstacküberlauf sind nicht sicher
abfangbar. Compiler-/Allocatorgrenzen sind kein Schutz gegen absichtliche
Speichermanipulation. Hardwaredebug bleibt für solche Fälle nutzbar.

## Buildstruktur und Abnahmekriterien für die folgenden APs

Dateistruktur: `forth/build.py`, `forth/image.py`, `forth/kernel/`,
`forth/tests/`, `forth/README.md` ab AP 2; `forth/lib/` und `forth/examples/`
erst bei Bedarf in späteren APs anlegen.
Buildwerkzeug in Python, Wiederverwendung von prim.isa und Prim-Assembler/
CPU-Modell erlaubt, keine TokenForth-Compiler-/Tokenizerabhängigkeit. Statische
Kernelbeschreibung darf Prim-Code und Header generieren; sie darf den späteren
CPU-Interpreter nicht durch Ausführung auf dem Host ersetzen.

AP-2-Artefakte unter build/forth/: kernel.bin (RAM 0000..FFEF, 65520 Bytes),
kernel.map.json und kernel.disasm. CLI: `python3 forth/build.py`; Build- und
Simulatoranleitung in README.md. Keine Änderungen am ISA-/Stackmodell.

AP 2 prüft Boot/Speicherkarte. Ab AP 3 Stackbudget und arithmetische Grenzfälle
prüfen. Ab AP 5 echte Textsessions mit unabhängig erwarteten Ergebnissen,
ab AP 6 CPU-seitige Definitionen und Rollback, ab AP 7 verschachtelte Sprünge.
Optimierungen mit Verhalten, Codegröße und Returnstackbedarf prüfen. Ab AP 9
Python-Modell und RTL/UART abdecken; relevante bestehende Tests unverändert
erhalten. Hardwaretests sind gesondert auszuweisen, nicht aus Simulation ableiten.
