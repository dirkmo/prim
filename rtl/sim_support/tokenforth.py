"""Fresh host-compiler pipelines and reusable Python environment selection."""
from pathlib import Path
import sys
from .paths import ROOT, SRC
from .process import run


def compiler_python(explicit=None):
    candidates = [explicit] if explicit is not None else [sys.executable, ROOT / '.venv' / 'bin' / 'python']
    for candidate in candidates:
        candidate = Path(candidate).absolute()  # Keep the venv symlink path.
        if candidate.is_file():
            result = run([candidate, '-c', 'import prim.artifacts'], timeout=10, allowed=(0, 1))
            if result.returncode == 0:
                return candidate
    raise RuntimeError('Install the project with pip install -e . or specify --compiler-python')


class TokenForthBuild:
    def __init__(self, directory, python=None):
        self.directory = Path(directory)
        self.python = compiler_python(python)

    def stage(self, name, module, *arguments):
        result = run([self.python, '-m', f'prim.{module}', *arguments], cwd=self.directory,
                     log=self.directory / f'{name}.log')
        if 'uart-tx:' in result.stdout:
            raise RuntimeError(f'{name}: UART output happened at compile time, not runtime')

    def compile_examples(self, names):
        self.directory.mkdir(parents=True, exist_ok=True)
        base_tokens, base_image = self.directory / 'base.tok.toml', self.directory / 'base.tf.toml'
        self.stage('base-tokenize', 'tokenizer', '-i', SRC / 'base.cf', '-o', base_tokens)
        self.stage('base-compile', 'compiler', '-i', base_tokens, '-o', base_image)
        images = {}
        for name in names:
            tokens, compiled = self.directory / f'{name}.tok.toml', self.directory / f'{name}.tf.toml'
            binary = self.directory / f'{name}.bin'
            self.stage(f'{name}-tokenize', 'tokenizer', '-i', SRC / 'examples' / f'{name}.cf',
                       '-o', tokens, '-it', base_image)
            self.stage(f'{name}-compile', 'compiler', '-i', tokens, '-o', compiled)
            self.stage(f'{name}-export', 'exporter', '-i', compiled, '-o', binary, '-s', 'memory')
            images[name] = binary.read_bytes()
        return images

    def run_regression(self, script):
        return run([self.python, SRC / script], log=self.directory / f'{script}.log')
