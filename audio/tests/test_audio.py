#!/usr/bin/env python3
"""Audio core and system bus behavioral checks."""
import argparse
import sys
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
