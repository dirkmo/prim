# TODO

- [x] VGA-Fontdaten reparieren: Der ursprüngliche Atlas enthält bereits
  abgeschnittene Unterlängen und keinen Unterstrich. Vollständigen 8x16-Zeichensatz
  übernommen und Font-/Rasterprüfungen ergänzt.
- [x] Reparierten VGA-Font auf dem Board prüfen: Sichtprüfung vom Benutzer
  am 2026-11-01 als bestanden bestätigt; Schrift wird vollständig dargestellt.

- [ ] Compiler-Ladeabbild auf tatsächlich benötigte Speicherbereiche verkleinern;
  benötigte Nullinitialisierungen dabei erhalten.

- [x] Eine Heartbeat-LED auf dem FPGA-Board blinken lassen und am Board prüfen.
  LED2 wird vom Heartbeat-Zähler im Board-Wrapper angesteuert. Blinken auf dem
  Board vom Benutzer bestätigt.
