#!/usr/bin/env python3
"""Physical SRAM transactions and CPU/reference regression scenarios."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))

from support.config import run_tests
from support.scenarios import SramScenarios
from support.unittest_bridge import SramHarness


class SramChecks(SramScenarios, SramHarness, unittest.TestCase):
    pass


if __name__ == '__main__':
    run_tests(SramChecks)
