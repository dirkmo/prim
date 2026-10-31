# Audio register interface

`audio/rtl/audio.v` implements three tone voices and one noise voice. All
addresses below are **byte addresses**, little endian. The Olimex board enables
this peripheral with `AUDIO_ENABLE=1`; generic systems default to zero.
FFE0..FFEF remains reserved when disabled (reads zero, ignores writes).

| Address | Name | Access | Reset | Fields |
| --- | --- | --- | --- | --- |
| FFE0 | MASTER | R/W | 00 | Bit 0 output enable; bit 1 mute; bits 3:2 attenuation shift 0..3 |
| FFE1 | VOICE | R/W | 00 | Bits 1:0 select voice 0..3 |
| FFE2 | MODE | R/W | 00 | Bits 1:0 waveform: 0 pulse, 1 triangle, 2 saw, 3 silence; bit 2 one-shot envelope |
| FFE3 | VOLUME | R/W | 00 | Bits 3:0 peak amplitude 0..15 |
| FFE4 | RATE_LO | R/W | 00 | Increment bits 7:0 |
| FFE5 | RATE_MID | R/W | 00 | Increment bits 15:8 |
| FFE6 | RATE_HI | R/W | 00 | Increment bits 23:16 |
| FFE7 | DUTY | R/W | 00 | Pulse threshold 0..255 |
| FFE8 | ATTACK | R/W | 00 | Milliseconds per increasing amplitude step |
| FFE9 | DECAY | R/W | 00 | Milliseconds per decreasing amplitude step |
| FFEA | COMMAND | W, reads 0 | 00 | Bit 0 APPLY; bit 1 TRIGGER; bit 2 STOP; bit 3 STOP ALL |
| FFEB | STATUS | R | 00 | Bits 3:0 playing voices; bits 7:4 pending commands for voices 0..3 |
| FFEC..FFEF | Reserved | R/ignored W | 00 | Always read zero |

Unused bits always read zero and ignore writes. MODE through DECAY are separate
**staging banks per voice**. VOICE selects the bank for both reads and writes.
Voice 3 always uses noise; its waveform and duty fields have no sound effect.

## Commands, timing and atomicity

1. Select VOICE and write all desired staging fields.
2. Write APPLY to activate the staged configuration while retaining phase.
   In constant mode, this also sets the amplitude to VOLUME. In envelope mode,
   it preserves the current envelope progress, clamping level to the new peak;
   a zero peak stops the envelope. APPLY does not start a stopped envelope.
3. Write TRIGGER to activate staging, reset phase to zero, and start constant
   output or the one-shot envelope. Noise trigger also restores the LFSR seed.
4. STOP clears the selected voice's level/envelope at the next frame boundary.
   STOP ALL does this for all four voices. Staging and active parameters remain.

Command priority within a byte is STOP ALL > STOP > TRIGGER > APPLY. A zero
command does nothing. Pending commands commit at the next 256-clock frame
boundary. Mixer output becomes PWM duty at the following boundary, so audible
changes can take up to two frames (20.48 us at 25 MHz), excluding envelope time.

To save FPGA registers, **all audio writes wait while any command is pending**.
The bus must hold its request/data until ACK; the normal CPU and debug adapters
already do this. Reads, including STATUS, do not wait for pending commands.
This preserves command configuration without a third bank of snapshot registers.
Later commands execute in order; there is no overwrite/cancel queue. At the
board clock a blocked write waits at most one frame plus normal bus overhead.
This supersedes the original plan's nonblocking latest-command-wins queue.

A multi-byte RATE write changes staging only. No intermediate frequency reaches
playback before APPLY/TRIGGER. Byte lanes are serialized in lower-address-first
order, so a word at FFEA writes COMMAND then ignores its STATUS high byte.
Unaligned words and mixed SRAM/audio/timer words retain system bus semantics;
side effects occur once per selected lane. Neither register selection nor
configuration sequences are interrupt-safe against another audio writer;
current ISRs do not access audio. Drivers should serialize access if that changes.

## Synthesis and envelope behavior

At `CLK_HZ=25000000`, frame and PWM frequency are 97,656.25 Hz. For tone voices:

```text
increment = round(frequency_hz * 2^24 * 256 / CLK_HZ)
frequency_hz = increment * CLK_HZ / 2^32
```

Resolution is approximately 0.005820766 Hz. RATE=0 freezes phase. Restrict tone
frequencies to below half the frame rate; pulse/saw harmonics can still alias.
No band-limiting, sine table, sample memory or digital filter is implemented.

Pulse compares the upper phase byte against DUTY, producing +127 when below
and -127 otherwise. DUTY=0 is constant -127; DUTY=128 is 50%; DUTY=255 is
255/256, not constant high. Triangle folds the next eight phase bits according
to the top phase bit, then subtracts 128. Saw uses the upper phase byte minus
128. Triangle and saw span -128..127. MODE=3 produces zero.

Noise shifts a 15-bit LFSR on RATE accumulator carry. Thus the formula gives
its **update rate**, not a pitched fundamental. The recurrence is
`{state[13:0], state[14] XOR state[13]}` with seed 1 and period 32767 shifts.
Output is +127 or -127 according to bit 0. No carry means hold the noise value.

Envelope steps use a dedicated global millisecond tick (`CLK_HZ / 1000`, integer
cycles). Four voices are serviced in consecutive clocks after each tick. At the
board clock this adds at most 160 ns service latency. Each nonzero interval
counts global ticks; the first tick after a trigger can arrive in less than one
millisecond. Attack rises from 0 to VOLUME, then decay falls to zero. Attack=0
starts immediately at peak; decay=0 skips decay immediately on reaching peak.
Both zero make an enveloped trigger silent. Constant mode has no envelope.
VOLUME=0 is silent and inactive. STATUS playing includes an attack at level zero.

Each voice's level is sampled by the shared scaler once per audio frame. A
shared signed shift/add datapath applies the 4-bit level and sums all voices in
15 bits. Normalize by arithmetic shift right 6, apply MASTER attenuation shift,
saturate to -128..127, and add 128 for PWM. Negative shifts round toward minus
infinity. Maximum configured amplitude fits with headroom; arithmetic cannot
wrap. Envelope service, phase addition and amplitude scaling are shared; no
hardware multipliers or block RAM are required.

MASTER enable/mute affects output only: phase/envelopes continue. Disabled/muted
output uses midpoint duty 128, not a static low GPIO. System reset clears all
configuration, phase, levels and pending commands, seeds noise and restores
midpoint PWM. CPU halt, single-step and CPU-only debug reset preserve audio.
No audio IRQ is generated; software can poll STATUS or use the existing timer.
