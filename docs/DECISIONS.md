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
comparisons are in `cpu/`, `debug_uart/`, `system/` and `src/prim/`. Amaranth dependencies remain optional.

### D13 – Preserve CPU memory behavior across Python and RTL

The user requires Python and hardware CPU memory accesses to behave alike.
Addresses wrap at 16 bits; there are no CPU traps for program/dictionary
collisions or memory overflow. No compiler collision checks are introduced
in this change. A host-compiler diagnostic would be a separate tool policy,
not a change to the emulated CPU, and would require a separate decision.
The debugger's existing UART RX extension is distinct from the TX-only RTL.

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
and the CLI. Existing `src/*.py` commands initially remained available through
wrappers (removed in D12).
Optional debugger and HDL dependencies are loaded only when needed. Tests
import the installed package without changing `sys.path`.

Commit: `0c89525`.

### D09 – Test helpers without import side effects

`tests/support/` groups build support, tool execution, the reference model,
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

### D12 – Remove the legacy Python tool wrappers

All implementations and library imports use `prim.*`. Remove the redundant
`src/*.py` compatibility wrappers and use `python -m prim` in the Makefile,
CLI tests and IDE launch configurations. Installed console commands remain
available. External callers of old script paths or top-level modules must
switch to the package CLI or `prim.*` imports. This supersedes the wrapper
retention in D08.

### D14 – Debugger inspection and reset are deterministic

Debugger memory/code views, disassembly and the `r` command use side-effect-free
`peek8`/`peek16` accesses. These show CPU-visible MMIO values, including the next
queued RX byte, without consuming it. CPU reads retain their UART effects.
Interactive UART text is encoded as UTF-8 bytes. Reset restores the initial
memory and UART file contents, discards interactive RX additions and temporary
step-over breakpoints, and preserves user breakpoints. Without `-u`, RX starts
empty; explicitly requested UART files must be readable.

### D15 – Keep Makefile outputs under build/src

The source Makefile writes its seven generated outputs under `build/src/`
(`OUT_DIR` can override this). Python modules, project configuration and the
Makefile itself are build dependencies. Convenience targets retain their names.
`all`, `clean` and convenience aliases are phony; failed recipes delete their
target. Clean removes only named outputs, preserving unrelated files. Legacy
outputs already under `src/` are not deleted automatically.

### D16 – Generate TokenForth opcode emitters from the ISA

The user selected comma-suffixed words without a prefix, generated by an
additional export function in `prim.isa`. The assembler's mnemonic spellings
supply names such as `+,`, `>r,` and `c@,`; opcode values remain in PrimOpcodes.
`export_tokenforth_opcodes` and `prim opcodes --format tokenforth` write the
source. The existing Verilog export and its default CLI behavior remain.

`bootstrap.cf` defines `c,` and `,`; generated `opcodes.cf` is compiled against
that image; `base.cf` imports the result. Manual single-opcode emitters are
removed from base; composite emitters use generated words. PUSH emitters write
only the opcode byte, leaving operand emission explicit. SIMEND is exported
as a simulation marker. `boot!` uses these emitters to install the reset entry
while preserving HERE. Examples and the on-CPU interpreter use this helper.
The Makefile now owns twelve outputs, extending the seven described in D15.

### D17 – Fold simple semicolon returns into the preceding instruction

Requested on 2026-10-27. The conservative first stage is implemented: simple
word endings fold the return bit into the last known instruction, including
compiler-generated PUSH operands. Compilation state survives token-by-token
interpretation in the live preview. Definitions involving Immediate mode, data,
address literals, raw operand-bearing mnemonics or explicit control transfers
retain NOP.RET. An empty definition also retains NOP.RET; final word calls are covered by D18.
Broader optimization of generated control flow remains future work.

A source `;` should set the return bit (bit 7) on the preceding instruction
when that preserves behavior, instead of always emitting a separate NOP.RET.
Retain NOP.RET when folding is unsafe or there is no suitable instruction.
The optimization must identify instruction boundaries, avoid modifying literal
or operand bytes, and preserve control-flow targets and return-stack semantics.
In particular, CALL and jump instructions cannot be assumed to honor the return
bit. Apply the behavior consistently to the normal compiler and live preview;
verify execution equivalence as well as reduced code size.


### D18 – Optimize final word calls into tail jumps

For simple definitions eligible for D17, a final compiled word call followed
by `;` replaces CALL with JP and omits NOP.RET. The callee returns directly to
the original caller and consumes no extra return-stack entry. Raw CALL
mnemonics and definitions disqualified by Immediate mode, data or control flow
retain their existing behavior. Code inspecting return addresses must account
for the eliminated frame. Live stepping retains source attribution across tail
jumps independently of the physical return stack.
