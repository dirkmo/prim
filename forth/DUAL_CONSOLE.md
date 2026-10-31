# Shared interpreter on UART and PS/2/VGA

Implementation follows [the PS/2 work packages](../docs/PS2_CONSOLE_PLAN.md).
Each package is committed separately. Hardware AP2/AP3 already provides the
receiver, FIFO, MMIO and shared IRQ_PENDING source bits.

## AP4: output routing and integrated VGA backend

The default FPGA build (`python3 forth/build.py`) now selects the dual-console
kernel. `--uart-only` retains the original small UART-polling image for systems
without VGA/PS2; `forth/run.py` uses that profile for a host terminal. Python
`build_image()` defaults to dual; existing component fixtures explicitly request
`dual_console=False`, while dual-console checks execute the default target.

All ordinary output, including errors, prompts, number signs/spaces, EMIT,
TYPE and input echo, uses one raw emitter. `console_owner=0` selects UART;
1 selects the integrated VGA backend. User dictionary and stacks are shared.
The backend handles CR, LF, BS/DEL, line wrapping, 32-row ring scrolling,
cursor updates and display clearing. It restores every prior VGA CONTROL bit
after each mapped VRAM write, and resides below E000. It uses no extra FPGA
video storage. Eight private cells at F000..F00F are reserved initially;
software buffers and dispatcher state are added in later packages.

AP4 supplies routing/backend routines; input selection, boot prompts on both
endpoints and automatic execution ownership are completed in AP7. Kernel
images and helpers never execute inside the temporarily banked E000..EFFF
window. User definitions may still use that SRAM region between video writes.

Validation: `python3 forth/tests/test_dual.py` runs real Prim instructions
against an independent VGA/MMIO model, checking output separation, scrolling,
numeric formatting, bank restoration and physical stack bounds. Existing
UART-profile regression suites retain their original behavior.

## AP5: generic ISR and receive rings

One INTAD vector enters `irq_entry`, which starts with INTDI, saves carry once,
calls the shared source dispatcher and restores carry before INTEI.RET.
The dispatcher snapshots enabled pending sources, acknowledges each selected
bit before calling its corresponding handler, checks all sources and rescans.
UART and PS/2 handlers drain into independent 64-byte rings (63 bytes usable).
Overflow discards newest bytes and sets a sticky loss flag. PS/2 hardware
errors also set that local loss flag. Decoding and output stay in foreground.
Timer/TX are disabled at boot; their default handlers mask unexpected enabled
events and record diagnostic bits rather than looping forever.

Cold boot disables sources, drains stale hardware input, clears errors/pending,
initializes the vector/rings, then enables RX sources. CPU-only reset therefore
cannot accidentally interpret bytes retained from the previous image/session.
IRQ-private cells occupy F020..F02F. Rings reserve F100..F17F and F180..F1FF;
each uses a six-byte head/tail/loss header followed by 64 bytes of storage.

The stack constraint requires an explicit scheduling choice: **global IRQs are
enabled only inside `irq_wait`**, called by the idle collector without data
temporaries. Its INTEI/NOP/INTDI sequence bounds interruption to known kernel
states. Arbitrary Forth execution remains masked; KEY and foreground collection
call the same dispatcher synchronously. This preserves the existing eight
user cells and 16-cell stacks without claiming safe asynchronous entry during
an arbitrary 16-deep return stack or an arithmetic routine already using all
data cells. During a long-running Forth word, buffering is limited to hardware
(PS/2 16 bytes; UART one byte with host credit). Overflow is reported when
control returns. A program that never returns/reads KEY blocks both consoles.

Dispatcher/handler/enqueue code adds at most three data cells and four return
frames including CPU IRQ entry. The collector may have two call frames at
`irq_wait`: total at most six return frames and eleven data cells with eight
user cells. ISR scratch never aliases parser, arithmetic, VGA state or the
banked window. This is a safe-window policy, not general Forth multitasking.
AP7 connects these wait points; AP8 verifies injection across their boundaries.

`python3 forth/tests/test_irq.py` checks simultaneous sources, retained masked
pending, FIFO/ring wrap/loss, errors, events during dispatch, unhandled-source
masking, both carry values, eight preserved user cells and untouched arithmetic
scratch under actual Prim IRQ entry. The measured IRQ path stays within the
three-cell/four-frame additional budget.
