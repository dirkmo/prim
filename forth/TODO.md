# Offene Forth-Aufgaben

Bei späteren Forth-Arbeiten diese Liste prüfen und am Ende kurz an die offenen
Punkte erinnern. Die Liste ist eine Erinnerung im Projekt; weitere Aufgaben
werden erst auf Auftrag begonnen.

- [x] **Timer-Callback:** Konfigurierbares XT, im ISR vorgemerktes Ereignis,
  explizites `TIMER-POLL` im Vordergrund und `TIMER-EVERY` ergänzt.
- [x] **Standard-Hardwarewörter:** Timer samt Callback-Hilfe, gemeinsame
  VGA-Konsolenwörter und Audio-Treiber ins Dual-Standard-Image aufgenommen.
  Demos bleiben separat; das UART-only-Profil behält den kleinen Kern.

- [x] **1. Höhere Kernelwörter in Forth:** `.fs`-Quellen beim Imagebau mit dem
  CPU-seitigen Compiler übersetzen, ins Startwörterbuch übernehmen und erste
  höhere Wörter übertragen. Acht Wörter stehen in `kernel/core.fs`; der Prim-
  Compiler erzeugt ihren Code und der Build übernimmt Wörterbuch und Bootgrenzen.
- [x] **2. SEE für Benutzerwörter:** Wortaufrufe, Literale und Sprungziele im
  laufenden System anzeigen; keine exakte Rekonstruktion von IF/Schleifen
  erforderlich. Implementiert, einschließlich eingebetteter Strings, Bereichs-
  grenzen, Stack/BASE-Erhaltung und Konsolen-/IRQ-Prüfungen.
- [x] **3. MARKER:** Wörterbuchstand samt Datenallokationen in Forth sichern und
  exakt wiederherstellen, einschließlich eigener Definition und Alignment.
  `MS` mit Callback-Verarbeitung sowie überlappungssicheres `MOVE` und `FILL`
  stehen ebenfalls als Forth-Quellen im Standard-Image.
- [x] **4. Zeitfunktionen vereinheitlichen:** Audio-Demos verwenden den gemeinsamen
  Timer-Treiber über `TIMER-INIT`/`TIMER-WAIT`; Ladeabhängigkeiten und exklusive
  Timer-Nutzung für beide Konsolenprofile dokumentiert.
- [ ] **5. Quellpositionen bei Fehlern:** Bei Uploads Dateiname, Zeilennummer
  und betroffenes Wort ausgeben.
- [ ] **6. Status automatisch ableiten:** Wortanzahl und Speicherbilanz aus
  dem aktuellen Build übernehmen, statt feste Werte manuell zu pflegen.
