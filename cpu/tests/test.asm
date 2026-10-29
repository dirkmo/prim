; Call/return regression test.
; The subroutine starts at address 0x000a and returns to the instruction after CALL.
10
CALL
99
88
NOP
NOP
;
; subroutine entry, returns to caller
42
NOP.RET
