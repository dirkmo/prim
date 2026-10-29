import json
from pathlib import Path
import re


def load_records(filename):
    records = []
    for number, line in enumerate(Path(filename).read_text().splitlines(), 1):
        try:
            records.append(json.loads(line))
        except ValueError as exc:
            raise RuntimeError(f'{filename}:{number}: invalid retirement JSON: {exc}') from exc
    return records


def final_state(output):
    if 'Simulation halted on BREAK' not in output:
        raise RuntimeError(f'Simulator did not halt on BREAK\n{output}')
    match = re.search(r'state:\s+pc=([0-9a-fA-F]+)\s+dsp=(\d+)\s+rsp=(\d+)\s+T=([0-9a-fA-F]+)\s+N=([0-9a-fA-F]+)\s+R=([0-9a-fA-F]+)\s+ir=([0-9a-fA-F]+)', output, re.IGNORECASE)
    if not match:
        raise RuntimeError(f'Simulator did not emit a final state\n{output}')
    return {key: int(value, base) for key, value, base in
            zip(('pc', 'dsp', 'rsp', 'T', 'N', 'R'), match.groups()[:6], (16, 10, 10, 16, 16, 16))}
