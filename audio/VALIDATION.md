# Audio validation and measured resources

Implementation checked on 2026-10-31. Hardware playback has not been tested and
no FPGA or flash programming was performed.

## FPGA implementation

Same Olimex iCE40HX8K-CT256 target, 25 MHz system clock and nextpnr seed 1.
Before: `build/audio-before/`; after: `build/audio-after/`.
The integrated bitstream is `build/audio-after/prim.bin`.
[Saved resource reports and RTL checksum](resources.json).

| Resource | Before | After | Delta | Capacity |
| --- | ---: | ---: | ---: | ---: |
| Routed logic cells | 5872 | 7630 | +1758 | 7680 |
| Synthesis LUT4 | 4934 | 6015 | +1081 | 7680 |
| Synthesis flip-flops | 1569 | 2279 | +710 | 7680 |
| Block RAM, 4 Kibit | 17 | 17 | 0 | 32 |
| PLL | 1 | 1 | 0 | 2 |
| Global buffers | 4 | 7 | +3 | 8 |
| I/O pins | 56 | 57 | +1 | 206 device maximum |

LUTs/flip-flops are components of logic cells and must not be added to that
count. Routed timing passes at **25 MHz**; the final timing JSON reports a
maximum internal system frequency of **28.17 MHz**. This is a static timing
result, not a measured board clock/SRAM/audio specification.

The complete current system uses **99.3% of logic cells, with 50 cells free**.
The initial 700-cell audio target was not met. The full feature set fits using
shared phase/envelope/scaling paths and write backpressure instead of a third
configuration bank, but leaves little room for further logic. No extra EBR or
PLL is used. Future changes must be synthesized and routed again; this fit is
not a promise of spare capacity for another peripheral.

## Automated checks

- Audio core and enabled/disabled system MMIO tests pass. The harness also
  verifies the reduced TokenForth immediate-code boundary (222 code bytes
  accepted; 223 refused before changing memory).
- Forth driver/demo sources compile in the actual interpreter on the Python
  CPU. A compiled check word then runs on the actual CPU RTL against the SRAM
  bus and integrated audio registers. It verifies 440 Hz triangle, 523 Hz saw,
  a raw 24-bit rate and enveloped noise. CPU halt is followed by four frame
  times to allow the last queued update to commit. The test-local CPU copy
  suppresses unrelated instruction logging; CPU logic is unchanged.
- Python source suite: **107 tests pass**; shared harness suite: **16 tests pass**.
- All **23 CTest entries** pass across the full run and the final rerun of the
  two initially failing entries. The failures were an older timer scoreboard
  treating FFEF as SRAM and the original serial compilation test's timeout;
  the final tests use the new memory contract and separate compilation/runtime.
- The Forth regression entry includes **97 passing tests**, including the full
  UART/PS2/VGA dual-console RTL session. Report:
  `build/audio-checks/forth-tests/report.json`.
- `git diff --check` passes.

Logs: `/tmp/audio-python-tests.log`, `/tmp/audio-harness-tests.log`,
`/tmp/audio-ctest.log`, `/tmp/audio-ctest-rerun.log`. CTest's retained final
entry output is under `build/audio-checks/Testing/Temporary/`.

## Forth RAM

Fresh standard images/maps: `build/audio-forth/` (dual console) and
`build/audio-forth-uart/` (UART only). Both raw images contain 65,504 bytes,
ending at FFDF; reserved SRAM and MMIO are excluded from free dictionary counts.

| Profile/content | Dictionary start/HERE | Usable end, exclusive | Free bytes |
| --- | --- | --- | ---: |
| Fresh dual-console kernel | 31BA | F000 | 48710 |
| Fresh UART-only kernel | 2482 | F000 | 52094 |
| UART-only + audio.fs + demo.fs | 2D6A | F000 | 49814 |
| Same plus compiled test definition | 2DDE | F000 | 49698 |

The optional sources consume 2280 dictionary bytes in the checked UART-only
profile. They are loaded definitions, not added initial kernel words. The
library counts come from the interpreter's freshly compiled HERE/header values
and the runtime RTL RAM dump. Future kernel/source changes can change them.

## Pending physical checks

Connect the RC filter and Adafruit PAM8302 to GPIO1.9 with a suitable supply;
check PWM/filter signal, speaker loudness, clipping, startup/reset clicks,
idle noise and supply stability while VGA and PS/2 operate. Verify the amplifier
supply's current headroom before drawing power from the board regulator.
