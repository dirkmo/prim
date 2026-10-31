#!/usr/bin/env python3
"""Audio core and system bus behavioral checks."""
import argparse
import sys
import json
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
class AudioTests(unittest.TestCase):
    def simulate(self, top, sources, parameters=()):
        with tempfile.TemporaryDirectory(prefix='prim-audio-') as directory:
            binary = Path(directory) / top
            cmd = [IVERILOG, '-g2012', '-Wall', '-s', top, '-o', str(binary)]
            for parameter in parameters:
                cmd += ['-P', parameter]
            result = subprocess.run(cmd + [str(ROOT / source) for source in sources], capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result = subprocess.run([VVP,str(binary)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS',result.stdout)
    def test_immediate_scratch_boundary(self):
        from prim import compiler
        from prim.cpu import Prim
        from prim.isa import Consts, PrimOpcodes as Op
        memory = compiler.Mif()
        cpu = Prim(memory)
        self.assertEqual(Consts.IMMEDIATE_CAPACITY,224)
        compiler.execute(cpu,[Op.NOP]*222)
        before = bytes(memory._mem)
        with self.assertRaisesRegex(ValueError,'222'):
            compiler.execute(cpu,[Op.NOP]*223)
        self.assertEqual(bytes(memory._mem),before)

    def test_core(self):
        self.simulate('tb_audio',['audio/rtl/audio.v','audio/tests/tb_audio.sv'])
    def test_port_contract(self):
        self.simulate('tb_audio_contract',['audio/rtl/audio.v','audio/tests/tb_audio_contract.sv'])

    @unittest.skipUnless(shutil.which('yosys') and shutil.which('yosys-config'),
                         'Yosys iCE40 cells needed for mapped RAM check')
    def test_mapped_ebr_contract(self):
        # Check actual inferred EBR count and run the same port scoreboard on
        # the technology-mapped circuit, not a second behavioral RAM model.
        with tempfile.TemporaryDirectory(prefix='prim-audio-ebr-') as directory:
            d=Path(directory)
            script=(f'read_verilog "{ROOT / "audio/rtl/audio.v"}"; '
                    f'synth_ice40 -top audio -json "{d / "audio.json"}"; '
                    f'write_verilog -noattr "{d / "audio.v"}"')
            result=subprocess.run(['yosys','-Q','-T','-p',script],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            cells=json.loads((d/'audio.json').read_text())['modules']['audio']['cells']
            self.assertEqual(sum(c['type']=='SB_RAM40_4K' for c in cells.values()),1)
            datdir=subprocess.check_output(['yosys-config','--datdir'],text=True).strip()
            result=subprocess.run([IVERILOG,'-g2012','-s','tb_audio_contract','-o',str(d/'sim'),
                str(ROOT/'audio/tests/tb_audio_contract.sv'),str(d/'audio.v'),
                str(Path(datdir)/'ice40/cells_sim.v')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([VVP,str(d/'sim')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS',result.stdout)

    def test_mmio(self):
        for enabled in (0,1):
            self.simulate('tb_audio_mmio', ['audio/tests/tb_audio_mmio.sv','audio/rtl/audio.v',
                'system/rtl/memory_io.v','system/rtl/memory.v','system/rtl/timer_mmio.v',
                'timer/rtl/timer.v'], [f'tb_audio_mmio.ENABLED={enabled}'])
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iverilog',default='iverilog');parser.add_argument('--vvp',default='vvp')
    args,rest=parser.parse_known_args();IVERILOG,VVP=args.iverilog,args.vvp
    unittest.main(argv=[__file__,*rest])
