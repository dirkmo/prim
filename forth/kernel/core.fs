\ Higher kernel words, compiled by the same Prim Forth compiler as user code.
: 2DUP OVER OVER ;
: 2DROP DROP DROP ;
: 1+ 1 + ;
: 1- 1 - ;
: CELL+ 2 + ;
: NEGATE 0 SWAP - ;
: SPACE 32 EMIT ;
: CR 13 EMIT 10 EMIT ;
