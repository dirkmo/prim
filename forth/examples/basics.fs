\ Basic arithmetic and conditional definitions.
: quadrat DUP * ;
7 quadrat . CR
: betrag DUP 0< IF NEGATE THEN ;
-9 betrag . CR
