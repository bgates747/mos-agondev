.ASSUME ADL = 1
SECTION TEXT
WAIT: MACRO VALUE
$$again: ld a,VALUE
jr nz,$$again
ENDMACRO
SCOPE
entry:
$named: WAIT 1
jr $F
$$: db %AA
jr $named
SCOPE
loop?: djnz loop?
DL 0x12345678
DW24 0xabcdef
END
db "ignored after END"
