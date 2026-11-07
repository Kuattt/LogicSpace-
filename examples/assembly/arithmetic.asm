; Arithmetic: (10 + 5) - 5 = 10 in R0.
; Expected: R0=10, R1=5, Z=0, C=1, HLT.
MOV R0, 10
MOV R1, 5
ADD R0, R1
SUB R0, R1
HLT
