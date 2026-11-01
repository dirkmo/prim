# Procedural FPGA audio

Three independent pulse/triangle/saw tone voices plus one rate-controlled noise
voice, 4-bit volume, constant or attack/decay envelopes, mixed into an 8-bit PWM
output. One EBR holds parameters and voice state. No wavetables, samples, extra
PLLs or audio IRQs.

- [Register interface](registers.md): addresses, commands, clocking and reset.
- [Forth driver](forth/audio.fs): included in the standard dual-console image;
  load it manually only with the smaller UART-only profile.
- [Examples](forth/demo.fs): scale, chord, laser and siren.
- [Validation and resources](BRAM_VALIDATION.md): measured implementation results.

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
make bitstream FPGA_BUILD_DIR=build/audio-bram
make forth-image
# Flash/program the bitstream through the normal explicit hardware workflow.
# Then upload the freshly rebuilt CPU image and open its normal console.
```

The standard dual-console image already contains `audio/forth/audio.fs` as
protected kernel words. Run `AUDIO-INIT` before playback; boot does not start
audio. With the UART-only profile, load the driver manually first; number base
is left DECIMAL. Demo words in `audio/forth/demo.fs` remain optional.
All voices now share one preparation buffer: `AUDIO-VOICE` changes the target
only. Configuration getters return the shared preparation buffer, not a saved
bank for the selected voice. Active playback remains independent. The existing
helpers and demos work with this behavior; custom drivers that relied on
per-voice staging must explicitly prepare their configuration.
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
The standard dual-console image includes both required drivers. With UART-only,
upload `timer/forth/timer.fs`, then `audio/forth/audio.fs`, then
`audio/forth/demo.fs`, one line at a time. Loading these files only defines words;
it does not configure the timer or start audio. The sources leave BASE decimal.

Scale/laser/siren use `AUDIO-MS`, a wrapper around the shared `TIMER-WAIT`.
They require free-running COUNT, COMPARE=65535 and AUTO enabled; one tick is
one millisecond on the Olimex 25 MHz build. When the timer is otherwise unused,
explicitly run `AUDIO-DEMO-TIMER` (a wrapper around `TIMER-INIT`) once:

```forth
AUDIO-INIT
AUDIO-DEMO-TIMER
AUDIO-SCALE
```

Setup resets the timer and disables its interrupts; it leaves CPU and console
IRQs alone. The demos do not reconfigure the timer themselves. `AUDIO-MS`
handles 16-bit COUNT wrap but does not poll callbacks; do not use timed demos
alongside `TIMER-EVERY` or another timer mode. Applications that own the timer
must use their own delay/scheduler (for example `MS` for periodic callbacks in
the standard image). `AUDIO-CHORD` and the direct examples need no timer.

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
.venv/bin/python audio/tests/test_forth.py --standard
ctest --test-dir build/audio-checks --output-on-failure -R audio
```

Core tests cover phase tuning, waveform endpoints, pulse width, noise period,
constant/envelope modes, command write backpressure, reset, mix headroom and
PWM average. A separate port-only scoreboard runs on both behavioral RTL and
the synthesized iCE40 primitives, verifies exactly one inferred audio EBR, and
checks shared staging, independent playback and clearing dirty RAM on reset. Bus tests cover enabled/disabled operation, masks, byte lanes,
unaligned RATE writes, SRAM/audio/timer boundaries and address wrapping. The
Forth check compiles the optional sources with the actual interpreter on the
Python CPU, then executes a compiled test word on CPU, SRAM bus, system MMIO
and audio RTL. `--standard` exercises the built-in driver from the standard
dual-console image without uploading its source. The standard Python CPU runner still
has no audio model; its compile check does not imply sound simulation.
