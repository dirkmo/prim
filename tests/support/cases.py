"""Shared instruction regression vectors; importing does not run them."""
CASES = [
    (
        'call_ret_1',
        '5 call BREAK nop 2.ret',
        {'pc': 0x0004, 'dsp': 1, 'rsp': 0, 'T': 0x0002, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'call_ret_2',
        '6 nop call BREAK nop 2.ret',
        {'pc': 0x0005, 'dsp': 1, 'rsp': 0, 'T': 0x0002, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'int_isr_return',
        '7 intad int nop BREAK nop 2.ret',
        {'pc': 0x0006, 'dsp': 1, 'rsp': 0, 'T': 0x0002, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'int_preserves_data_stack',
        '7 intad 0x55 int BREAK 2.ret',
        {'pc': 0x0007, 'dsp': 2, 'rsp': 0, 'T': 0x0002, 'N': 0x0055, 'R': 0x0000},
    ),
    (
        'jp',
        '4 jp BREAK 0xff',
        {'pc': 0x0007, 'dsp': 1, 'rsp': 0, 'T': 0x00ff, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'jz_zero',
        '0 8 jz BREAK 0xfe',
        {'pc': 0x0009, 'dsp': 0, 'rsp': 0, 'T': 0x0000, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'jz_nonzero',
        '1 8 jz BREAK 0xfe',
        {'pc': 0x0006, 'dsp': 0, 'rsp': 0, 'T': 0x0000, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'stack_dup',
        '1 2 dup BREAK',
        {'pc': 0x0006, 'dsp': 3, 'rsp': 0, 'T': 0x0002, 'N': 0x0002, 'R': 0x0000},
    ),
    (
        'stack_swap',
        '1 2 swap BREAK',
        {'pc': 0x0006, 'dsp': 2, 'rsp': 0, 'T': 0x0001, 'N': 0x0002, 'R': 0x0000},
    ),
    (
        'stack_over',
        '1 2 over BREAK',
        {'pc': 0x0006, 'dsp': 3, 'rsp': 0, 'T': 0x0001, 'N': 0x0002, 'R': 0x0000},
    ),
    (
        'stack_nip',
        '1 2 nip BREAK',
        {'pc': 0x0006, 'dsp': 1, 'rsp': 0, 'T': 0x0002, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'stack_rot',
        '1 2 3 rot BREAK',
        {'pc': 0x0008, 'dsp': 3, 'rsp': 0, 'T': 0x0001, 'N': 0x0003, 'R': 0x0000},
    ),
    (
        'stack_rot_deep',
        '1 2 3 rot nip BREAK',
        {'pc': 0x0009, 'dsp': 2, 'rsp': 0, 'T': 0x0001, 'N': 0x0002, 'R': 0x0000},
    ),
    (
        'stack_nrot',
        '1 2 3 -rot BREAK',
        {'pc': 0x0008, 'dsp': 3, 'rsp': 0, 'T': 0x0002, 'N': 0x0001, 'R': 0x0000},
    ),
    (
        'stack_nrot_deep',
        '1 2 3 -rot nip BREAK',
        {'pc': 0x0009, 'dsp': 2, 'rsp': 0, 'T': 0x0002, 'N': 0x0003, 'R': 0x0000},
    ),
    (
        'stack_drop',
        '1 2 drop BREAK',
        {'pc': 0x0006, 'dsp': 1, 'rsp': 0, 'T': 0x0001, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'stack_to_r',
        '1 >r BREAK',
        {'pc': 0x0004, 'dsp': 0, 'rsp': 1, 'T': 0x0000, 'N': 0x0000, 'R': 0x0001},
    ),
    (
        'stack_rdrop',
        '1 >r 2 >r rdrop BREAK',
        {'pc': 0x0008, 'dsp': 0, 'rsp': 1, 'T': 0x0000, 'N': 0x0000, 'R': 0x0001},
    ),
    (
        'stack_from_r',
        '1 >r 2 r> BREAK',
        {'pc': 0x0007, 'dsp': 2, 'rsp': 0, 'T': 0x0001, 'N': 0x0002, 'R': 0x0000},
    ),
    (
        'alu_and',
        '0xf0f0 0x0ff0 and BREAK',
        {'dsp': 1, 'T': 0x00f0, 'N': 0x0000},
    ),
    (
        'alu_or',
        '0xf00f 0x0ff0 or BREAK',
        {'dsp': 1, 'T': 0xffff, 'N': 0x0000},
    ),
    (
        'alu_xor',
        '0xaaaa 0x0ff0 xor BREAK',
        {'dsp': 1, 'T': 0xa55a, 'N': 0x0000},
    ),
    (
        'alu_not',
        '0x0ff0 not BREAK',
        {'dsp': 1, 'T': 0xf00f, 'N': 0x0000},
    ),
    (
        'alu_sr',
        '0x8003 sr BREAK',
        {'dsp': 1, 'T': 0x4001, 'N': 0x0000},
    ),
    (
        'alu_sr_carry',
        '0x8003 sr carry BREAK',
        {'dsp': 2, 'T': 1, 'N': 0x4001},
    ),
    (
        'alu_srw',
        '0x8123 srw BREAK',
        {'dsp': 1, 'T': 0x0081, 'N': 0x0000},
    ),
    (
        'alu_srw_carry',
        '0x8123 srw carry BREAK',
        {'dsp': 2, 'T': 0, 'N': 0x0081},
    ),
    (
        'alu_sl',
        '0x4001 sl BREAK',
        {'dsp': 1, 'T': 0x8002, 'N': 0x0000},
    ),
    (
        'alu_sl_carry',
        '0x8000 sl carry BREAK',
        {'dsp': 2, 'T': 1, 'N': 0x0000},
    ),
    (
        'alu_slw',
        '0x0181 slw BREAK',
        {'dsp': 1, 'T': 0x8100, 'N': 0x0000},
    ),
    (
        'alu_slw_carry',
        '0x0181 slw carry BREAK',
        {'dsp': 2, 'T': 1, 'N': 0x8100},
    ),
    (
        'alu_add',
        '0x1234 0x0102 + BREAK',
        {'dsp': 1, 'T': 0x1336, 'N': 0x0000},
    ),
    (
        'alu_add_carry',
        '0xffff 1 + carry BREAK',
        {'dsp': 2, 'T': 1, 'N': 0x0000},
    ),
    (
        'alu_sub',
        '0x1234 0x0102 - BREAK',
        {'dsp': 1, 'T': 0x1132, 'N': 0x0000},
    ),
    (
        'alu_sub_borrow',
        '0 1 - carry BREAK',
        {'dsp': 2, 'T': 1, 'N': 0xffff},
    ),
    (
        'alu_lts_true',
        '0xffff 1 < BREAK',
        {'dsp': 1, 'T': 0xffff, 'N': 0x0000},
    ),
    (
        'alu_lts_false',
        '1 0xffff < BREAK',
        {'dsp': 1, 'T': 0x0000, 'N': 0x0000},
    ),
    (
        'alu_ltu_true',
        '1 2 <u BREAK',
        {'dsp': 1, 'T': 0xffff, 'N': 0x0000},
    ),
    (
        'alu_ltu_false',
        '2 1 <u BREAK',
        {'dsp': 1, 'T': 0x0000, 'N': 0x0000},
    ),
    (
        'memory_fetch_word',
        '0x1234 0x100 ! 0x100 @ BREAK',
        {'pc': 0x000c, 'dsp': 1, 'rsp': 0, 'T': 0x1234, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'memory_store_word',
        '0x1234 0x100 ! BREAK',
        {'pc': 0x0008, 'dsp': 0, 'rsp': 0, 'T': 0x0000, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'memory_fetch_byte_low',
        '0x1234 0x100 ! 0x100 c@ BREAK',
        {'pc': 0x000c, 'dsp': 1, 'rsp': 0, 'T': 0x0034, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'memory_fetch_byte_high',
        '0x1234 0x100 ! 0x101 c@ BREAK',
        {'pc': 0x000c, 'dsp': 1, 'rsp': 0, 'T': 0x0012, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'memory_store_byte_low',
        '0x1234 0x100 ! 0xab 0x100 c! 0x100 @ BREAK',
        {'pc': 0x0012, 'dsp': 1, 'rsp': 0, 'T': 0x12ab, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'memory_store_byte_high',
        '0x1234 0x100 ! 0xab 0x101 c! 0x100 @ BREAK',
        {'pc': 0x0012, 'dsp': 1, 'rsp': 0, 'T': 0xab34, 'N': 0x0000, 'R': 0x0000},
    ),
]
