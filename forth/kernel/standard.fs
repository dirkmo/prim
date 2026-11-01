\ Standard-image utilities; translated by the on-CPU Forth compiler.
\ Memory scratch is private to MOVE/FILL; neither dispatches callbacks.
VARIABLE MEM-SRC VARIABLE MEM-DST VARIABLE MEM-LEFT VARIABLE MEM-BYTE
: FILL ( addr u byte -- )
  MEM-BYTE ! MEM-LEFT ! MEM-DST !
  BEGIN MEM-LEFT @ WHILE
    MEM-BYTE @ MEM-DST @ C! 1 MEM-DST +! -1 MEM-LEFT +!
  REPEAT ;
: MOVE ( src dst u -- )
  MEM-LEFT ! MEM-DST ! MEM-SRC !
  MEM-SRC @ MEM-DST @ U< IF
    MEM-LEFT @ MEM-SRC +! MEM-LEFT @ MEM-DST +!
    BEGIN MEM-LEFT @ WHILE
      -1 MEM-SRC +! -1 MEM-DST +!
      MEM-SRC @ C@ MEM-DST @ C! -1 MEM-LEFT +!
    REPEAT
  ELSE
    BEGIN MEM-LEFT @ WHILE
      MEM-SRC @ C@ MEM-DST @ C!
      1 MEM-SRC +! 1 MEM-DST +! -1 MEM-LEFT +!
    REPEAT
  THEN ;
\ Restore is interpret-only, also rejecting use inside [ ... ].
\ Cancel callbacks before reclaiming any of their possible code/data.
: M-RESTORE ( saved-here saved-latest -- )
  ?INTERPRET 0 TIMER-CALLBACK! LATEST ! DP ! ;
: MARKER ( "name" -- )
  ?INTERPRET HERE LATEST @ ['] : EXECUTE
  SWAP ['] LITERAL EXECUTE ['] LITERAL EXECUTE
  ['] M-RESTORE COMPILE, ['] ; EXECUTE ; IMMEDIATE
