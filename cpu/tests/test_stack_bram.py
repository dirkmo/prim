#!/usr/bin/env python3
"""Check BRAM inference and mapped-cell behavior against the Python ISA."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile
import sys
import unittest

from prim.assembler import PrimAsm
from prim.cpu import Prim
from prim.isa import PrimOpcodes as Op

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))
from support.paths import ROOT
from support.process import run
from support.reference import Memory


class TraceMemory(Memory):
    def __init__(self, image):
        super().__init__(image)
        self.events = []
        self.irq_addresses = set()
        self.on_irq = None

    def read8(self, address):
        value = super().read8(address)
        self.events.append(f'R {address & 65535} {value}')
        return value

    def write8(self, address, value):
        super().write8(address, value)
        self.events.append(f'W {address & 65535} {value & 255}')
        if address in (0x4300, 0x4302) and address not in self.irq_addresses:
            self.irq_addresses.add(address)
            self.on_irq()


class StackBramChecks(unittest.TestCase):
    def test_mapped_stacks(self):
        # Force both pointers around their rings several times. Drain through
        # memory writes so every retained cell is externally observable.
        program = ' '.join(str(0x1200 + i) for i in range(96))
        program += ' rot -rot swap over + nip'
        program += ' ' + ' '.join(f'{0x4000 + 2*i} !' for i in range(30))
        program += ' ' + ' '.join(f'{0x5600 + i} >r' for i in range(96))
        program += ' ' + ' '.join(f'r> {0x4100 + 2*i} !' for i in range(32))
        # Two-cell return pops on both bank alignments, and >R.RET, must use
        # the correct prefetch even immediately after the preceding push.
        for count in (0, 1, 30, 31, 32, 33):
            program += ' ' + ' '.join(f'{i + 1} >r' for i in range(count))
            for op in ('r>', 'rdrop', '>r'):
                # Keep the placeholder the same width as the final address.
                prefix = program + ' 0xffff >r'
                if op == '>r':
                    # >R.RET returns through T without writing the array.
                    target = len(PrimAsm.assemble(program + ' 0xffff >r.ret 0xdead BREAK'))
                    program += f' {target} >r.ret 0xdead BREAK'
                else:
                    target = len(PrimAsm.assemble(prefix + f' 0x3456 >r {op}.ret 0xdead BREAK'))
                    program += f' {target} >r 0x3456 >r {op}.ret 0xdead BREAK'
                    if op == 'r>':
                        program += ' 0x4200 !'
        # Inject an IRQ during STORE's bus wait/cleanup, then a second pulse
        # inside the masked ISR. INTEI.RET must return before pushing the next
        # IRQ's PC, without nesting or losing the pending request.
        tail = 'intad intei 1 0x4300 ! nop BREAK'
        isr_address = len(PrimAsm.assemble(program + ' 0xffff ' + tail))
        program += f' {isr_address} {tail} intdi 0xbeef 0x4302 ! intei.ret'
        image = bytes(PrimAsm.assemble(program))
        memory = TraceMemory(image)
        cpu = Prim(memory)
        memory.on_irq = cpu.request_irq
        for _ in range(10000):
            if cpu.step() == Op.BREAK:
                break
        else:
            self.fail('reference program did not halt')
        self.assertEqual(cpu._pc, isr_address, 'returned to an early failure marker')
        self.assertEqual(memory.irq_addresses, {0x4300, 0x4302})
        expected = memory.events + [f'HALT {cpu._pc}']

        with tempfile.TemporaryDirectory(prefix='prim-stack-bram-') as directory:
            directory = Path(directory)
            netlist = directory / 'mapped.v'
            json_path = directory / 'mapped.json'
            script = directory / 'synth.ys'
            script.write_text(
                'read_verilog -Icpu/rtl cpu/rtl/prim.v\n'
                f'synth_ice40 -top Prim -json "{json_path}"\n'
                f'write_verilog -noattr "{netlist}"\n')
            run([self.yosys, '-Q', '-s', script], cwd=ROOT, timeout=120)
            cells = json.loads(json_path.read_text())['modules']['Prim']['cells']
            counts = Counter(cell['type'] for cell in cells.values())
            self.assertEqual(counts['SB_RAM40_4K'], 4)
            # A stray asynchronous read must not silently turn a stack back
            # into hundreds of flip-flops.
            self.assertLess(sum(n for t, n in counts.items() if t.startswith('SB_DFF')), 256)
            data_dir = run([self.yosys_config, '--datdir']).stdout.strip()
            cells_sim = Path(data_dir) / 'ice40' / 'cells_sim.v'
            binary = directory / 'mapped.vvp'
            run([self.iverilog, '-g2012', '-DNO_ICE40_DEFAULT_ASSIGNMENTS',
                 '-s', 'tb_stack_bram', '-o', binary, netlist, cells_sim,
                 ROOT / 'cpu/tests/tb_stack_bram.sv'])
            hex_path = directory / 'image.hex'
            hex_path.write_text(''.join(f'{byte:02x}\n' for byte in image))
            result = run([self.vvp, binary, f'+image={hex_path}'])
            actual = [line for line in result.stdout.splitlines()
                      if line.startswith(('R ', 'W ', 'HALT '))]
            self.assertEqual(actual, expected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yosys', default='yosys')
    parser.add_argument('--yosys-config', default='yosys-config')
    parser.add_argument('--iverilog', default='iverilog')
    parser.add_argument('--vvp', default='vvp')
    options, remaining = parser.parse_known_args()
    for name, value in vars(options).items():
        setattr(StackBramChecks, name, value)
    unittest.main(argv=[sys.argv[0], *remaining])
