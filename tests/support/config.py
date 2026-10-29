"""Explicit test-tool options; argument parsing happens only at script entry."""
import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import unittest
from .paths import SIMULATOR


@dataclass(frozen=True)
class Tools:
    iverilog: str = 'iverilog'
    vvp: str = 'vvp'
    simulator: Path = SIMULATOR
    compiler_python: Path | None = None


def run_tests(test_class, *, simulator=False, compiler=False, argv=None):
    parser = argparse.ArgumentParser(description=f'Run {test_class.__name__}')
    if simulator:
        parser.add_argument('--simulator', type=Path, required=True)
    else:
        parser.add_argument('--iverilog', default='iverilog')
        parser.add_argument('--vvp', default='vvp')
    if compiler:
        parser.add_argument('--compiler-python', type=Path)
    options, remaining = parser.parse_known_args(argv)
    test_class.tools = Tools(**vars(options))
    unittest.main(module=test_class.__module__, argv=[sys.argv[0], *remaining])
