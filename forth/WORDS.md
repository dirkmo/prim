# Forth word reference

All initial kernel words are listed below. Cells are 16 bits and addresses are
byte addresses. Stack effects read left to right, with the top cell on the
right. `n` is signed, `u` unsigned, `addr` a byte address, `xt` a code address.
Arithmetic wraps modulo 65536 unless a specific error is documented.
Flags are `I` (immediate) and `C` (compile-only); a dash means neither.
For control words the table shows the compile-time effect; their runtime flag
effects are stated in the description. `S"` changes effect with STATE.

There are eight checked user data cells. The hardware data and return stacks
remain 16 cells each. Returnstack overflow has no general software trap.
Errors clear user data, discard the line and rollback an open definition;
see [the guide](README.md) for the complete input/memory contracts.

| Word | Stack effect | Flags | Meaning |
| --- | --- | --- | --- |
| `DUP` | `a -- a a` | - | Duplicate the top cell. |
| `DROP` | `a --` | - | Discard the top cell. |
| `SWAP` | `a b -- b a` | - | Exchange the top two cells. |
| `OVER` | `a b -- a b a` | - | Copy the second cell. |
| `ROT` | `a b c -- b c a` | - | Rotate three cells left. |
| `-ROT` | `a b c -- c a b` | - | Rotate three cells right. |
| `NIP` | `a b -- b` | - | Discard the second cell. |
| `2DUP` | `a b -- a b a b` | - | Duplicate a pair. |
| `2DROP` | `a b --` | - | Discard a pair. |
| `+` | `a b -- sum` | - | Add modulo 65536. |
| `-` | `a b -- difference` | - | Subtract b from a modulo 65536. |
| `AND` | `a b -- bits` | - | Bitwise AND. |
| `OR` | `a b -- bits` | - | Bitwise OR. |
| `XOR` | `a b -- bits` | - | Bitwise XOR. |
| `INVERT` | `a -- bits` | - | Invert all 16 bits. |
| `<` | `n1 n2 -- flag` | - | Signed less-than. |
| `>` | `n1 n2 -- flag` | - | Signed greater-than. |
| `U<` | `u1 u2 -- flag` | - | Unsigned less-than. |
| `@` | `addr -- cell` | - | Read a little-endian 16-bit cell; unaligned addresses are supported. |
| `!` | `cell addr --` | - | Write a 16-bit cell. |
| `C@` | `addr -- u` | - | Read an unsigned byte. |
| `C!` | `cell addr --` | - | Write the low eight bits. |
| `2*` | `a -- shifted` | - | Logical left shift by one, low 16 bits. |
| `CELLS` | `n -- bytes` | - | Multiply by two modulo 65536. |
| `1+` | `a -- a+1` | - | Increment modulo 65536. |
| `1-` | `a -- a-1` | - | Decrement modulo 65536. |
| `CELL+` | `addr -- addr+2` | - | Advance one cell. |
| `NEGATE` | `a -- -a` | - | Two's-complement negation; 8000 remains 8000. |
| `ABS` | `n -- magnitude` | - | Signed absolute value as a cell; -32768 becomes 8000. |
| `2/` | `n -- half` | - | Arithmetic right shift by one; negative odd values round downward. |
| `0=` | `a -- flag` | - | True when zero. |
| `0<>` | `a -- flag` | - | True when nonzero. |
| `0<` | `n -- flag` | - | True when signed negative. |
| `=` | `a b -- flag` | - | Equal cells. |
| `<>` | `a b -- flag` | - | Unequal cells. |
| `MIN` | `n1 n2 -- minimum` | - | Signed minimum. |
| `MAX` | `n1 n2 -- maximum` | - | Signed maximum. |
| `TRUE` | `-- flag` | - | Push FFFF. |
| `FALSE` | `-- flag` | - | Push zero. |
| `LSHIFT` | `a u -- shifted` | - | Logical left shift; u must be 0..15. |
| `RSHIFT` | `a u -- shifted` | - | Logical right shift; u must be 0..15. |
| `+!` | `cell addr --` | - | Add to the stored cell modulo 65536. |
| `*` | `a b -- product` | - | Low 16 product bits; software multiply. |
| `/MOD` | `n1 n2 -- remainder quotient` | - | Compute both signed results; zero divisor and -32768/-1 are errors. |
| `/` | `n1 n2 -- quotient` | - | Signed division, truncated toward zero. |
| `MOD` | `n1 n2 -- remainder` | - | Signed remainder, same sign as n1 unless zero. |
| `KEY` | `-- char` | - | Wait for one CPU UART byte; NUL is a valid result. |
| `EMIT` | `char --` | - | Write low seven bits to CPU UART; wait for TX credit as needed. |
| `CR` | `--` | - | Emit CRLF. |
| `SPACE` | `--` | - | Emit ASCII space. |
| `BASE` | `-- addr` | - | Address of numeric base; values 2..36 are supported. |
| `DECIMAL` | `--` | - | Set BASE to 10. |
| `HEX` | `--` | - | Set BASE to 16. |
| `\` | `--` | I | Ignore the remainder of this input line. |
| `(` | `--` | I | Skip through the next closing parenthesis on the same line; not nested. |
| `.` | `n --` | - | Print signed number in BASE followed by a space. |
| `U.` | `u --` | - | Print unsigned number in BASE followed by a space. |
| `DEPTH` | `-- u` | - | Push the previous user stack depth. |
| `.S` | `... -- ...` | - | Print depth and values bottom-to-top without consuming them; depth is also in BASE. |
| `WORDS` | `--` | - | List visible dictionary names, newest first, ending in CRLF. |
| `ABORT` | `... --` | - | Non-returning: rollback an open definition, discard stack/current line, resume input. |
| `:` | `--` | I | Parse a name and begin a hidden definition; nested definitions are rejected. |
| `;` | `--` | IC | Finish a definition, require an empty control stack, emit return and publish the header. |
| `STATE` | `-- addr` | - | Read the mode variable: 0 interpret, 1 compile; use brackets instead of writing it. |
| `IMMEDIATE` | `--` | - | Mark the latest completed user definition; kernel words are protected. |
| `[` | `--` | IC | Temporarily interpret within an open definition. |
| `]` | `--` | I | Resume compilation within an open definition. |
| `LITERAL` | `a --` | IC | Compile a checked runtime literal from the compile-time top cell. |
| `'` | `-- xt` | - | Parse the next name at execution time and return its execution token. |
| `[']` | `--` | IC | Parse the next name now and compile its XT as a checked runtime literal. |
| `EXECUTE` | `... xt -- ...` | - | Consume an XT and tail-invoke it; its stack effects and checks apply. |
| `IF` | `--` | IC | Compile a forward conditional branch; runtime consumes one flag. |
| `ELSE` | `--` | IC | Compile the alternative branch and resolve the preceding IF. |
| `THEN` | `--` | IC | Resolve a preceding IF or ELSE to the current code position. |
| `BEGIN` | `--` | IC | Remember the current loop entry. |
| `UNTIL` | `--` | IC | Close BEGIN; runtime consumes a flag and repeats when it is zero. |
| `AGAIN` | `--` | IC | Close BEGIN with an unconditional backward branch. |
| `WHILE` | `--` | IC | Within BEGIN, compile an exit branch; runtime consumes a flag and exits when zero. |
| `REPEAT` | `--` | IC | Close one BEGIN/WHILE pair with a backward branch and resolve its exit. |
| `HERE` | `-- addr` | - | Return the next free dictionary/data byte. |
| `UNUSED` | `-- u` | - | Return the remaining dictionary/data bytes (F000 minus HERE); print with U. |
| `ALLOT` | `n --` | - | Reserve 0..32767 bytes; negative values are rejected, memory is not cleared. |
| `,` | `cell --` | - | Store a cell at HERE and advance by two bytes. |
| `C,` | `cell --` | - | Store the low byte at HERE and advance by one. |
| `CREATE` | `--` | - | Parse a name and define a checked body-address word; HERE points at the uninitialized body. |
| `VARIABLE` | `--` | - | Parse a name, define a body-address word, allocate and zero one cell. |
| `CONSTANT` | `cell --` | - | Parse a name and define a checked constant-value word. |
| `TYPE` | `addr u --` | - | Emit u bytes; length zero performs no read. |
| `S"` | `-- addr u (interpret); -- (compile)` | I | Parse through the next quote. Interpret to a temporary buffer; compile persistent data and two checked runtime results. |
| `."` | `--` | I | Parse through the next quote. Print now or compile printing; preserves the user stack even at depth eight. |

## Deliberate omissions

This is a small Forth, not an implementation of a Forth standard. No DO/LOOP,
I/J, public >R/R>/R@, RECURSE, EXIT, DOES>, POSTPONE, EVALUATE, files,
CATCH/THROW, floating point or public double-cell arithmetic is provided.
Only one unmatched WHILE is allowed per BEGIN. Comments and strings must end
on their current input line. Kernel words can be shadowed by new names but
IMMEDIATE cannot modify a kernel header.

## Related documents

- [Getting started and limits](README.md)
- [Executable examples and expected results](examples/README.md)
- [Architecture](ARCHITECTURE.md)
- [Compact implementation handoff](STATUS.md)
