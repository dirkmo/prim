# prim

A primitive CPU aimed to execute a colorforth like language.

## The Plan

The CPU shall have 8-bit opcodes, a 16-bit ALU, 8-bit and 16-bit memory accesses, 16-bit data and return stacks.


Example:
`0x00: call and add or` will be assembled to: `call nop and add or`
`0x01: call and add or` will be assembled to: `call and add or`

The ColorForth assembler has to make sure, that CALLs and JPs are only to even addresses.

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
@, !, c@, c!
PUSH8, PUSH
```

Only `PUSH` and `PUSH8` have immediate data.

Bit #7 of an opcode represents the return bit.

Other instructions can be added easily, since there are a lot of unused opcodes.
