#!/usr/bin/env python3
"""First-contact UART checks and raw program loading for the Olimex board."""
import argparse
from pathlib import Path
import sys
import shlex

from prim_debug_uart import DebugUART


def check_sram(client, report=print):
    """Preserve a small scratch area; check aligned and unaligned word access."""
    address = 0x2000
    original = bytes(client.read8(address + i) for i in range(8))
    try:
        pattern = bytes([0x00, 0xff, 0x55, 0xaa, 0x12, 0x34, 0x80, 0x01])
        client.write_bytes(pattern, address=address)
        actual = bytes(client.read8(address + i) for i in range(8))
        if actual != pattern:
            raise RuntimeError(f'SRAM byte check failed: {actual.hex()} != {pattern.hex()}')
        client.write_words([0xba21, 0xdc43], address=address + 1)
        words = [client.read16(address + 1), client.read16(address + 3)]
        if words != [0xba21, 0xdc43]:
            raise RuntimeError(f'SRAM unaligned word check failed: {words}')
    finally:
        client.write_bytes(original, address=address)
    report('SRAM byte/unaligned-word check passed; scratch bytes restored')


def prepare_image(path, skip_uart_mmio=False, report=None):
    image = Path(path).read_bytes()
    if not 1 <= len(image) <= 65536:
        raise ValueError('Image must contain 1..65536 bytes')
    if len(image) > 0xfffe:
        if not skip_uart_mmio:
            raise ValueError('Addresses 0xFFFE/0xFFFF are UART MMIO; use --skip-uart-mmio to omit them explicitly')
        for address in range(0xfffe, len(image)):
            message = (f'Skipping address 0x{address:04X} (image byte 0x{image[address]:02x}): '
                       'UART MMIO; not written or verified.')
            if report:
                report(message)
            else:
                print(message, file=sys.stderr)
        image = image[:0xfffe]
    return image


def add_commands(parser, *, console=False):
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('status', 'uart-status', 'sram-check', 'halt', 'run', 'step', 'reset-halt', 'pc'):
        commands.add_parser(command)
    load = commands.add_parser('load')
    load.add_argument('image', type=Path, help='Raw CPU machine-code image, not token bytes')
    load.add_argument('--run', action='store_true', help='Run only after verified loading')
    load.add_argument('--skip-uart-mmio', action='store_true',
                      help='Explicitly omit FFFE/FFFF from writing and verification')
    if console:
        from prim_debug_uart.console import HELP
        commands.add_parser('console', description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)


def dispatch(client, args, *, image=None, report=print):
    if args.command == 'status':
        status = client.status()
        report(f'halted={status.halted} break={status.break_reason}')
        if status.halted:
            report(f'pc=0x{client.read_pc():04x}')
    elif args.command == 'uart-status':
        status = client.uart_status()
        report(f'rx_received={status.received} tx_free={status.tx_free}')
    elif args.command in ('step', 'pc'):
        if not client.status().halted:
            raise RuntimeError(f'{args.command} requires a halted CPU; use halt or reset-halt first')
        if args.command == 'step':
            client.step()
        report(f'pc=0x{client.read_pc():04x}')
    elif args.command in ('halt', 'run', 'reset-halt'):
        getattr(client, args.command.replace('-', '_'))()
        report('CPU running' if args.command == 'run' else 'CPU halted')
    elif args.command == 'sram-check':
        client.halt()
        check_sram(client, report)
    elif args.command == 'load':
        if image is None:
            image = prepare_image(args.image, args.skip_uart_mmio, report)
        client.reset_halt()
        client.write_bytes(image, address=0)
        for address, expected in enumerate(image):
            actual = client.read8(address)
            if actual != expected:
                raise RuntimeError(f'Verify failed at 0x{address:04x}: {actual:02x} != {expected:02x}')
        report(f'Loaded and verified {len(image)} bytes; PC=0x{client.read_pc():04x}')
        if args.run:
            client.run()
            report('CPU running')


class ConsoleParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message + '; use help for commands')

    def print_help(self, file=None):
        raise ValueError(self.format_help())


def run_console(args):
    from prim_debug_uart.console import Console
    from prim_debug_uart.session import UARTSession

    parser = ConsoleParser(prog='debug')
    add_commands(parser)
    # stop is a local alias. It never becomes CPU-channel text.
    def execute(text):
        tokens = shlex.split(text)
        if tokens and tokens[0] == 'stop':
            tokens[0] = 'halt'
        command = parser.parse_args(tokens)
        dispatch(session, command, report=ui.message)

    ui = Console(execute)
    session = UARTSession.connect(args.port, timeout=args.timeout,
                                  on_output=ui.cpu_output, on_break=lambda: ui.message('[BREAK]'))
    try:
        ui.run(session)
    finally:
        session.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='/dev/serial/by-id/... for the UART adapter')
    parser.add_argument('--timeout', type=float, default=2.0)
    add_commands(parser, console=True)
    args = parser.parse_args(argv)
    image = None
    if args.command == 'load':
        try:
            image = prepare_image(args.image, args.skip_uart_mmio)
        except ValueError as exc:
            parser.error(str(exc))
    if args.command == 'console':
        run_console(args)
        return
    client = DebugUART.connect(args.port, timeout=args.timeout)
    try:
        dispatch(client, args, image=image)
    finally:
        client.transport.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, TimeoutError, ImportError, ValueError) as exc:
        sys.exit(str(exc))
