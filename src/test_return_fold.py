"""Conservative semicolon folding must preserve instruction and data boundaries."""
import contextlib
import io
import unittest
from prim.compiler import compile_tokens, Mif, HERE_FETCH
from prim.tokenizer import tokenize_document
from prim.isa import PrimOpcodes as Op
from prim.live import preview, default_library


def code(source):
    with contextlib.redirect_stdout(io.StringIO()):
        image = compile_tokens(tokenize_document(source))
    memory = Mif(image.memory)
    return bytes(image.memory[14:HERE_FETCH(memory)])


class ReturnFoldTests(unittest.TestCase):
    def test_simple_endings_and_immediate_operands(self):
        self.assertEqual(code(':w dup + ;'), bytes([Op.DUP, Op.ADD | 128]))
        self.assertEqual(code(':w 3 ;'), bytes([Op.PUSH8 | 128, 3]))
        self.assertEqual(code(':w $1234 ;'), bytes([Op.PUSH | 128, 0x34, 0x12]))
        self.assertEqual(code(':w dup ( comment ) + ;'), bytes([Op.DUP, Op.ADD | 128]))

    def test_unsafe_endings_fall_back(self):
        for source in (':w ;', ':w #42 ;', ':w "hi" ;', ':w [ 1 ] dup ;',
                       ':a 1 ; :w a ;', ':w 0 jp ;', ':w 0 call ;',
                       ':w 0 jz ;', ':w int ;', ':w dup.ret ;'):
            with self.subTest(source=source):
                self.assertEqual(code(source)[-1], 128)

    def test_runtime_matches_explicit_return(self):
        for body, stack in (('dup +', '7'), ('3', ''), ('$1234', ''), ('swap -', '9 4')):
            with self.subTest(body=body):
                optimized = preview(':w ' + body + ' ; w', stack)
                explicit = preview(':w ' + body + ' nop.ret ; w', stack)
                self.assertNotIn('error', optimized)
                self.assertEqual(optimized['stack'], explicit['stack'])
                self.assertEqual(optimized['return_stack'], [])


    def test_control_flow_keeps_end_return(self):
        library = default_library()
        result = preview(':w [ if ] 10 [ else ] 20 [ then ] ; 0 w 1 w', library=library)
        self.assertEqual(result['stack'], [20, 10])
        self.assertEqual(result['disassembly'][-1]['instruction'], 'NOP.RET')
