#!/usr/bin/env python3
"""Standalone timer tests; no imports from the host repository."""
import argparse
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TimerTests(unittest.TestCase):
    iverilog = "iverilog"
    vvp = "vvp"

    def simulate(self, top, divisor, *, invalid=False):
        with tempfile.TemporaryDirectory(prefix="timer-test-") as directory:
            binary = Path(directory) / "timer.vvp"
            compile_result = subprocess.run(
                [self.iverilog, "-g2012", "-Wall", "-s", top,
                 f"-P{top}.DIVISOR={divisor}", "-o", str(binary),
                 str(ROOT / "rtl/timer.v"), str(ROOT / f"tests/{top}.sv")],
                text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            result = subprocess.run([self.vvp, str(binary)], text=True,
                                    capture_output=True, timeout=60)
            output = result.stdout + result.stderr
            if invalid:
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("DIVISOR must be positive", output)
            else:
                self.assertEqual(result.returncode, 0, output)
                self.assertIn("PASS", output)

    def test_behavior(self):
        for divisor in (1, 2, 7, 8):
            with self.subTest(divisor=divisor):
                self.simulate("tb_timer", divisor)

    def test_dividers(self):
        for divisor in (1, 3, 255, 256, 257, 12500, 25000, 50000, 65537):
            with self.subTest(divisor=divisor):
                self.simulate("tb_timer_divider", divisor)

    def test_invalid_parameters(self):
        for divisor in (0, -1, -1000):
            with self.subTest(divisor=divisor):
                self.simulate("tb_timer_divider", divisor, invalid=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iverilog", default="iverilog")
    parser.add_argument("--vvp", default="vvp")
    args, remaining = parser.parse_known_args()
    TimerTests.iverilog = args.iverilog
    TimerTests.vvp = args.vvp
    unittest.main(argv=[__file__, *remaining])
