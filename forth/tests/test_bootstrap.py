"""Target-compiler bootstrap, dictionary sealing and build diagnostics."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'src', ROOT / 'tests'):
    sys.path.insert(0, str(path))

from forth.bootstrap import CORE_EFFECTS, CORE_SOURCE, compile_core
from forth.build import build_image, memory_map
from forth.image import Image
from forth.libraries import standard_sources
from forth.kernel.boot import emit_kernel, VARIABLES
from forth.tests.model import session, cell
from forth.tests.dual_support import DualSession
from forth.tests.rtl_console import RtlConsole

RTL = False


class BootstrapChecks(unittest.TestCase):
    def test_words_lists_hardware_before_older_core_and_user_words_first(self):
        r = DualSession()
        r.uart(': NEWEST 42 ;\rWORDS\r')
        r.quiet()
        output = bytes(r.memory.tx)
        expected = ('NEWEST ' + ' '.join(w['name'] for w in reversed(r.image.words))
                    + ' \r\nok\r\n').encode()
        self.assertTrue(output.endswith(expected), output)
        names = expected.decode().split()
        self.assertLess(names.index('AUDIO-INIT'), names.index('VGA-INIT'))
        self.assertLess(names.index('VGA-INIT'), names.index('+'))
        self.assertEqual(names[-3:], ['DROP', 'DUP', 'ok'])

    def test_core_source_is_sealed_and_described_in_both_profiles(self):
        for dual in (False, True):
            image = build_image(dual_console=dual)
            core = [w for w in image.words if w.get('source') == 'forth/kernel/core.fs']
            self.assertEqual({w['name'] for w in core}, set(CORE_EFFECTS))
            self.assertEqual(len(core), 8)
            for word in core:
                xt = image.symbols[word['xt']]
                self.assertLess(xt, image.symbols['user_start'])
                self.assertIn(xt, image.instructions)
                self.assertIn(f'{xt:04x}', image.disassembly())
                self.assertEqual(word['source'], 'forth/kernel/core.fs')
                self.assertGreater(word['source_line'], 1)
            self.assertEqual(image.symbols['kernel_latest'], image.symbols[image.words[-1]['header']])
            self.assertEqual(memory_map(image)['words'][-1]['name'], 'MARKER' if dual else 'CR')

    def test_standard_libraries_are_sealed_with_sources_and_initialized_data(self):
        image = build_image()
        expected = {name for _, effects in standard_sources() for name in effects}
        compiled = [w for w in image.words if w.get('source')]
        self.assertEqual({w['name'] for w in compiled}, expected)
        self.assertEqual(len(compiled), len(expected))
        self.assertEqual(memory_map(image)['forth_sources'], [
            'forth/kernel/core.fs', 'timer/forth/timer.fs',
            'timer/forth/callback.fs', 'timer/forth/ms.fs', 'vga/forth/console.fs',
            'audio/forth/audio.fs', 'forth/kernel/standard.fs'])
        for word in compiled:
            self.assertLess(image.symbols[word['xt']], image.symbols['user_start'])
            self.assertLess(image.symbols[word['xt']], 0xE000)
            self.assertIn(image.symbols[word['xt']], image.instructions)
        r = DualSession()
        r.uart('A-XLO @ A-XHI @ A-Y @ A-LO @ A-HI @\n')
        r.quiet()
        self.assertEqual(r.stack(), [0] * 5)
        self.assertEqual(r.memory.timer[4], 0)  # No timer starts on boot.
        self.assertEqual(r.get('timer_callback'), 0)
        for name in ('TIMER-EVERY', 'TIMER-INIT', 'VGA-TYPE', 'VGA-EMIT', 'AUDIO-INIT', 'A-XLO'):
            r.uart(f'FORGET {name}\n')
            r.quiet()
        self.assertEqual(bytes(r.memory.tx).count(b'cannot forget kernel word'), 6)

    def test_builtin_vga_uses_console_state_and_preserves_bank_and_hidden_ram(self):
        r = DualSession()
        r.memory.video[0] = 0x16
        r.memory.data[0xE000:0xE004] = b'kept'
        r.uart('VGA-PAGE 65 VGA-PUT VGA-BS 66 VGA-PUT VGA-CLEAR-ROW\n')
        r.quiet()
        self.assertEqual(r.memory.vram[:80], b' ' * 80)
        self.assertEqual(r.get('vga_x'), 1)
        r.uart('0 VX ! S" AB" VGA-TYPE 67 VGA-EMIT\n')
        r.quiet()
        self.assertNotIn(b'error:', bytes(r.memory.tx))
        self.assertEqual(r.memory.vram[:3], b'ABC')
        self.assertEqual(r.get('vga_x'), 3)
        self.assertEqual(r.memory.video[0], 0x16)
        self.assertEqual(r.memory.data[0xE000:0xE004], b'kept')
        r.set('console_owner', 1)
        r.invoke('raw_emit', [68])
        self.assertEqual(r.memory.vram[:4], b'ABCD')

    def test_builtin_audio_and_timer_execute_without_upload(self):
        r = DualSession()
        # Observe the actual bus writes; this console fixture has no audio model.
        writes = []
        original = r.memory.write8

        def write(address, value):
            if 0xFFE0 <= address < 0xFFF0:
                writes.append((address, value & 255))
            original(address, value)

        r.memory.write8 = write
        r.uart('TIMER-INIT TIMER-STOP AUDIO-INIT 440 TONE\n')
        r.quiet()
        self.assertNotIn(b'error:', bytes(r.memory.tx))
        self.assertEqual(r.stack(), [])
        self.assertEqual(r.memory.timer[4], 2)
        self.assertEqual(r.memory.read16(0xFFF2), 65535)
        registers = dict(writes)
        self.assertEqual(registers[0xFFE0], 1)
        self.assertEqual(registers[0xFFEA], 2)
        self.assertEqual(registers[0xFFE4] | registers[0xFFE5] << 8,
                         (440 * 43980 >> 8) & 65535)

    def test_core_words_execute_and_reset_retains_them(self):
        image = build_image(dual_console=False)
        source = b'5 1+ 1- CELL+ NEGATE SPACE CR 1 2 2DUP 2DROP\n'
        out, values, _, _ = session(image, source)
        self.assertNotIn(b'error:', out)
        self.assertEqual(values, [65529, 1, 2])
        self.assertIn(b' \r\nok', out)
        for name in CORE_EFFECTS:
            out, _, _, _ = session(image, f'FORGET {name}\n'.encode())
            self.assertIn(b'cannot forget kernel word', out)
        out, _, _, _ = session(image, b': user 42 ;\n')
        out, _, memory, _ = session(image, b'WORDS\n')
        self.assertNotIn(b'user ', out)
        self.assertEqual(cell(memory, VARIABLES['here']), image.symbols['user_start'])
        for name in CORE_EFFECTS:
            self.assertIn(name.encode() + b' ', out)
        for local in (False, True):
            r = DualSession()
            send = r.keyboard if local else r.uart
            send('1 2 2DUP 2DROP + 1+\r')
            r.quiet()
            self.assertEqual(r.stack(), [4])
            r.cpu.reset()
            r.physical = r.frames = 0
            r.until(lambda: r.cpu._pc == r.image.symbols['read_line'] and r.get('console_initialized'))
            r.quiet()
            send('2 1+\r')
            r.quiet()
            self.assertEqual(r.stack(), [3])

    def test_bootstrap_errors_include_source_and_do_not_publish_partial_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.fs'
            for text, detail in ((': 2DUP OVER OVER ;\nunknown-build-word\n', ':2:'),
                                  (': 2DUP OVER\n', 'incomplete definition'),
                                  ('ABORT\n', 'bootstrap aborted'),
                                  ('1 65504 C!\n', 'peripheral registers'),
                                  ('x' * 128, 'invalid kernel source line')):
                image = Image()
                image.dual_console = False
                emit_kernel(image)
                image.resolve()
                before = bytes(image.memory)
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError) as error:
                    compile_core(image, path)
                self.assertIn(str(path), str(error.exception))
                self.assertIn(detail, str(error.exception))
                self.assertEqual(bytes(image.memory), before)

    def test_source_change_is_compiled_by_the_target(self):
        # Change one body, keeping the declared stack contract. This proves
        # source text, rather than a parallel Python definition, determines code.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'core.fs'
            path.write_text(CORE_SOURCE.read_text().replace(': 1+ 1 + ;', ': 1+ 2 + ;'))
            image = Image()
            image.dual_console = False
            emit_kernel(image)
            image.resolve()
            compile_core(image, path)
            _, values, _, _ = session(image, b'10 1+\n')
            self.assertEqual(values, [12])

    def test_core_control_flow_strings_and_shared_line_locations(self):
        text = CORE_SOURCE.read_text().replace(': NEGATE 0 SWAP - ;',
                                               ': NEGATE DUP IF 0 SWAP - THEN ;')
        text = text.replace(': SPACE 32 EMIT ;', ': SPACE ." xyz" ;')
        text = text.replace(': 1+ 1 + ;\n: 1-', ': 1+ 1 + ; : 1-')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'core.fs'
            path.write_text(text)
            image = Image()
            image.dual_console = False
            emit_kernel(image)
            image.resolve()
            compile_core(image, path)
            out, values, _, _ = session(image, b'2 NEGATE SPACE\n')
            self.assertEqual(values, [65534])
            self.assertIn(b'xyzok', out)
            data = image.memory.index(b'xyz')
            self.assertTrue(all(at not in image.instructions for at in range(data, data + 3)))
            source_words = {w['name']: w for w in image.words if w.get('source')}
            self.assertEqual(source_words['1+']['source_line'], source_words['1-']['source_line'])

    def test_rtl_core_words_from_sealed_image(self):
        if not RTL:
            self.skipTest('enable bootstrapped-word RTL execution with --rtl')
        with tempfile.TemporaryDirectory() as directory:
            sim = RtlConsole(directory, build_image(dual_console=False))
            out, values, _ = sim.session(b'4 1+ CELL+ NEGATE 1 2 2DUP 2DROP\n')
            self.assertNotIn(b'error:', out)
            self.assertEqual(values, [65529, 1, 2])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
