; Fibonacci: eight iterations from (F0,F1)=(0,1).
; Expected: R0=F8=21, R1=F9=34, R3=0, HLT.
MOV R0, 0
MOV R1, 1
MOV R3, 8
LOOP:
    MOV R2, R0
    ADD R2, R1
    MOV R0, R1
    MOV R1, R2
    MOV R2, 1
    SUB R3, R2
    JNZ LOOP
HLT
