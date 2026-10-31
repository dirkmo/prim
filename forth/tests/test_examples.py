"""The documented example files are executable, independently checked fixtures."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'src', ROOT / 'tests'):
    sys.path.insert(0, str(path))
from forth.build import build_image
from forth.tests.model import session
from forth.tests.rtl_console import RtlConsole

RTL = False
EXAMPLES = ROOT / 'forth/examples'


def fixtures():
    manifest = json.loads((EXAMPLES / 'expected.json').read_text())
    for name, spec in manifest.items():
        source = (EXAMPLES / name).read_bytes()
        lines = source.splitlines()
        if len(lines) != len(spec['responses']):
            raise AssertionError(f'{name}: response count differs from line count')
        expected = b'ok\r\n' + b''.join(line + b'\r\n' + response.encode('ascii')
            for line, response in zip(lines, spec['responses']))
        yield name, source, expected, spec['stack']


class ExampleChecks(unittest.TestCase):
    def test_examples_in_cpu_model(self):
        image = build_image()
        for name, source, expected, stack in fixtures():
            with self.subTest(name=name):
                self.assertTrue(all(len(line) <= 127 for line in source.splitlines()))
                output, actual, _, _ = session(image, source)
                self.assertEqual(output, expected)
                self.assertEqual(actual, stack)

    def test_documented_pipe_workflow(self):
        for name, source, expected, _ in fixtures():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run([sys.executable, str(ROOT / 'forth/run.py')],
                    input=source, capture_output=True, cwd=directory, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)

    def test_word_reference_covers_every_kernel_word_once(self):
        text = (ROOT / 'forth/WORDS.md').read_text()
        documented = re.findall(r'^\| `([^`]+)` \|', text, re.MULTILINE)
        names = [w['name'] for w in build_image().words]
        self.assertEqual(len(documented), len(set(documented)))
        self.assertEqual(set(documented), set(names))

    def test_examples_in_rtl(self):
        if not RTL:
            self.skipTest('enable executable documentation/UART checks with --rtl')
        with tempfile.TemporaryDirectory(prefix='forth-examples-') as directory:
            simulator = RtlConsole(directory, build_image())
            for name, source, expected, stack in fixtures():
                with self.subTest(name=name):
                    output, actual, _ = simulator.session(source)
                    self.assertEqual(output, expected)
                    self.assertEqual(actual, stack)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
