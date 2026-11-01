# TODO

- [x] VGA-Fontdaten reparieren: Der ursprüngliche Atlas enthält bereits
  abgeschnittene Unterlängen und keinen Unterstrich. Vollständigen 8x16-Zeichensatz
  übernommen und Font-/Rasterprüfungen ergänzt.
- [ ] Reparierten VGA-Font auf dem Board prüfen: Unterlängen (`g j p q y`),
  Unterstrich und unterste Reihe der Blockgrafik vollständig sichtbar.

- [ ] Compiler-Ladeabbild auf tatsächlich benötigte Speicherbereiche verkleinern;
  benötigte Nullinitialisierungen dabei erhalten.

- [x] Eine Heartbeat-LED auf dem FPGA-Board blinken lassen und am Board prüfen.
  LED2 wird vom Heartbeat-Zähler im Board-Wrapper angesteuert. Blinken auf dem
  Board vom Benutzer bestätigt.
