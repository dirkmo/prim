from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'src'
CPU_RTL = ROOT / 'cpu' / 'rtl'
DEBUG_RTL = ROOT / 'debug_uart' / 'rtl'
SYSTEM_RTL = ROOT / 'system' / 'rtl'
SOURCE_DIRS = tuple(ROOT / component / kind
                    for component in ('cpu', 'debug_uart', 'system', 'timer')
                    for kind in ('rtl', 'tests'))
BUILD = ROOT / 'build' / 'sim'
SIMULATOR = BUILD / 'simulator'
TIMINGS = ((1, 1, 3), (2, 2, 12), (3, 4, 19))


def source_path(name):
    """Resolve a unique simulation source across the RTL components."""
    matches = [directory / name for directory in SOURCE_DIRS if (directory / name).is_file()]
    if len(matches) != 1:
        raise ValueError(f'Expected one simulation source for {name!r}, found {matches}')
    return matches[0]
