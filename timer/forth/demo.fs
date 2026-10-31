\ Load timer.fs first. Definitions only; run TIMER-DEMO interactively.
\ Olimex board: one tick = 1 ms. Takes ownership of the timer.
: TIMER-DEMO
  TIMER-INIT
  ." Start" CR 1000 TIMER-WAIT ." One second" CR
  1000 TIMER-WAIT ." Two seconds" CR ;
