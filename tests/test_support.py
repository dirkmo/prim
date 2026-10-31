#!/usr/bin/env python3
"""Regression tests for the test infrastructure itself."""
from pathlib import Path
import sys
import tempfile
import unittest

from support.config import Tools
from support.paths import ROOT
from support.process import run
from support.traces import load_records, final_state


class SupportChecks(unittest.TestCase):
    def test_imports_do_not_parse_arguments_or_launch_tools(self):
        code = '''
import sys
from unittest.mock import patch
from pathlib import Path
root = Path.cwd()
for directory in ['cpu/tests', 'system/tests', 'debug_uart/tests', 'forth/tests']:
    sys.path.insert(0, str(root / directory))
sys.argv = ['embedding-application', '--unknown-option', '--compiler-python', '/missing']
with patch('argparse.ArgumentParser.parse_args', side_effect=AssertionError('parsed argv')), \\
     patch('argparse.ArgumentParser.parse_known_args', side_effect=AssertionError('parsed argv')), \\
     patch('subprocess.run', side_effect=AssertionError('launched a tool')), \\
     patch('tempfile.TemporaryDirectory', side_effect=AssertionError('created build directory')), \\
     patch('pathlib.Path.mkdir', side_effect=AssertionError('created artifacts')):
    import compare, control_flow_regressions
    import test_compare, test_memory, test_sram, test_io, test_tokenforth
    import test_debug_cpu, test_debug_uart, test_rtl, test_host
    import test_boot, test_primitives, test_parser, test_console
    import test_compiler, test_control, test_data, test_system
    import forth.test, forth.run
print('PASS imports')
'''
        result = run([sys.executable, '-c', code], cwd=ROOT)
        self.assertEqual(result.stdout.strip(), 'PASS imports')

    def test_failed_process_retains_stdout_stderr_and_exit_code(self):
        with self.assertRaises(RuntimeError) as raised:
            run([sys.executable, '-c', "import sys; print('build output'); print('compiler error', file=sys.stderr); sys.exit(7)"])
        message = str(raised.exception)
        self.assertIn('exit 7', message)
        self.assertIn('build output', message)
        self.assertIn('compiler error', message)

    def test_process_timeout_is_bounded(self):
        with self.assertRaisesRegex(RuntimeError, 'Timed out'):
            run([sys.executable, '-c', 'import time; time.sleep(5)'], timeout=0.05)

    def test_invalid_trace_reports_file_and_line(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / 'trace.jsonl'
            trace.write_text('{"kind":"step"}\nnot JSON\n')
            with self.assertRaisesRegex(RuntimeError, r'trace.jsonl:2:'):
                load_records(trace)

    def test_final_state_requires_break(self):
        state = 'state: pc=0007 dsp=2 rsp=0 T=0001 N=ffff R=0000 ir=22\n'
        with self.assertRaisesRegex(RuntimeError, 'did not halt'):
            final_state(state + 'Simulation timeout')
        self.assertEqual(final_state(state + 'Simulation halted on BREAK'),
                         {'pc': 7, 'dsp': 2, 'rsp': 0, 'T': 1, 'N': 65535, 'R': 0})

    def test_tool_options_are_independent(self):
        configured = Tools(iverilog='/custom/iverilog', compiler_python=Path('/custom/python'))
        self.assertEqual(Tools().iverilog, 'iverilog')
        self.assertIsNone(Tools().compiler_python)
        self.assertEqual(configured.iverilog, '/custom/iverilog')


if __name__ == '__main__':
    unittest.main()
