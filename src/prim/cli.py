"""Command-line dispatch; importing the package never starts a command."""
import argparse
from importlib import import_module

COMMANDS = {'asm': 'assembler', 'tokenize': 'tokenizer', 'compile': 'compiler',
            'export': 'exporter', 'disasm': 'disassembler', 'debug': 'debugger',
            'opcodes': 'isa', 'live': 'live'}


def debug_main(argv=None):
    try:
        from .debugger import main
    except ModuleNotFoundError as exc:
        if exc.name != 'blessed':
            raise
        raise SystemExit('The debugger requires the debug extra: pip install -e ".[debug]"') from None
    return main(argv)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Prim CPU / TokenForth tools')
    parser.add_argument('command', choices=COMMANDS)
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == 'debug':
        return debug_main(args.arguments)
    return import_module(f'.{COMMANDS[args.command]}', __package__).main(args.arguments)
