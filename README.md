# prim

## The Plan

Implement a primitive stack machine and a ColorForth like language that I call __TokenForth__.

### Stack Machine

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

The CPU is implemented in file `prim.py`, a very primitive assembler/disassembler
is implemented in `primasm.py`.

### TokenForth

A tokenizer (`tokenizer.py`) parses the source code and converts it into a binary representation. This is compiled then by `tokenforth.py`. Words in immediate mode are executed during compilation by the CPU.

The TokenForth language recognizes the following token types:

#### DEFINITION
Defines a word (word as understood in Forth context). Definitions are prefixed with `:` (colon).

Example:
```
:wordname
```
This is basically like a label in a "normal" assembly language.

#### LITERALS
Literals compile raw data and are prefixed with `#`. There are two literal types, one for numbers, one for strings.

Examples:
```
#$ffff             \ compiles 0xffff
#"string literal"  \ compiles a counted string
```

#### COMPILE
Compilation tokens are compiled during compilation phase (...well, yes, it's true ;-) ).

##### COMPILE NUMBER
Compiles code that pushes a number on stack.

Example:
```
:word 1 2 3 \ define word that pushes numbers 1, 2, 3 on stack
```

##### COMPILE_STRING


##### COMPILE DEFINITION CALL
Compiles a call to a previously defined word.

Example:
```
:word1 1 2 + ; \ define word1 that adds two numbers and returns
:word2 word1 ; \ define word2 that calls word1 and returns
```

##### COMPILE DEFINITION ADDRESS
Compiles code that pushes the address of a definition on stack.

Example:
```
:word1 1 2 + ;   \ define word1
:word2 'word1 ;  \ define word2 that pushes address of word1 on stack
```

#### IMMEDIATES
Immediates are not compiled during compilation phase, but executed immediately.

The syntax is like the compilation tokens, but immediate mode must be started with `[`. Immediate mode can be ended by `]`.

##### IMMEDIATE NUMBER
```
:word1 1 [ 2 ] ; \ compile word that pushes 1 when executed.
```
During compilation of `word1`, the compiler executes `2` resulting with a 2 on top of the data stack after the compilation. When `word1` is executed, 1 is pushed onto the data stack.

##### IMMEDIATE STRING

##### IMMEDIATE WORD CALL
```
:word1 1 [ word2 ] 2 ; \ executes word2 after compiling 1, but before compiling 2.
```
##### IMMEDIATE WORD ADDRESS
```
:word1 [ 'word2 ] 1 ; \ push address of word2 on stack before compiling 1.
```

#### MNEMONICS
Mnemonics are the names of the CPU instructions.

#### BUILDINS
Buildins are tokens that are understood by the tokenizer, and will be translated somehow to CPU instructions.

|Buildin|Description|
|-------|-----------|
|`;`    |Return|
|`,`    |Compile T as number|

Semicolon (`;`) is used to return from a call to a word and, for the time being, compiles to `NOP.RET`.

Comma (`,`) takes T from stack and compiles it as a number (not number literal).

#### COMMENTS
```
:word1 1 2 and ; \ This is a comment
:word2 1 ( this is a comment ) 2 and ;
```


#### WHITE SPACE
There is also a token for white space. This is ignored by the compiler. It is included to be able to reconstruct the source code from the token representation.

### Variables
The initialization value of a variable is defined by a number literal.
A definition is used to label the address of the variable in memory.
```
:myvar #1 \ #1 is a number literal
:inc 'myvar @ 1 + 'myvar ! \ read variable from memory, increment, and store back to memory
```

### Build-in Words
The following words are predefined:
```forth
2dup
if else then
while + repeat
```

### TokenForth Examples

```forth
:min ( n1 n2 -- n )
    2dup < [ if ] drop [ else ] nip [ then ] ;
```
