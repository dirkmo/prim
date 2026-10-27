"""Makefile output isolation, rebuild and clean regressions."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which('make'), 'make is required')
class BuildChecks(unittest.TestCase):
    def test_build_dependencies_and_clean(self):
        with tempfile.TemporaryDirectory(prefix='prim-build-') as directory:
            root = Path(directory)
            source = root / 'src'
            source.mkdir()
            for name in ('Makefile', 'base.cf', 'test.cf', 'interpreter.cf'):
                shutil.copy2(ROOT / 'src' / name, source / name)
            shutil.copytree(ROOT / 'src' / 'prim', source / 'prim',
                            ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copy2(ROOT / 'pyproject.toml', root / 'pyproject.toml')

            def make(*arguments):
                result = subprocess.run(['make', f'PYTHON={sys.executable}', *arguments],
                                        cwd=source, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout

            make('-j2')
            output = root / 'build' / 'src'
            generated = list(output.iterdir())
            self.assertEqual(len(generated), 7)
            self.assertFalse(list(source.glob('*.toml')))
            self.assertNotIn('-m prim', make())
            self.assertNotIn('-m prim', make('base.tf.toml'))
            for changed in (source / 'prim' / 'compiler.py',
                            source / 'prim' / 'tokenizer.py', root / 'pyproject.toml'):
                # Change only this prerequisite; unrelated inputs stay untouched.
                stamp = max(time.time_ns(), max(p.stat().st_mtime_ns for p in generated) + 1)
                os.utime(changed, ns=(stamp, stamp))
                with self.subTest(changed=changed.name):
                    commands = make('-n')
                    self.assertIn('-m prim tokenize', commands)
                    self.assertIn('-m prim compile', commands)
                    self.assertIn('-m prim export', commands)
                make()
            unrelated = output / 'keep.toml'
            unrelated.write_text('keep = true\n')
            source_input = source / 'handwritten.toml'
            source_input.write_text('keep = true\n')
            make('clean')
            self.assertEqual(list(output.iterdir()), [unrelated])
            self.assertTrue(source_input.exists())
            make('base.tf.toml')
            self.assertTrue((output / 'base.tf.toml').is_file())


if __name__ == '__main__':
    unittest.main()
