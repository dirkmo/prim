from pathlib import Path
from .paths import ROOT, CPU_RTL, BUILD, SIMULATOR, source_path
from .process import run


def verilator(simulator=None):
    if simulator is None:
        run(['cmake', '-S', ROOT, '-B', BUILD], timeout=120)
        run(['cmake', '--build', BUILD], timeout=120)
        simulator = SIMULATOR
    simulator = Path(simulator).absolute()
    if not simulator.is_file():
        raise RuntimeError(f'Simulator not found: {simulator}; build with cmake --build {BUILD}')
    return simulator


def icarus(output, *, tools, top, sources, parameters=None):
    command = [tools.iverilog, '-g2012', '-s', top, '-I', CPU_RTL, '-o', output]
    for name, value in (parameters or {}).items():
        command += ['-P', f'{top}.{name}={value}']
    run([*command, *(source_path(source) for source in sources)])
    return output
