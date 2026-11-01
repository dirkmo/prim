#!/usr/bin/env python3
"""Run uploaded libraries, or --standard built-ins, on the CPU/audio RTL."""
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'tests')]
from forth.build import build_image
from forth.run import ConsoleMemory
from prim.cpu import Prim
from prim.isa import PrimOpcodes as Op
from forth.tests.model import lookup

def main():
    standard = '--standard' in sys.argv
    image=build_image(dual_console=standard)
    source=(b'' if standard else (ROOT/'timer/forth/timer.fs').read_bytes()
            + (ROOT/'audio/forth/audio.fs').read_bytes())
    source+=(ROOT/'audio/forth/demo.fs').read_bytes()
    assert max(map(len,source.splitlines())) < 127
    commands=b'''AUDIO-DEMO-TIMER
0 AUDIO-MS
3 AUDIO-MS
AUDIO-INIT
440 TRI-TONE
1 AUDIO-VOICE AUDIO-SAW 6 AUDIO-VOLUME 523 AUDIO-HZ AUDIO-TRIGGER
2 AUDIO-VOICE 13398 18 AUDIO-RATE AUDIO-TRIGGER
4000 NOISE
'''
    # Compilation/syntax check in the host CPU; no claim of host audio simulation.
    definition = b': AUDIO-CHECK\n' + commands + b';\n'
    if standard:
        from forth.tests.dual_support import DualSession
        fixture=DualSession()
        image=fixture.image
        for line in (source+definition).splitlines(keepends=True):
            fixture.uart(line)
            fixture.quiet()
        memory=fixture.memory
        output=bytes(memory.tx)
    else:
        memory=ConsoleMemory(image.memory,BytesIO(source+definition),BytesIO());cpu=Prim(memory)
        for _ in range(6000000):
            if memory.eof and cpu._pc==image.symbols['raw_key']:break
            cpu.step()
        else:raise AssertionError('host compile timeout')
        output=memory.sink.getvalue()
    assert b'error' not in output.lower(),output
    assert memory.read16(image.symbols['depth'])==0
    free=0xf000-memory.read16(0x100)
    profile='standard dual' if standard else 'UART-only'
    print(f'{profile} with audio demos + test definition: {free} free dictionary bytes, range HERE..EFFF')
    with tempfile.TemporaryDirectory(prefix='prim-audio-forth-') as directory:
        d=Path(directory)
        header,xt=lookup(memory,'AUDIO-CHECK')
        print(f'{profile} library+demo dictionary: HERE={header:04X}, free={0xf000-header} bytes through EFFF')
        blob=bytearray(memory.data)
        blob[:5]=bytes([Op.PUSH,xt&255,xt>>8,Op.CALL,Op.BREAK])
        (d/'image.hex').write_text(''.join(f'{blob[i+1]:02x}{blob[i]:02x}\n' for i in range(0,65536,2)))
        payload=b''
        (d/'rx.hex').write_text(''.join(f'{b:02x}\n' for b in payload))
        sources=['audio/tests/tb_audio_forth.sv','audio/rtl/audio.v','cpu/rtl/prim.v',
          'debug_uart/rtl/uart_buffers.v','system/rtl/memory_io.v','system/rtl/memory.v',
          'system/rtl/timer_mmio.v','timer/rtl/timer.v']
        # CPU retirement logging is unrelated to audio; quiet a test-local copy.
        cpu_source=d/'prim.v'
        cpu_source.write_text('\n'.join(line for line in (ROOT/'cpu/rtl/prim.v').read_text().splitlines()
                                       if '$display("EXEC' not in line)+'\n')
        sources.remove('cpu/rtl/prim.v')
        subprocess.run(['iverilog','-g2012','-s','tb_audio_forth','-I',str(ROOT/'cpu/rtl'),
          '-o',str(d/'sim'),str(cpu_source),*[str(ROOT/s) for s in sources]],check=True,capture_output=True,text=True)
        result=subprocess.run(['vvp',str(d/'sim'),f'+image={d/"image.hex"}',f'+rx={d/"rx.hex"}',
          f'+count={len(payload)}',f'+waitpc={image.symbols["raw_key"]}',f'+tx={d/"tx.hex"}',
          f'+ram={d/"ram.hex"}'],capture_output=True,text=True,timeout=90)
        assert result.returncode==0,result.stdout+result.stderr
        tx=bytes(int(s,16) for s in (d/'tx.hex').read_text().split())
        assert b'error' not in tx.lower(),tx
        ram=bytes(b for s in (d/'ram.hex').read_text().split() for b in (int(s,16)&255,int(s,16)>>8))
        assert int.from_bytes(ram[0x108:0x10a],'little')==0
        print(result.stdout.strip())
        print(f'RTL {profile} after library/demo/actions: {0xf000-int.from_bytes(ram[0x100:0x102],"little")} free dictionary bytes')
if __name__=='__main__':main()
