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
        self.assertEqual(result['disassembly'][-1]['instruction'], '+.RET')

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

    def test_symbolic_calls_and_base_disassembly(self):
        library = default_library()
        result = preview(':double dup + ; :main double ; main', '3', library)
        self.assertNotIn('error', result)
        self.assertEqual(result['stack'], [6])
        rows = result['disassembly']
        self.assertTrue(any(row['labels'] == ['double'] for row in rows))
        self.assertTrue(any('(double)' in row['instruction'] for row in rows))
        base = next(entry for entry in result['dictionary'] if entry['name'] == '1+')
        base_row = next(row for row in result['all_disassembly'] if row['address'] == base['address'])
        self.assertEqual(base_row['labels'], ['1+'])
        self.assertNotIn(base_row, rows)

    def test_data_word_does_not_swallow_next_label(self):
        result = preview(':value #42 :get \'value @ ; get')
        rows = result['disassembly']
        self.assertEqual(rows[0]['labels'], ['value'])
        self.assertEqual(rows[0]['instruction'], 'DATA')
        self.assertEqual(len(rows[0]['bytes']), 2)
        self.assertEqual(rows[1]['labels'], ['get'])

    def test_step_restart_and_return_stack(self):
        source = ':double dup + ; 7 double'
        first = preview(source, steps=0)
        self.assertTrue(first['paused'])
        self.assertEqual(first['stack'], [])
        self.assertEqual(first['steps'], 0)
        one = preview(source, steps=1)
        self.assertEqual(one['stack'], [7])
        self.assertEqual(one['steps'], 1)
        states = [preview(source, steps=n) for n in range(15)]
        self.assertTrue(any(state['return_stack'] for state in states))
        self.assertTrue(any(state['pc'] == first['dictionary'][-1]['address'] for state in states))
        done = states[-1]
        self.assertFalse(done['paused'])
        self.assertEqual(done['stack'], [14])
        self.assertEqual(done['return_stack'], [])
        self.assertEqual(preview(source, steps=0), first)

    def test_stepping_loop_matches_full_run(self):
        library = default_library()
        source = ':count 3 0 [ for ] i [ next ] ; count'
        full = preview(source, library=library)
        middle = preview(source, library=library, steps=20)
        self.assertTrue(middle['paused'])
        self.assertIsNotNone(middle['current_instruction'])
        stepped = preview(source, library=library, steps=full['steps'])
        self.assertFalse(stepped['paused'])
        self.assertEqual(stepped['stack'], [0, 1, 2])
        self.assertEqual(stepped['stack'], full['stack'])

    def test_invalid_step_counts(self):
        for steps in (-1, 20001, True, '1'):
            self.assertIn('error', preview('1', steps=steps))

    def test_token_step_compiles_incrementally(self):
        source = ':double dup + ; 7 double'
        first = preview(source, tokens=0)
        self.assertTrue(first['token_paused'])
        self.assertEqual(first['next_token']['text'], ':double')
        definition = preview(source, tokens=1)
        self.assertEqual(definition['dictionary'][-1]['name'], 'double')
        self.assertEqual(definition['disassembly'], [])
        body = preview(source, tokens=2)
        self.assertEqual(body['disassembly'][0]['instruction'], 'DUP')
        self.assertEqual(body['next_token']['text'], '+')
        completed = preview(source, tokens=6)
        self.assertFalse(completed['token_paused'])
        self.assertEqual(completed['stack'], [14])

    def test_token_step_immediate_and_source_positions(self):
        source = '\\ comment\n[ 7 ( skip ) dup + ] 3'
        result = preview(source, tokens=4)
        self.assertTrue(result['token_paused'])
        self.assertEqual(result['compiler_stack'], [14])
        self.assertEqual(result['stack'], [])
        token = result['next_token']
        self.assertEqual(source[token['start']:token['end']], ']')
        self.assertEqual(token['line'], 2)
        self.assertEqual(preview(source, tokens=6)['stack'], [3])

    def test_token_steps_for_immediate_loop_emitters(self):
        library = default_library()
        source = ':count 3 0 [ for ] i [ next ] ; count'
        snapshots = [preview(source, library=library, tokens=n) for n in range(13)]
        self.assertTrue(all('error' not in state for state in snapshots))
        self.assertTrue(any(state['compiler_stack'] for state in snapshots))
        self.assertEqual(snapshots[-1]['stack'], [0, 1, 2])

    def test_invalid_token_budget(self):
        for tokens in (-1, True, '1', 65537):
            self.assertIn('error', preview('1', tokens=tokens))
        self.assertIn('error', preview('1', steps=1, tokens=1))

    def test_step_reports_executed_and_next_instruction(self):
        result = preview('7 dup +', steps=1)
        self.assertEqual(result['last_instruction']['instruction'], 'PUSH8 0x7')
        self.assertEqual(result['last_instruction']['bytes'], [32, 7])
        self.assertEqual(result['current_instruction']['instruction'], 'BREAK')
        self.assertIsNone(preview('7', steps=0)['last_instruction'])
        result = preview(':w dup + ; 7 w', steps=5)
        self.assertEqual(result['last_instruction']['instruction'], 'DUP')
        self.assertEqual(result['current_instruction']['instruction'], '+.RET')

    def test_cpu_instruction_maps_to_definition_source(self):
        source = ':w dup + ; 7 w'
        result = preview(source, steps=5)
        self.assertEqual(result['last_instruction']['source']['text'], 'dup')
        self.assertEqual(result['current_instruction']['source']['text'], '+')
        span = result['last_instruction']['source']
        self.assertEqual(source[span['start']:span['end']], 'dup')
        result = preview(source, steps=1)
        self.assertEqual(result['last_instruction']['source']['text'], '7')

    def test_library_execution_maps_to_editor_call(self):
        library = default_library()
        source = ':w 1+ ; 7 w'
        states = [preview(source, library=library, steps=n) for n in range(1, 12)]
        inside = [s['last_instruction'] for s in states
                  if s.get('last_instruction', {}).get('word') == '1+']
        self.assertTrue(inside)
        self.assertTrue(all(instruction['source']['text'] == '1+' for instruction in inside))

    def test_disassembly_maps_call_instructions_to_source(self):
        source = ':double dup + ; :w double ;'
        result = preview(source)
        call_position = source.rindex('double')
        rows = [row for row in result['disassembly'] if row['source'] and
                row['source']['start'] == call_position]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]['instruction'], 'CALL')
        self.assertTrue(all(source[row['source']['start']:row['source']['end']] == 'double' for row in rows))

    def test_memory_snapshot_and_changes(self):
        import base64
        source = '$1234 $100 !'
        result = preview(source)
        memory = base64.b64decode(result['memory'])
        self.assertEqual(len(memory), 65536)
        self.assertEqual(memory[0x100:0x102], bytes([0x34, 0x12]))
        self.assertIn(0x100, result['memory_changed'])
        self.assertIn(0x101, result['memory_changed'])
        before = preview(source, steps=0)
        self.assertEqual(base64.b64decode(before['memory'])[0x100:0x102], b'\0\0')
        self.assertNotIn(0x100, before['memory_changed'])
        self.assertEqual(base64.b64decode(preview('')['memory'])[0x100], 0)

    def test_memory_includes_immediate_writes_and_runtime_error(self):
        import base64
        result = preview('[ 65 $200 c! ] +')
        self.assertIn('error', result)
        self.assertEqual(base64.b64decode(result['memory'])[0x200], 65)
        self.assertIn(0x200, result['memory_changed'])

    def test_library_memory_baseline(self):
        result = preview('', library=default_library())
        self.assertEqual(result['memory_changed'], [])
