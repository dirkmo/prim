"""Dual-console kernel acceptance tests, run on the actual Prim instruction model."""
import unittest
from dual_support import DualRunner


class OutputChecks(unittest.TestCase):
    def test_output_routes_and_restores_video_bank(self):
        r = DualRunner()
        r.invoke('vga_init')
        self.assertEqual(r.memory.vram[:2560], b' ' * 2560)
        r.invoke('raw_emit', [ord('U')])
        self.assertEqual(bytes(r.memory.tx), b'U')
        self.assertEqual(r.memory.vram[0], 32)
        r.set('console_owner', 1)
        r.memory.data[0xE000:0xE004] = b'kept'
        for byte in b'AB\bC\r\nD':
            r.invoke('raw_emit', [byte])
        self.assertEqual(bytes(r.memory.tx), b'U')
        self.assertEqual(r.memory.vram[:2], b'AC')
        self.assertEqual(r.memory.vram[80], ord('D'))
        self.assertEqual(r.memory.video[0], 0x1E)
        self.assertEqual(r.memory.data[0xE000:0xE004], b'kept')
        self.assertEqual((r.get('vga_x'), r.get('vga_y')), (1, 1))

    def test_wrapping_scrolling_and_shared_numeric_formatting(self):
        r = DualRunner()
        r.invoke('vga_init')
        r.set('console_owner', 1)
        for _ in range(35):
            r.invoke('raw_emit', [65])
            r.invoke('raw_emit', [10])
        self.assertEqual((r.get('vga_row'), r.get('vga_y')), (6, 29))
        self.assertEqual(r.memory.screen().splitlines()[-1], b' ' * 80)
        word = next(w for w in r.image.words if w['name'] == '.')
        r.set('depth', 1)
        r.invoke(word['xt'], [0xFFFF])
        self.assertTrue(r.memory.screen().splitlines()[-1].startswith(b'-1 '))
        self.assertFalse(r.memory.tx)
        self.assertLessEqual(r.max_data, 16)
        self.assertLessEqual(r.max_frames, 16)


if __name__ == '__main__':
    unittest.main()
