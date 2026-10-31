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
