\ Variables, constants and raw data space.
VARIABLE total
0 total !
: sum BEGIN DUP WHILE DUP total +! 1- REPEAT DROP ;
5 sum total @ . CR
42 CONSTANT answer
answer . CR
CREATE buffer 65 C, 66 C,
buffer 2 TYPE CR
