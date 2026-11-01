\ Standard-image timer driver. UART-only: load line by line over UART.
\ Takes ownership of the timer; leaves CPU/console IRQs alone.
\ Durations are unsigned hardware ticks (1 ms on the Olimex 25 MHz build).
HEX
: TIMER-COUNT@ ( -- u ) FFF0 @ ;
: TIMER-COUNT! ( u -- ) FFF0 ! ;
: TIMER-COMPARE@ ( -- u ) FFF2 @ ;
: TIMER-COMPARE! ( u -- ) FFF2 ! ;
: TIMER-STOP ( -- ) FFF4 C@ 2 AND FFF4 C! ;
: TIMER-START ( -- ) FFF4 C@ 2 AND 1 OR FFF4 C! ;
: TIMER-RESET ( -- ) 0 TIMER-COUNT! ;
: TIMER-DONE? ( -- flag ) TIMER-COUNT@ TIMER-COMPARE@ = ;
\ Free-running modulo 65536, without timer IRQs.
: TIMER-INIT ( -- )
  0 FFF4 C! FFFF TIMER-COMPARE! TIMER-RESET 3 FFF4 C! ;
\ A zero-duration one-shot is already done; COUNT remains zero.
: TIMER-ONCE ( ticks -- )
  0 FFF4 C! TIMER-COMPARE! TIMER-RESET 1 FFF4 C! ;
\ AUTO period is COMPARE+1. Zero/one ticks cannot form a running period.
: TIMER-PERIOD ( ticks -- )
  DUP 2 U< IF DROP ABORT THEN
  0 FFF4 C! 1- TIMER-COMPARE! TIMER-RESET 3 FFF4 C! ;
\ Requires TIMER-INIT mode and no concurrent reconfiguration.
\ Subtract successive elapsed deltas so long waits also work across wrap.
\ Poll at least once per 65536 ticks; this is a busy wait, not a scheduler.
: TIMER-WAIT ( ticks -- )
  TIMER-COUNT@ BEGIN OVER WHILE
    TIMER-COUNT@ SWAP OVER SWAP - ROT
    2DUP U< IF SWAP - SWAP ELSE 2DROP 0 SWAP THEN
  REPEAT 2DROP ;
DECIMAL
