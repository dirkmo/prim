\ Standard image: share the integrated VGA backend and console cursor state.
: VGA-TYPE ( addr len -- )
  BEGIN DUP WHILE SWAP DUP C@ VGA-EMIT 1+ SWAP 1- REPEAT 2DROP ;
