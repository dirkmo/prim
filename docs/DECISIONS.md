# Decisions

As of October 27, 2026. This log distinguishes explicit user requirements from
implemented technical choices. New entries should record the decision, its
rationale and its consequences. See [PROJECT_KNOWLEDGE.md](PROJECT_KNOWLEDGE.md)
for architecture and development commands.

## Explicit user requirements

### D01 – Keep the CPU minimal; do not reset stack arrays

The CPU should remain as minimal as possible. Data-stack and return-stack
storage is therefore not reset. Unused cells are undefined; software and
comparisons must not assume that they contain zero. Control registers needed
for execution are still reset. A stack reset should not be introduced as a
supposed bug fix.

### D02 – Carry holds the last bit shifted out

Shifts use the same semantics in Python and RTL:

| Instruction | Carry from the original operand |
|-------------|---------------------------------|
| SR | Bit 0 |
| SRW | Bit 7 |
| SL | Bit 15 |
| SLW | Bit 8 |

The user explicitly selected this behavior, which can be wired directly in
RTL. ADD sets carry on overflow, SUB on borrow; other instructions preserve
carry. CARRY pushes its value as 0 or 1.

### D03 – SRAM has no FPGA-controlled byte enables

The board connection permits only physical whole-word accesses. The controller
must implement byte accesses and unaligned word accesses using these transfers.
Partial writes therefore require read-modify-write, even though this takes
additional cycles. Neighboring bytes must be preserved.

### D04 – Focus current work on Verilog and Python

The user excluded `hdl/` from the current scope. Active implementation and
comparisons are in `rtl/` and `src/prim/`. Amaranth dependencies remain optional.

## Implemented technical choices

### D05 – Compare behavior after instruction completion

Python serves as an executable reference model. RTL may need multiple clocks
and memory wait cycles for an instruction. Comparisons check architectural
state and memory effects after instruction completion. Additional independent
expected values and SRAM/UART models check cases where both implementations
could share the same error.

### D06 – Complete memory transfers through ACK

The CPU holds requests stable until acknowledgment. This allows the SRAM
controller to perform whole-word transfers and read-modify-write, and allows
UART writes to wait while the transmitter is busy. The controller uses the
stable CPU signals and a shared data buffer instead of registering every
request separately.

### D07 – Map UART TX to byte address `0xffff`

The integrated RTL follows the compiler's memory model: writing to `0xffff`
sends a byte; reading accesses SRAM. There is currently no FIFO. ACK confirms
acceptance of the byte, not completion of the serial frame. Word accesses
are handled in CPU byte-lane order.

### D08 – Installable Python package with compatible tool entry points

Implementations live under `src/prim/`; `pyproject.toml` defines installation
and the CLI. Existing `src/*.py` commands remain available through wrappers.
Optional debugger and HDL dependencies are loaded only when needed. Tests
import the installed package without changing `sys.path`.

Commit: `0c89525`.

### D09 – Test helpers without import side effects

`rtl/sim_support/` groups build support, tool execution, the reference model,
traces and simulation. Test modules do not import other test modules, parse
arguments or start builds on import. Configuration is passed explicitly.
This supports both direct script execution and test discovery.

Commit: `f3a5159`.

### D10 – Shared document models and I/O boundary

`TokenDocument` and `ProgramImage` centralize structural validation and data
ownership. Byte buffers become `bytes`, symbol/address lists become tuples,
and metadata is copied. `from_mapping` and `to_mapping` preserve the existing
dictionary interfaces; TOML field names and document types remain compatible.
The compiler continues to validate token semantics.

Symbol tables and dictionaries belong to each compilation instead of global
class state. Input libraries are not modified. Immediate execution is bounded
so that faulty words cannot block compilation indefinitely.

Commit introducing the shared models: `d67e3b4`.

### D11 – Read TOML with the standard library; write with `tomli-w`

Requiring Python 3.11 or newer makes `tomllib` available for reading. `tomli-w`
handles writing. The old `toml` dependency and its comma-symbol workaround
have been removed. Existing valid TOML files remain readable; formatting may
change when saved. Empty symbol names are errors and are no longer repaired
by interpreting them as commas.

Commit: `4badd43`.
