# Procedural mono audio implementation plan

Status: implemented; see [audio documentation](../audio/README.md) and
[the final register contract](../audio/registers.md). Hardware listening validation
remains pending. The implementation uses write backpressure instead of the
original snapshot queue below to fit the current system. Scope approved for planning: three tone voices, one noise
voice, envelopes and one GPIO output. No wavetables or sample playback.

## Architecture and sound contract

- Reuse the 25 MHz system clock exclusively, with clock enables. No extra PLL,
  derived clock, audio interrupt, DMA, FIFO or block RAM.
- Generate one audio frame every 256 system clocks: 97,656.25 frames/s. Use
  8-bit PWM at the same repetition rate, loading the next duty value only at a
  frame boundary. The PWM continues during silence at midpoint duty (128).
- Three independently tunable tone voices: pulse with programmable duty,
  triangle and sawtooth. Each voice selects its own waveform. Pulse duty uses
  an 8-bit threshold; define the constant-output endpoint cases explicitly.
- Each tone voice has a 24-bit phase accumulator, advanced once per frame.
  `increment = round(frequency_hz * 2^24 / (CLK_HZ / 256))`. At 25 MHz the
  frequency resolution is approximately 0.00582 Hz. Generate note increments
  on the host; a note-frequency table in software is not a waveform table.
- Derive 8-bit waveform values from phase using bit selection, inversion and
  comparison. No sine, band-limiting, resonant filter or FM in this version.
  Document aliasing at high pitches and the analog filter's limited bandwidth.
- A fourth, independent voice generates deterministic pseudo-random noise using
  a maximal-length 15-bit LFSR and its own 24-bit rate accumulator. Shift on
  accumulator carry; this rate is the noise update rate, not a musical pitch.
  Specify taps, shift direction and nonzero reset seed in the RTL contract.
- Each voice has a 4-bit peak volume (0..15). Constant-volume mode supports
  sustained notes. One-shot mode implements attack then decay to zero, with
  independent 8-bit millisecond intervals per amplitude step; zero means an
  immediate transition. No sustain/release stages in the first version.
- Derive envelope timing from a dedicated 1 ms clock enable, without changing
  the existing CPU timer. Apply the resulting levels at audio frame boundaries.
- Reuse one amplitude-scaling datapath across the four voices. Pulse/noise
  require only sign selection; triangle/saw can use a shared four-step
  shift/add scaler instead of parallel multipliers. Complete each mix within
  the 256-clock frame budget and register its result.
- Use a wide signed sum, fixed normalization with headroom, and explicit
  saturation before conversion to unsigned 8-bit PWM. Never allow arithmetic
  wraparound. Define rounding and signed widths in the implementation contract.
- Global enable/mute and optional power-of-two attenuation; no master multiplier.
  Mute retains phase/envelope progression. STOP clears the selected voice level;
  global STOP clears all voice levels. No audio is enabled at reset.
- HALT and CPU-only debug reset leave audio running, following existing
  peripheral behavior. System reset clears all voices and restores midpoint
  PWM duty. Startup/reset clicks are assessed on hardware; click-free operation
  is not promised without a separate amplifier mute control.

## Register integration

FFF0..FFFF is fully occupied. Reserve a new 16-byte block at **FFE0..FFEF**,
without moving existing peripherals. Proposed byte register layout:

| Address | Register | Purpose |
| --- | --- | --- |
| FFE0 | MASTER | Enable, mute, global attenuation; reserved bits read zero |
| FFE1 | VOICE | Select voice 0..3 |
| FFE2 | MODE | Waveform and constant/envelope mode |
| FFE3 | VOLUME | Peak volume 0..15 |
| FFE4..FFE6 | RATE | Little-endian 24-bit phase increment/noise rate |
| FFE7 | DUTY | Pulse threshold |
| FFE8 | ATTACK | Milliseconds per rising amplitude step |
| FFE9 | DECAY | Milliseconds per falling amplitude step |
| FFEA | COMMAND | APPLY, TRIGGER, STOP, global STOP commands |
| FFEB | STATUS | Active voice mask and update-pending indication |
| FFEC..FFEF | Reserved | Read zero, writes ignored |

Per-voice configuration registers are staging registers. APPLY snapshots the
selected voice configuration into a pending update; TRIGGER also restarts its
phase/noise state and envelope. Commit the complete snapshot at the next frame
boundary, preventing transient frequencies during three separate RATE writes.
Define command priority, pending-write behavior and update status before RTL;
the intended policy is one pending snapshot per voice, latest command wins,
and global STOP cancels all older pending updates. Reads return staging values;
STATUS describes active playback. Normal parameter updates preserve phase.

Integrate byte lanes into the existing `memory_io` wrapper. Preserve byte,
unaligned word, wrapping word and mixed SRAM/peripheral transaction semantics;
side effects occur exactly once for each selected lane. CPU and halted-debug
access share the same contract. Add `AUDIO_ENABLE`, default off in generic
systems and on in the Olimex board. The block remains reserved when disabled.

This changes the software-visible SRAM endpoint to FFDF (65,504 bytes):

- Update board host image validation/trimming and `--skip-mmio` reporting from
  FFF0 to FFE0; loading must never write audio registers accidentally.
- Update `forth/image.py`, generated maps, image sizes and relevant tests/docs.
  `USER_LIMIT=F000` remains unchanged; the 16-byte reservation comes from the
  upper reserved area, not the usable Forth dictionary.
- Update TokenForth immediate scratch bounds above FF00. Its available area
  shrinks from 240 to 224 bytes; derive bounds from the MMIO base, retaining
  the existing end-margin convention. Audit hard-coded 238/240-byte assumptions.
- Rebuild images alongside the new bitstream and document their compatibility.

## Board and external circuit

Proposed audio output: **GPIO1.9 / FPGA ball F5**. The checked-in main-board
netlist connects these directly, and the iCE40-IO Rev.A netlist passes pin 9
through without a peripheral load. Check current constraints and board revision
again during integration, then add `audio_pwm` to the top-level and PCF.

External connection: GPIO -> 2.2 kohm -> filter node -> PAM8302 A+; 10 nF
from filter node to GND. Ground A-, share signal/power ground, and connect the
confirmed Ekulit LSM-92F (8 ohm, 1 W) between the amplifier outputs. Use the
Adafruit module's existing input coupling capacitors and start with low gain.
Use an adequately rated amplifier supply and local decoupling; assess the
available board 3.3 V supply headroom before choosing it as amplifier power.
No second FPGA pin is required for the amplifier shutdown input.

## Implementation work packages and acceptance

1. **Freeze contracts and baseline.** Record the current board build's actual
   resource/timing reports, pin mapping, register semantics and reset behavior.
   Define numeric widths, envelope endpoints and command collision behavior.
   Target zero added EBRs/PLLs and provisionally at most 700 added logic cells;
   this is an engineering target, not a measured estimate or fit guarantee.
2. **Implement and simulate standalone audio RTL** under `audio/rtl/`, with
   focused tests under `audio/tests/`. Verify tuning/phase wrap, duty, triangle
   and saw endpoints, LFSR period/nonzero seed, envelope timing/retrigger, all
   four voices mixed at maximum, saturation, silence and PWM average duty.
   Verify the shared datapath completes before every frame boundary.
3. **Integrate MMIO and software memory limits together.** Add the optional
   peripheral to `memory_io`, `prim_system`, board top and source/test manifests.
   Test staging versus playback, command collisions, ACK side effects, reset,
   disabled mode, CPU/debug visibility, boundary words FFDF/FFE0 and FFEF/FFF0,
   and loader refusal/trimming. Run affected CPU/peripheral regressions.
4. **Add Forth support and demonstrations.** Prefer an optional source library
   under `audio/examples/` over expanding every kernel image. Provide words for
   selecting/configuring voices, frequency/note setting, trigger, stop and mute.
   Demonstrate a scale, three-note chord, triangle melody, noise percussion,
   software-driven laser sweep and siren. The CPU sequences notes and changes
   parameters; it does not feed audio samples. Reuse existing timing facilities
   without changing the timer interrupt contract. Verify the examples in RTL;
   the Python simulator has no audio peripheral and must not imply audio support.
5. **Synthesize, route and document.** Run the integrated board build at 25 MHz.
   Report matching before/after logic cells, LUT4, flip-flops, EBRs and PLLs;
   accept only a timing-passing build. Rebuild Forth images and report free RAM
   from fresh profile maps using the actual usable dictionary range. Document
   registers, wiring, source builds, loading and example commands in English.
6. **Physical acceptance after the amplifier arrives.** Check the unloaded GPIO
   and PWM/filter signal if instruments are available, then connect the module
   and speaker at low volume. Confirm scale/chord/percussion, useful loudness,
   idle noise, reset clicks, VGA/PS2 coexistence and supply stability. Keep
   physical results separate from simulation and timing-report claims.

Completion means the implemented source, automated checks, timing-passing
bitstream, matching software images and usage documentation are available.
Physical listening/power validation remains explicitly pending until performed.
