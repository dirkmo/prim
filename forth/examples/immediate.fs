\ Immediate words execute while compiling the next definition.
: forty-two 42 ; IMMEDIATE
: answer forty-two LITERAL ;
answer . CR
: mode STATE @ ; IMMEDIATE
: compiled-mode mode LITERAL ;
compiled-mode . CR
