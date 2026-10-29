from pathlib import Path
import tempfile
from .process import run
from .reference import compare_records
from .traces import load_records, final_state


def compare(image, simulator, max_steps=1000, wait_cycles=0, wait_seed=None):
    if not image or len(image) > 65536:
        raise ValueError('Image must contain 1..65536 bytes')
    if not 0 <= wait_cycles <= 10000:
        raise ValueError('wait_cycles must be in 0..10000')
    if wait_seed is not None and not 0 <= wait_seed <= 0xffffffff:
        raise ValueError('wait_seed must be an unsigned 32-bit integer')
    with tempfile.TemporaryDirectory(prefix='prim-compare-') as directory:
        directory = Path(directory)
        binary, trace = directory / 'image.bin', directory / 'retirement.jsonl'
        binary.write_bytes(image)
        command = [simulator, '-i', binary, '-j', trace,
                   '-c', max_steps * (2 * wait_cycles + 3) + wait_cycles + 20,
                   '-w', wait_cycles]
        if wait_seed is not None:
            command += ['-s', wait_seed]
        result = run(command, cwd=directory, allowed=(0, 1))
        if not trace.exists():
            raise RuntimeError(f'Simulator did not emit a trace\n{result.stdout}\n{result.stderr}')
        records = load_records(trace)
    return compare_records(image, records, max_steps, result.returncode)


def run_final_state(image, simulator):
    with tempfile.TemporaryDirectory(prefix='prim-state-') as directory:
        binary = Path(directory) / 'image.bin'
        binary.write_bytes(image)
        result = run([simulator, '-i', binary], cwd=Path(simulator).parent, timeout=10)
    return final_state(result.stdout + result.stderr)
