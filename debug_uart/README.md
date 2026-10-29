# Debug UART

This component owns the complete shared serial link: RX, TX, debug command
parser, address pointer, responses, pending BREAK notifications and TX priority.
The CPU and bus multiplexer are external components. The authoritative protocol
is [docs/DRAFT.md](../docs/DRAFT.md).

| RTL module | Responsibility |
|---|---|
| `debug_uart_link` | Connect UART, controller and arbiter; derive fixed 115200-baud divider from CLK_HZ |
| `uart_rx` | Two synchronizer flops and bit-centre sampling |
| `uart_tx` | 8N1 valid/ready transmitter; completes its current frame |
| `uart_buffers` | One retained RX byte/valid flag and one pending CPU TX byte |
| `debug_uart` | Debug parser, master bus requests, responses and BREAK pending state |
| `uart_arbiter` | Debug priority over seven-bit normal output at TX acceptance boundaries |

`debug_uart_link` exposes CPU control/status and a 16-bit debug master bus.
The system grants bus ownership only at confirmed CPU halt. Normal CPU output
uses `i_output_data[6:0]`, `i_output_valid`, `o_output_ready`. There are no
CPU-opcode dependencies or MMIO address decisions in this component. The
UART transmitter completes every accepted frame before accepting another one.

The host implementation lives in `python/prim_debug_uart/`. Installing the
root project installs it along with `prim`; both imports work:

```python
from prim_debug_uart import DebugUART
# Compatibility for existing callers:
from prim.debug_uart import DebugUART
```

From the project root:

```sh
python debug_uart/tests/test_rtl.py
python debug_uart/tests/test_host.py
```

The tests cover TX/RX, arbitration with backpressure and an in-progress frame,
and the host API. Complete CPU/SRAM/debug integration belongs to `system/tests`;
CPU instruction-boundary controls belong to `cpu/tests`. Shared test helpers
live in the root `tests/support` directory.

`docs/initial_design.md` preserves the original proposal as historical material;
it is superseded by the implemented protocol linked above.

## Concurrent console and UART buffers

Channel-0 input updates the retained CPU RX register independently of the debug
parser. Consumption clears only its received flag; new reception wins over a
simultaneous read. System reset clears buffers, CPU-only reset does not. UART
status bit 0 is RX received, bit 1 is pending-TX-free (the UART frame may still
be active). The new debug command `q` returns `K` plus this status nibble without
acquiring the CPU bus. All existing debug replies and BREAK retain priority.

`prim_debug_uart.session.UARTSession` owns the serial port with one continuous
RX thread. It dispatches CPU output and BREAK even while idle or waiting for a
reply. A separate input sender queries `q`, sends one seven-bit CPU byte only
when RX is free, then releases the transaction lock while waiting for credit.
All debug operations are serialized, including whole persistent write bursts;
credit polls never interrupt an address or write mode. Console loads additionally
use `transact()` around the whole load. Reader callbacks must not block or start
debug operations themselves. With an output callback, CPU output is streamed
rather than retained indefinitely in memory. Protocol timeouts/invalid replies
stop the session to avoid reusing a late reply as a subsequent response.

The reusable POSIX UI is `prim_debug_uart.console.Console`. Ctrl+J opens a local
prompt; Ctrl+D quits either mode without changing CPU state; Ctrl+V quotes the
next CPU byte. Empty Enter returns to CPU mode; normal Enter is CPU input.
The terminal runs with raw input so Enter (CR) and Ctrl+J (LF) remain distinct.
Output and BREAK continue during command entry, help, blocked CPU input or an
outstanding debug operation. Terminal attributes are restored on exit.

Run the session/PTY tests with `python debug_uart/tests/test_session.py`. They
are registered in CTest as `uart_session_checks`. FPGA integration and CLI
entrypoints remain in `system/` and `boards/` respectively.
