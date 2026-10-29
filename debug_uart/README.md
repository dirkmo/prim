# Debug UART

This component owns the complete shared serial link: RX, TX, debug command
parser, address pointer, responses, pending BREAK notifications and TX priority.
The CPU and bus multiplexer are external components. The authoritative protocol
is [docs/DRAFT.md](../docs/DRAFT.md).

| RTL module | Responsibility |
|---|---|
| `debug_uart_link` | Connect UART, controller and arbiter; derive fixed 115200-baud divider from CLK_HZ |
| `uart_rx` | Two synchronizer flops and bit-centre sampling |
| `uart_tx` | Existing unbuffered 8N1 valid/ready transmitter |
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
