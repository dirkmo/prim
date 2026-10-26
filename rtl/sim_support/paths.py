from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / 'rtl'
SRC = ROOT / 'src'
BUILD = ROOT / 'build' / 'rtl'
SIMULATOR = BUILD / 'simulator'
TIMINGS = ((1, 1, 3), (2, 2, 12), (3, 4, 19))
