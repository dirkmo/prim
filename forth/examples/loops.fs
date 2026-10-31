\ Multiline compilation, WHILE/REPEAT and UNTIL.
: countdown
  BEGIN DUP WHILE DUP . 1- REPEAT DROP
;
3 countdown CR
: down BEGIN 1- DUP 0= UNTIL ;
4 down . CR
: choose 0= IF 99 ELSE 42 THEN ;
0 choose . CR
