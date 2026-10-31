#!/usr/bin/env python3
"""Run independent Forth regression suites and retain their logs/report."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SUITES = ('boot', 'primitives', 'parser', 'console', 'compiler', 'control', 'data', 'system', 'examples')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    parser.add_argument('--iverilog', default='iverilog')
    parser.add_argument('--vvp', default='vvp')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/forth-tests')
    args = parser.parse_args()
    env = dict(os.environ)
    if args.rtl:
        for name in ('iverilog', 'vvp'):
            path = shutil.which(getattr(args, name))
            if path is None:
                parser.error(f'{name} not found: {getattr(args, name)}')
            env['FORTH_' + name.upper()] = str(Path(path).resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'rtl': args.rtl, 'python': sys.executable,
              'tools': {k: v for k, v in env.items() if k in ('FORTH_IVERILOG', 'FORTH_VVP')},
              'suites': []}
    report_path = output / 'report.json'

    def save():
        report_path.write_text(json.dumps(report, indent=2) + '\n')

    save()  # Replace any previous green report before attempting a rebuild.
    failures = 0
    commands = [('build', [sys.executable, str(ROOT / 'forth/build.py'), '--output', str(output / 'kernel')])]
    commands += [(name, [sys.executable, str(ROOT / f'forth/tests/test_{name}.py'),
                         *(['--rtl'] if args.rtl else []), '-v']) for name in SUITES]
    for name, command in commands:
        env['FORTH_TEST_ARTIFACTS'] = str(output / 'artifacts' / name)
        log = output / (name + '.log')
        start = time.monotonic()
        with log.open('w') as stream:
            try:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=300)
                code = result.returncode
            except (subprocess.TimeoutExpired, OSError) as exc:
                stream.write(f'\n{exc}\n')
                code = -1
        text = log.read_text(errors='replace')
        ran = re.search(r'Ran (\d+) tests?', text)
        skipped = re.search(r'OK \(skipped=(\d+)\)', text)
        entry = {'suite': name, 'command': command, 'exit_code': code,
                 'seconds': round(time.monotonic() - start, 3), 'log': str(log),
                 'tests': int(ran[1]) if ran else 0, 'skipped': int(skipped[1]) if skipped else 0}
        report['suites'].append(entry)
        failures += int(code != 0)
        save()
        print(f'{"PASS" if code == 0 else "FAIL"} {name}: {entry["tests"]} tests, '
              f'{entry["skipped"]} skipped ({entry["seconds"]}s)', flush=True)
        if code:
            print(text[-6000:], file=sys.stderr, flush=True)
    report['status'] = 'failed' if failures else 'passed'
    report['tests'] = sum(item['tests'] for item in report['suites'])
    report['skipped'] = sum(item['skipped'] for item in report['suites'])
    save()
    print(f'Report: {report_path}', flush=True)
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
