\ Included in the standard dual-console IRQ image, after timer.fs.
\ Callback: ( -- ), preserve the caller's stack. Call TIMER-POLL in your loop.
: TIMER-EVERY ( ticks xt -- )
  0 TIMER-CALLBACK! SWAP TIMER-PERIOD TIMER-CALLBACK! ;
