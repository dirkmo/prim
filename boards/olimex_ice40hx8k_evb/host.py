#!/usr/bin/env python3
"""First-contact UART checks and raw program loading for the Olimex board."""
import argparse
from pathlib import Path
import sys

from prim_debug_uart import DebugUART


def check_sram(client):
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
    print('SRAM byte/unaligned-word check passed; scratch bytes restored')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='/dev/serial/by-id/... for the separate UART adapter')
    parser.add_argument('--timeout', type=float, default=2.0)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    commands.add_parser('sram-check')
    load = commands.add_parser('load')
    load.add_argument('image', type=Path, help='Raw CPU machine-code binary, not token bytes')
    load.add_argument('--run', action='store_true', help='Run at reset PC after verified loading')
    args = parser.parse_args()
    image = None
    if args.command == 'load':
        image = args.image.read_bytes()
        # FFFF is write-only UART MMIO, so it cannot be loaded as SRAM.
        if not 1 <= len(image) <= 65535:
            parser.error('Image must contain 1..65535 bytes; address FFFF is UART MMIO')
    client = DebugUART.connect(args.port, timeout=args.timeout)
    try:
        if args.command == 'status':
            status = client.status()
            print(f'halted={status.halted} break={status.break_reason}')
            if status.halted:
                print(f'pc=0x{client.read_pc():04x}')
        elif args.command == 'sram-check':
            client.halt()
            check_sram(client)
        else:
            client.reset_halt()
            client.write_bytes(image, address=0)
            for address, expected in enumerate(image):
                actual = client.read8(address)
                if actual != expected:
                    raise RuntimeError(f'Verify failed at 0x{address:04x}: {actual:02x} != {expected:02x}')
            print(f'Loaded and verified {len(image)} bytes; PC=0x{client.read_pc():04x}')
            if args.run:
                client.run()
    finally:
        client.transport.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, TimeoutError, ImportError) as exc:
        sys.exit(str(exc))
