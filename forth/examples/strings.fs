\ Temporary and persistent strings; execution tokens.
: greet ." Hello, Forth!" ;
greet CR
: message S" A persistent string" ;
message TYPE CR
S" temporary" TYPE CR
: emitxt ['] EMIT ;
90 emitxt EXECUTE CR
