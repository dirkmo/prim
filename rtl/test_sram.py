#!/usr/bin/env python3
"""Physical SRAM transactions and CPU/reference regression scenarios."""
import unittest
from sim_support.config import run_tests
from sim_support.scenarios import SramScenarios
from sim_support.unittest_bridge import SramHarness


class SramChecks(SramScenarios, SramHarness, unittest.TestCase):
    pass


if __name__ == '__main__':
    run_tests(SramChecks)
