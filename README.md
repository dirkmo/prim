# prim

## Project knowledge and decisions

Repository context is documented in
[Project knowledge](docs/PROJECT_KNOWLEDGE.md) covers architecture, workflows and open
work; [Decisions](docs/DECISIONS.md) records requirements and technical
decisions with their rationale.

## Python development setup

Python 3.11 or newer is required. Install the local package and activate its
environment from the repository root:

```sh
bash setup.sh
source .venv/bin/activate
prim --help
```

`pyproject.toml` declares the runtime dependency (`tomli-w`) and command-line tools.
`pip install -e .` installs the tools in editable mode. Optional dependencies
are separate: `pip install -e '.[debug]'` adds the terminal debugger;
`pip install -e '.[hdl]'` adds the existing Amaranth tools. Neither is needed
for the TokenForth compiler or Verilog simulations.

The Python implementations live in `src/prim/`:

```text
prim/
    cpu.py             Python CPU and memory interface
    isa.py             Existing opcode constants and Verilog export
    assembler.py       Assembly and binary disassembly
    tokenizer.py       Scanner and source tokenization
    compiler.py        TokenForth compilation
    artifacts.py       Token/program models, validation and TOML/binary I/O
    tokens.py          Token encoding
    errors.py          Compiler diagnostics
    exporter.py        TOML section -> binary export
    disassembler.py    Annotated program-image disassembly
    debugger.py        Optional terminal debugger
    cli.py             Command-line dispatch
```

Use `prim asm`, `prim tokenize`, `prim compile`, `prim export`, `prim disasm`,
`prim opcodes`, or `prim debug`. Separate `prim-asm`, `prim-tokenize`,
`prim-compile`, `prim-export`, `prim-disasm`, `prim-opcodes`, and `prim-debug`
commands are also available. `python -m prim` exposes the same subcommands.
Each command accepts `--help`.

The old `src/*.py` tool wrappers have been removed. Use, for example,
`python -m prim compile ...` instead of `python src/tokenforth.py ...`.
The Makefile uses the package CLI in the active environment. Library imports
use `prim.cpu`, `prim.tokenizer`, `prim.compiler`, etc. The RTL tests import the installed package without modifying `sys.path`.
See [rtl/README.md](rtl/README.md) for simulation and end-to-end tests.

## The Plan

Implement a primitive stack machine and a ColorForth like language that I call __TokenForth__.

## Stack Machine

The CPU has 8-bit opcodes, a 16-bit ALU, 8-bit and 16-bit memory accesses, 16-bit data and return stacks. It implements the basic Forth instructions.

```asm
NOP
CALL
JP, JPZ
AND, OR, XOR, NOT, SR, SL, SRW, SLW
+, -, CARRY
<, <u
SWAP, OVER, DUP, NIP, ROT, -ROT, DROP, RDROP
>R, R>
@, !, c@, c!
PUSH8, PUSH
```

Only `PUSH` and `PUSH8` have immediate data.

Bit #7 of an opcode represents the return bit.

Other instructions can be added easily, since there are a lot of unused opcodes.

The Python CPU is implemented in `src/prim/cpu.py`; the assembler/disassembler
is implemented in `src/prim/assembler.py`.

## TokenForth

A tokenizer (`src/prim/tokenizer.py`) parses the source code and converts it into a binary representation. This is compiled by `src/prim/compiler.py`. Words in immediate mode are executed during compilation by the CPU.

The TokenForth language recognizes the following token types:

### DEFINITION
Defines a word (word as understood in Forth context). Definitions are prefixed with `:` (colon).

Example:
```
:wordname
```
This is basically like a label in a "normal" assembly language.

### LITERALS
Literals compile raw data and are prefixed with `#`. There are two literal types, one for numbers, one for strings.

Examples:
```
#$ffff             \ compiles 0xffff
#"string literal"  \ compiles a counted string
```

### COMPILE
Compilation tokens are compiled during compilation phase (...well, yes, it's true ;-) ).

#### COMPILE NUMBER
Compiles code that pushes a number on stack.

Example:
```
:word 1 2 3 \ define word that pushes numbers 1, 2, 3 on stack
```

#### COMPILE_STRING


#### COMPILE DEFINITION CALL
Compiles a call to a previously defined word.

Example:
```
:word1 1 2 + ; \ define word1 that adds two numbers and returns
:word2 word1 ; \ define word2 that calls word1 and returns
```

#### COMPILE DEFINITION ADDRESS
Compiles code that pushes the address of a definition on stack.

Example:
```
:word1 1 2 + ;   \ define word1
:word2 'word1 ;  \ define word2 that pushes address of word1 on stack
```

### IMMEDIATES
Immediates are not compiled during compilation phase, but executed immediately.

The syntax is like the compilation tokens, but immediate mode must be started with `[`. Immediate mode can be ended by `]`.

#### IMMEDIATE NUMBER
```
:word1 1 [ 2 ] ; \ compile word that pushes 1 when executed.
```
During compilation of `word1`, the compiler executes `2` resulting with a 2 on top of the data stack after the compilation. When `word1` is executed, 1 is pushed onto the data stack.

#### IMMEDIATE STRING

#### IMMEDIATE WORD CALL
```
:word1 1 [ word2 ] 2 ; \ executes word2 after compiling 1, but before compiling 2.
```
#### IMMEDIATE WORD ADDRESS
```
:word1 [ 'word2 ] 1 ; \ push address of word2 on stack before compiling 1.
```

### MNEMONICS
Mnemonics are the names of the CPU instructions.

### BUILDINS
Buildins are tokens that are understood by the tokenizer, and will be translated somehow to CPU instructions.

|Buildin|Description|
|-------|-----------|
|`;`    |Return|

Semicolon (`;`) is used to return from a call to a word and, for the time being, compiles to `NOP.RET`.

### COMMENTS
```
:word1 1 2 and ; \ This is a comment
:word2 1 ( this is a comment ) 2 and ;
```


### WHITE SPACE
There is also a token for white space. This is ignored by the compiler. It is included to be able to reconstruct the source code from the token representation.

## Variables
The initialization value of a variable is defined by a number literal.
A definition is used to label the address of the variable in memory.
```
:myvar #1 \ #1 is a number literal
:inc 'myvar @ 1 + 'myvar ! \ read variable from memory, increment, and store back to memory
```

## Build-in Words
The following words are predefined:

```forth
1+ 1-
2dup 2drop
```

Looping words:
```
if else then
while repeat
do loop
```

All looping words have to be executed immediately.

### while repeat
`while repeat` loops until the flag is 0. `while` will consume the flag.

```
:test flag [ while ] flag [ repeat ] ;
```

### do loop
`do loop` loops n times. The counter is kept on the return stack.

This will execute 3 NOPs:
```
:test 3 [ do ] nop [ loop ] ;
```


### for next
not yet implemented

`for next` works similar to a for loop in C. `for` consumes stop and start values. The loop counter can be retrieved with `i`.

This will print ABC on UART (`tx` pops a value and send it via UART):
```
:test 3 0 [ for ] 65 i + tx [ next ] ;
```

## TokenForth Examples

```forth
:min ( n1 n2 -- n )
    2dup < [ if ] drop [ else ] nip [ then ] ;
```

Hello World, for the time being implemented with "while repeat".
```forth
:msg "Hello, World!" ;
:count dup 1+ swap c@ ;
:tx $ffff c! ;
:type dup [ while ] 1- >r dup c@ tx 1+ r> dup [ repeat ] 2drop ;
[ msg count type ]
```
