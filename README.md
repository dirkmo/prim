# prim

A primitive CPU aimed to execute a colorforth like language.

## The Plan

The CPU shall have 8-bit opcodes, a 16-bit ALU, 16-bit memory accesses, 16-bit data and return stacks.

The PC is 17-bits, the upper 16-bits are used to address memory, the LSB tells the decoder to execute the lower or upper byte of the 16-bit memory word.

## Instructions

I will start the implementation with the following instructions:

```asm
NOP
CALL
JP, JPZ
AND, OR, XOR, NOT, LSR, LSL
ADD, SUB, CARRY
<, <u
SWAP, OVER, DUP, NIP, ROT, -ROT, DROP, RDROP
>R, R>
INTR
@, !
PUSH8, PUSH
```

Only `PUSH` and `PUSH8` have immediate data.

Bit #7 of an opcode represents the return bit.

Other instructions can be added easily, since there are a lot of unused opcodes.

I do not want hw byte addressing, that must be handled in sw.
