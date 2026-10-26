"""Small lifecycle adapters; simulation/build code lives in ordinary helpers."""
from pathlib import Path
import tempfile
from .build import verilator
from .config import Tools
from .sram import SramSimulation


class VerilatorHarness:
    tools = Tools()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.simulator = verilator(cls.tools.simulator)


class SramHarness:
    tools = Tools()
    with_uart = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        temporary = tempfile.TemporaryDirectory(prefix='prim-sram-')
        cls.addClassCleanup(temporary.cleanup)
        cls.directory = Path(temporary.name)
        cls.simulation = SramSimulation(cls.directory, cls.tools, cls.with_uart)
        cls.simulation.build()

    def run_simulator(self, timing, *options):
        return self.simulation.run(timing, *options)

    def compare_image(self, image, timing):
        return self.compare_result(image, timing).serial

    def compare_result(self, image, timing):
        return self.simulation.compare_image(image, timing)
