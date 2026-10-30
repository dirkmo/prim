#!/usr/bin/env python3
"""First-contact UART checks and raw program loading for the Olimex board."""
import argparse
from pathlib import Path
import sys
import shlex
import time
import math

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


def prepare_image(path, skip_mmio=False, report=None):
    image = Path(path).read_bytes()
    if not 1 <= len(image) <= 65536:
        raise ValueError('Image must contain 1..65536 bytes')
    if len(image) > 0xfff0:
        if not skip_mmio:
            raise ValueError('Addresses 0xFFF0..0xFFFF are timer/reserved/LED/UART MMIO; use --skip-mmio to omit them explicitly')
        for address in range(0xfff0, len(image)):
            message = (f'Skipping address 0x{address:04X} (image byte 0x{image[address]:02x}): '
                       'system MMIO; not written or verified.')
            if report:
                report(message)
            else:
                print(message, file=sys.stderr)
        image = image[:0xfff0]
    return image


def write_delay(value):
    delay = float(value)
    if not math.isfinite(delay) or delay < 0:
        raise argparse.ArgumentTypeError('write delay must be finite and nonnegative (seconds)')
    return delay


def memory_number(value):
    """Prompt numbers are decimal unless explicitly prefixed with 0x."""
    try:
        return int(value, 16 if value.lower().startswith('0x') else 10)
    except ValueError:
        raise argparse.ArgumentTypeError(f'invalid number: {value!r}; use decimal or 0x-prefixed hex') from None


def add_commands(parser, *, console=False):
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('status', 'uart-status', 'sram-check', 'halt', 'run', 'step', 'reset-halt', 'pc'):
        commands.add_parser(command)
    read = commands.add_parser('read', help='Read bytes as a hex/ASCII dump')
    read.add_argument('address', metavar='addr', type=memory_number)
    read.add_argument('length', metavar='len', type=memory_number, nargs='?', default=1)
    write = commands.add_parser('write', help='Write consecutive bytes')
    write.add_argument('address', metavar='addr', type=memory_number)
    write.add_argument('values', metavar='byte', type=memory_number, nargs='+')
    load = commands.add_parser('load')
    load.add_argument('image', type=Path, help='Raw CPU machine-code image, not token bytes')
    load.add_argument('--run', action='store_true', help='Run after loading (and verification if requested)')
    load.add_argument('--verify', action='store_true', help='Read back and verify the loaded bytes')
    load.add_argument('--write-delay', type=write_delay, default=0,
                      help='Minimum pause between streamed word writes in seconds (default: 0)')
    load.add_argument('--skip-mmio', action='store_true',
                      help='Explicitly omit timer/reserved/LED/UART MMIO at FFF0..FFFF from writing and verification')
    if console:
        from prim_debug_uart.console import HELP
        commands.add_parser('console', description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)


def dispatch(client, args, *, image=None, report=print, progress_report=None):
    if args.command in ('read', 'write'):
        length = args.length if args.command == 'read' else len(args.values)
        if not 0 <= args.address <= 0xffff:
            raise ValueError('Address must be in 0..65535 (0xFFFF)')
        if length < 1 or args.address + length > 0x10000:
            raise ValueError('Memory range must contain at least one byte and fit in 0..65535 (0xFFFF)')
        if args.command == 'write':
            if any(not 0 <= value <= 255 for value in args.values):
                raise ValueError('Each byte must be in 0..255 (0xFF)')
            client.write_bytes(args.values, address=args.address)
            report(f'Wrote {length} bytes at 0x{args.address:04x}')
        else:
            client.set_address(args.address)
            for offset in range(0, length, 16):
                data = bytes(client.read8() for _ in range(min(16, length - offset)))
                hex_bytes = ' '.join(f'{byte:02x}' for byte in data)
                ascii_bytes = ''.join(chr(byte) if 32 <= byte < 127 else '.' for byte in data)
                report(f'{args.address + offset:04x}: {hex_bytes:47}  |{ascii_bytes}|')
    elif args.command == 'status':
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
            image = prepare_image(args.image, args.skip_mmio, report)
        if args.verify and hasattr(client, 'low_latency'):
            if client.low_latency:
                report('UART low-latency mode enabled')
            else:
                report(f'UART low-latency mode unavailable: {client.low_latency_error}')
        report('Resetting CPU and waiting for halt...')
        client.reset_halt()
        total = len(image)
        last_report = 0.0
        line_width = 0

        def inline_progress(text):
            nonlocal line_width
            print('\r' + text.ljust(line_width), end='', flush=True)
            if not text:
                print('\r', end='', flush=True)
            line_width = len(text)

        if progress_report is None:
            progress_report = inline_progress

        def progress(phase, done):
            nonlocal last_report
            now = time.monotonic()
            if done in (0, total) or now - last_report >= 1:
                progress_report(f'{phase}: {done}/{total} bytes ({100 * done // total}%)')
                last_report = now

        word_bytes = total & ~1

        def values():
            for address in range(0, word_bytes, 2):
                yield image[address] | (image[address + 1] << 8)

        try:
            progress('Writing', 0)
            if word_bytes:
                client.write_words_stream(values(), address=0, write_delay=args.write_delay,
                                          on_progress=lambda words: progress('Writing', words * 2))
            if total != word_bytes:
                client.write_bytes(image[word_bytes:], address=word_bytes)
                progress('Writing', total)
            if args.verify:
                verify_started = time.monotonic()
                progress('Verifying', 0)
                client.set_address(0)
                words = client.read_words(word_bytes // 2,
                                          on_progress=lambda done: progress('Verifying', done * 2))
                for index, actual in enumerate(words):
                    address = index * 2
                    for offset in range(2):
                        expected = image[address + offset]
                        byte = (actual >> (8 * offset)) & 255
                        if byte != expected:
                            raise RuntimeError(f'Verify failed at 0x{address + offset:04x}: {byte:02x} != {expected:02x}')
                if total != word_bytes:
                    actual = client.read8()
                    if actual != image[-1]:
                        raise RuntimeError(f'Verify failed at 0x{word_bytes:04x}: {actual:02x} != {image[-1]:02x}')
                    progress('Verifying', total)
        finally:
            progress_report('')
        if args.verify:
            elapsed = time.monotonic() - verify_started
            report(f'Verify completed in {elapsed:.2f} s ({total / max(elapsed, 1e-9):.0f} bytes/s)')
        label = 'Loaded and verified' if args.verify else 'Loaded'
        report(f'{label} {total} bytes; PC=0x{client.read_pc():04x}')
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
        dispatch(session, command, report=ui.message, progress_report=ui.progress)

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
            image = prepare_image(args.image, args.skip_mmio)
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
