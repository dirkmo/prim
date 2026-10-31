# Procedural FPGA audio

Three independent pulse/triangle/saw tone voices plus one rate-controlled noise
voice, 4-bit volume, constant or attack/decay envelopes, mixed into an 8-bit PWM
output. No wavetables, samples, EBRs, extra PLLs or audio IRQs.

- [Register interface](registers.md): addresses, commands, clocking and reset.
- [Forth driver](forth/audio.fs): load this optional library into the existing
  on-CPU Forth interpreter, line by line using the normal UART console/pacing.
- [Examples](forth/demo.fs): scale, chord, laser and siren.
- [Validation and resources](VALIDATION.md): measured implementation results.

The system integration necessarily changes files outside `audio/`: system bus,
board ports/constraints/source lists, image/loader limits, regression references
and root CTest registration. All audio-specific RTL, Forth, tests and interface
documentation live here.

## Wiring

Olimex iCE40HX8K-EVB Rev.B: **GPIO1.9 / FPGA ball F5**, passed through the
attached iCE40-IO Rev.A board. This pin is separate from VGA, PS/2 and UART.

```text
GPIO1.9 --- 2.2 kohm ---+--- PAM8302 A+
                       |
                     10 nF
                       |
GND -------------------+--- PAM8302 GND, A-

Rated supply -------------- PAM8302 VIN
PAM8302 OUT+ --- Ekulit LSM-92F 8 ohm / 1 W --- PAM8302 OUT-
```

Use the Adafruit module, whose input coupling capacitors are already fitted.
Start at low gain; speaker outputs are bridged and neither goes to ground.
Use an adequately rated amplifier supply with local decoupling and shared ground.
The FPGA GPIO supplies only the signal. Board regulator headroom has not been
measured; the implementation does not assume it can power the amplifier.
The RC filter corner is approximately 7.2 kHz at the 97.656 kHz PWM rate.
An amplifier shutdown GPIO is not needed. Startup clicks remain a hardware check.

## Build, load and use

```sh
make bitstream FPGA_BUILD_DIR=build/audio-after
make forth-image
# Flash/program the bitstream through the normal explicit hardware workflow.
# Then upload the freshly rebuilt CPU image and open its normal console.
```

Load `audio/forth/audio.fs` first. It creates ordinary Forth dictionary words;
it does not change the initial kernel vocabulary. Number base is left DECIMAL.
For example:

```forth
AUDIO-INIT
440 TONE
660 TONE
AUDIO-STOP-ALL
440 TRI-TONE
1 AUDIO-VOICE AUDIO-SAW 6 AUDIO-VOLUME 523 AUDIO-HZ AUDIO-TRIGGER
4000 NOISE
AUDIO-MUTE
AUDIO-ON
AUDIO-STOP-ALL
```

| Word | Stack effect | Meaning |
| --- | --- | --- |
| AUDIO-INIT | -- | Stop all, initialize voice 0 pulse defaults, enable output |
| AUDIO-VOICE | voice -- | Select voice 0..3 |
| AUDIO-PULSE / AUDIO-TRIANGLE / AUDIO-SAW | -- | Stage waveform in constant mode |
| AUDIO-MODE | mode -- | Stage raw waveform/envelope bits |
| AUDIO-VOLUME | volume -- | Stage peak 0..15 |
| AUDIO-DUTY | threshold -- | Stage pulse width, normally 128 |
| AUDIO-HZ | unsigned-hz -- | Stage tone frequency/noise update rate, board 25 MHz |
| AUDIO-RATE | low16 high8 -- | Stage exact 24-bit increment |
| AUDIO-ATTACK / AUDIO-DECAY | ms -- | Stage milliseconds per level step |
| AUDIO-ENVELOPE | attack-ms decay-ms -- | Stage timings and enable one-shot mode |
| AUDIO-CONSTANT | -- | Clear envelope bit, retain waveform |
| AUDIO-APPLY / AUDIO-TRIGGER | -- | Apply config; trigger additionally restarts |
| AUDIO-STOP / AUDIO-STOP-ALL | -- | Stop selected/all voices |
| AUDIO-STATUS | -- flags | Read playing/pending masks |
| AUDIO-ON / AUDIO-OFF / AUDIO-MUTE | -- | Output control, no phase/envelope pause |
| TONE / TRI-TONE | hz -- | Voice 0, volume 8, constant pulse/triangle, trigger |
| NOISE | rate-hz -- | Voice 3, volume 8, instant attack, 8 ms/step decay, trigger |

AUDIO-HZ uses `floor(hz * 43980 / 256)`, an unsigned double-width product,
with approximately 11 ppm coefficient error plus increment quantization. Use
AUDIO-RATE for exact tuning or other system clocks. Recommended integer input
range is 1..20000 Hz. Helper variables make the library non-reentrant; current
interrupt handlers do not use them. There are no audio register accesses in an ISR.

Load `audio/forth/demo.fs` for `AUDIO-SCALE`, `AUDIO-CHORD`, `AUDIO-LASER` and
`AUDIO-SIREN`. Chord runs until stopped. `NOISE` is already a percussion example.
Scale/laser/siren use `AUDIO-MS`, requiring the existing timer to run freely at
one millisecond/count, COMPARE=65535 and AUTO enabled. These examples do not change timer setup
or timer interrupt handling. When the timer is otherwise unused, explicitly run
`AUDIO-DEMO-TIMER` once to set up this mode (it disables timer interrupts).
If the application owns a different timer mode,
use its own delay/scheduler. `AUDIO-CHORD` and the direct examples need no timer.

The memory map now reserves **FFE0..FFFF**; program images end at **FFDF**
(65,504 bytes). Loader `--skip-mmio` trims the entire range. Use matching freshly
built firmware/images. The usable standalone Forth dictionary still ends at
EFFF; the additional registers take 16 bytes from reserved upper SRAM.
TokenForth scratch space at FF00 shrinks to 224 bytes (222 code bytes plus its
existing BREAK/end margin). Existing timer/UART/VGA/PS2 addresses do not move.

## Checks

```sh
.venv/bin/python audio/tests/test_audio.py
.venv/bin/python audio/tests/test_forth.py
ctest --test-dir build/audio-checks --output-on-failure -R audio
```

Core tests cover phase tuning, waveform endpoints, pulse width, noise period,
constant/envelope modes, command write backpressure, reset, mix headroom and
PWM average. Bus tests cover enabled/disabled operation, masks, byte lanes,
unaligned RATE writes, SRAM/audio/timer boundaries and address wrapping. The
Forth check compiles the optional sources with the actual interpreter on the
Python CPU, then executes a compiled test word on CPU, SRAM bus, system MMIO
and audio RTL. The standard Python CPU runner still
has no audio model; its compile check does not imply sound simulation.
