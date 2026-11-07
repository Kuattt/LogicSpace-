; Stack: PUSH a value, CALL a subroutine, RET, then POP the value.
; Expected: R0=14, R2=7, SP=0xFF, RAM[0xFF]=7, HLT.
MOV R0, 7
PUSH R0
CALL DOUBLE
POP R2
HLT

DOUBLE:
    MOV R1, R0
    ADD R0, R1
    RET
