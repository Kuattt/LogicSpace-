; Loop: count from 0 to 5 using CMP and JNZ.
; Expected: R0=5, R2=5, HLT.
MOV R0, 0
MOV R1, 1
MOV R2, 5
LOOP:
    ADD R0, R1
    CMP R0, R2
    JNZ LOOP
HLT
