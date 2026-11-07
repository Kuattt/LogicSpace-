; Memory: store 42 at RAM address 0x20, then load it again.
; Expected: R0=42, RAM[0x20]=42, HLT.
MOV R0, 42
STORE R0, 0x20
MOV R0, 0
LOAD R0, 0x20
HLT
