"""Live interpreter: definitions compile, free code executes."""
import unittest
from prim.live import preview, default_library


class LiveTests(unittest.TestCase):
    def test_free_code_and_start_stack(self):
        self.assertEqual(preview('dup +', '7')['stack'], [14])
        self.assertEqual(preview('1 2 +')['stack'], [3])

    def test_definitions_only_compile(self):
        result = preview(':double dup + ;', '7')
        self.assertEqual(result['stack'], [7])
        self.assertTrue(result['disassembly'])
        self.assertEqual(result['disassembly'][-1]['instruction'], 'NOP.RET')

    def test_definition_and_call(self):
        self.assertEqual(preview(':double dup + ; 7 double')['stack'], [14])
        self.assertEqual(preview('3 :double dup + ; double 1 +')['stack'], [7])

    def test_immediate_stack_is_separate(self):
        result = preview('[ 7 dup + ] 3', '2')
        self.assertEqual(result['compiler_stack'], [14])
        self.assertEqual(result['stack'], [2, 3])

    def test_base_and_conditionals(self):
        library = default_library()
        before = bytes(library.memory)
        source = ':choose [ if ] 10 [ else ] 20 [ then ] ; 0 choose 1 choose'
        result = preview(source, library=library)
        self.assertNotIn('error', result)
        self.assertEqual(result['stack'], [20, 10])
        entries = {e['name']: e for e in result['dictionary']}
        self.assertFalse(entries['if']['new'])
        self.assertTrue(entries['choose']['new'])
        self.assertEqual(bytes(library.memory), before)

    def test_data_and_string(self):
        self.assertEqual(preview(':value #42 :get \'value @ ; get')['stack'], [42])
        result = preview('"hi" c@')
        self.assertEqual(result['stack'], [2])

    def test_errors_and_limits(self):
        for source in ('+', ':bad + ; bad', ":forever 'forever jp ; forever",
                       ":forever 'forever jp ; [ forever ]", ':unfinished 1', '[ 1', ';'):
            with self.subTest(source=source):
                self.assertIn('error', preview(source))

    def test_error_preserves_compilat(self):
        result = preview(':bad + ; bad')
        self.assertIn('error', result)
        self.assertTrue(result['disassembly'])
        self.assertEqual(result['dictionary'][-1]['name'], 'bad')

    def test_fresh_state(self):
        self.assertEqual(preview('1')['stack'], [1])
        self.assertEqual(preview('')['stack'], [])
