\ One tick = 1 ms on the 25 MHz board. Requires a running AUTO timer.
\ No reconfiguration during MS; sample at least once per timer period.
: MS-STEP ( previous -- current elapsed )
  TIMER-COUNT@ DUP ROT
  2DUP U< IF - TIMER-COMPARE@ 1+ + ELSE - THEN ;
: MS ( u -- )
  DUP IF
    TIMER-COUNT@
    BEGIN OVER WHILE
      TIMER-POLL
      65524 C@ 3 AND 3 <> TIMER-COMPARE@ 0= OR IF ABORT THEN
      MS-STEP ROT
      2DUP U< IF SWAP - SWAP ELSE 2DROP 0 SWAP THEN
    REPEAT 2DROP
  ELSE DROP THEN ;
