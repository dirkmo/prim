# Shared staging and EBR optimization

Checked on 2026-10-31. This supersedes the resource figures and storage design
in [the original implementation report](VALIDATION.md). Waveforms, 24-bit
frequency resolution, four voices, 4-bit volume and hardware attack/decay remain.
No Forth kernel, ISR, CPU RTL or system address-map changes are part of this
optimization. Another agent is independently optimizing Forth in the workspace.

## Storage and interface changes

- Replace four 55-bit staging banks with **one 55-bit common staging register**.
  This removes 165 preparation register bits before mapping. VOICE changes
  the command target only; it does not load or swap preparation fields.
- Store the four active configurations, phases and envelope states in **one
  4-Kibit EBR**. Seven 16-bit words per voice store 101 useful bits plus padding;
  each record occupies an eight-word slot. Only 32 words need reset clearing.
- One 112-bit shift register loads/stores a voice record through the synchronous
  16-bit RAM port. Shared envelope, phase and scaling arithmetic processes each
  record in 29 clocks: 116 clocks for all voices, inside the 256-clock frame.
- On system reset, a 32-clock write sequence clears RAM. MMIO waits until this
  completes. This preserves EBR inference without resetting the RAM array.
- Commands snapshot their targets at the next frame boundary. Pending bits
  clear after complete state writeback; all audio writes wait while pending.
  Reads remain available after initialization. Changed staging cannot leak
  into an older command. Output duty still updates at frame boundaries.
- Millisecond epochs stored per voice let the frame sequencer service hardware
  envelopes once per tick, including 8-bit epoch wraparound. Tick service delay
  is less than one audio frame; no timer interrupt or software envelope is used.

The [register reference](registers.md) specifies the intentional compatibility
change: register reads return common staging, not the selected voice's bank.
The existing Forth library and demos work without modification. A custom driver
that depended on per-voice staging must explicitly prepare its parameters.

## Measured board resources

Olimex iCE40HX8K-CT256, 25 MHz, nextpnr seed 1. Before:
`build/audio-after/` (commit 6ead0a9 register-based audio). Optimized:
`build/audio-bram/`; bitstream `build/audio-bram/prim.bin`.
[Saved resource reports and RTL checksum](resources.json).

| Resource | Before | Optimized | Change | Capacity |
| --- | ---: | ---: | ---: | ---: |
| Routed logic cells | 7630 | 6733 | -897 | 7680 |
| Synthesis LUT4 | 6015 | 5573 | -442 | 7680 |
| Synthesis flip-flops | 2279 | 1923 | -356 | 7680 |
| Block RAM, 4 Kibit | 17 | 18 | +1 | 32 |
| PLL | 1 | 1 | 0 | 2 |
| Global buffers | 7 | 5 | -2 | 8 |
| I/O pins | 57 | 57 | 0 | 206 device maximum |

Overall logic use drops from 99.3% to **87.7%**, leaving **947 logic cells** and
**14 EBRs** free. The optimization saves 11.8% of the previous total logic-cell
count; routing/packing also contributes to that count. LUT and FF totals are
parts of logic cells, not additional independent usage.

Static timing passes at **25 MHz**. The final timing JSON reports a maximum
internal clock of **28.67 MHz**. No physical programming or listening test was
performed; static timing does not measure speaker or external SRAM behavior.

## Verification

- Five audio harness checks: core arithmetic/noise/envelopes, TokenForth scratch
  boundary, enabled/disabled MMIO, a port-only contract test, and the same
  contract against the synthesized iCE40 cells. All pass.
- The mapped-core check asserts **exactly one SB_RAM40_4K** and exercises actual
  inferred RAM cells, including dirty-reset clearing, write backpressure,
  unchanged shared staging after VOICE writes, independent active voices,
  waveform/PWM averages, noise decay and STOP ALL priority.
- The compiled Forth audio check passes on CPU/SRAM/system/audio RTL with the
  current parallel Forth implementation. It verifies independent 440 Hz/523 Hz
  voices, a raw 24-bit rate and enveloped noise. Audio Forth sources are unchanged.
- Eight selected CTest entries pass: audio core/mapped RAM, audio Forth, UART IO,
  debug/MMIO, timer, PS/2, VGA and the complete board startup/reset test.
- `git diff --check -- audio` passes.

Commands and retained output:

```sh
.venv/bin/python audio/tests/test_audio.py
.venv/bin/python audio/tests/test_forth.py
.venv/bin/python boards/olimex_ice40hx8k_evb/test_board.py
ctest --test-dir build/audio-checks --output-on-failure \
  -R 'audio_|timer_checks|ps2_checks|vga_checks|olimex_board_checks|uart_io_checks|debug_uart_checks' -j 2
.venv/bin/python boards/olimex_ice40hx8k_evb/build.py build --output build/audio-bram
.venv/bin/python tools/project.py resources --build-dir build/audio-bram
```

Logs: `/tmp/audio-bram-tests.log`, `/tmp/audio-bram-forth.log`,
`/tmp/audio-bram-board-tests.log`, `/tmp/audio-bram-ctest.log` and
`build/audio-bram/{synth.log,nextpnr.log,timing.json}`.

## Parallel Forth snapshot

No Forth source changes are included in the audio optimization. For reference,
fresh images/maps built into audio-owned artifact directories from the ongoing
parallel Forth working tree report:

| Profile | Fresh map | Usable dictionary range | Free bytes |
| --- | --- | --- | ---: |
| Dual console | build/audio-bram/forth-dual/kernel.map.json | 30FA..EFFF | 48902 |
| UART only | build/audio-bram/forth-uart/kernel.map.json | 23C8..EFFF | 52280 |

These are the fresh base-image values, before loading optional audio words;
they exclude reserved SRAM/MMIO. They describe the parallel Forth snapshot, not
RAM savings caused by this hardware optimization. Subsequent Forth edits can
change the counts.
