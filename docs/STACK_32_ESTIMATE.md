# Abschätzung: Hardwarestacks 32/32

Historische Abschätzung vom 31. Oktober 2026 auf Quellstand `322411a`.
Die anschließende Umsetzung und tatsächlichen Messwerte stehen in
[STACK32_IRQ.md](STACK32_IRQ.md).
Diese Abschätzung ändert weder Hardwarestacks noch Forth noch Bitstream.

Die aktuelle AP8-Messung in [PS2_AP8_RESOURCES.json](PS2_AP8_RESOURCES.json)
liefert die Basis mit VGA und PS/2. Ein älterer Synthese-/Routingvergleich
unter `build/stack-comparison/RESULTS.md` (Quellstand `797f599`) enthält
16/16 und 32/32 bei unverändertem CPU-RTL. Die Board-Peripherie ist seitdem
erweitert worden. Deshalb sind die auf den heutigen Aufbau übertragenen
Differenzen Schätzwerte, keine neue Messung.

| Ressource | Aktuell 16/16 | Schätzung 32/32 | Differenz |
| --- | ---: | ---: | ---: |
| Logikzellen | 4225 / 7680 (55,0 %) | ca. 5966 / 7680 (77,7 %) | +1741 |
| LUT4 | 3518 | ca. 5001 | +1483 |
| Flip-flops | 1054 | ca. 1569 | +515 |
| Block-RAM | 17 / 32 | 17 / 32 | 0 |
| PLL | 1 / 2 | 1 / 2 | 0 |
| Freier Forth-Wörterbuchbereich nach Boot (Dual-Konsole) | 44140 Bytes | 44140 Bytes bei unverändertem Forth | 0 |

Die Logikzellen würden damit um ca. 41,2 % gegenüber dem aktuellen Aufbau
wachsen; ca. 1714 Zellen (22,3 %) blieben frei. LUT4, Flip-flops und Carry-Zellen
sind Bestandteile der Logikzellen und werden nicht dazuaddiert.

Die zwei Stackarrays wachsen insgesamt von 512 auf 1024 Bits: 64 zusätzliche
Bytes Speicherkapazität im FPGA. Die vorhandene Implementierung nutzt dafür
Register und Auswahllogik, kein externes SRAM und kein Block-RAM. Die ältere
Vergleichsmessung ergab 3511 -> 5252 Board-Logikzellen, 3017 -> 4500 LUT4
und 855 -> 1370 Flip-flops. Größere Multiplexer erklären den gegenüber den
reinen Speicherbits erheblichen Logikbedarf.

Der freie Forth-Wörterbuchbereich liegt aktuell bei `4394..EFFF` (hex),
also 44140 Bytes direkt nach Boot, vor Benutzerdefinitionen. Die UART-only-
Variante hat 47534 Bytes frei. Reservierte Bereiche sind darin nicht enthalten.
Eine reine Hardwarevergrößerung hebt das geprüfte Forth-Benutzerlimit von
acht Zellen nicht an; dafür wären gesonderte Softwareänderungen nötig.

Die aktuelle 16/16-Variante erreicht intern 28,98 MHz bei 25 MHz Solltakt.
Für den heutigen Aufbau mit 32/32 ist ohne neuen Routinglauf keine belastbare
Timingangabe möglich. Die Schätzung setzt die bestehende Registerimplementierung
voraus; ein Umbau auf Block-RAM wäre eine andere Architektur.
