"""Set-2 sequences checked against independent literal ASCII expectations."""
import unittest
from dual_support import DualRunner


class KeyboardChecks(unittest.TestCase):
    def decode(self, r, sequence):
        result = bytearray()
        for byte in sequence:
            r.set('kbd_scan', byte)
            r.invoke('kbd_decode')
            if r.get('kbd_available'):
                result.append(r.get('kbd_char'))
        return bytes(result)

    def test_alphabet_typematic_breaks_and_edit_keys(self):
        r = DualRunner()
        sequence = [0x1C, 0x32, 0x21, 0x23, 0x24, 0x2B, 0x34, 0x33, 0x43,
                    0x3B, 0x42, 0x4B, 0x3A, 0x31, 0x44, 0x4D, 0x15, 0x2D,
                    0x1B, 0x2C, 0x3C, 0x2A, 0x1D, 0x22, 0x1A, 0x35]
        self.assertEqual(self.decode(r, sequence), b'abcdefghijklmnopqrstuvwxyz')
        self.assertEqual(self.decode(r, [0x1C, 0x1C, 0xF0, 0x1C, 0x29, 0x66, 0x5A, 0x0D]),
                         b'aa \b\r\t')
        self.assertEqual(self.decode(r, [0xE0, 0x5A, 0xE0, 0xF0, 0x5A]), b'\r')

    def test_independent_shifts_caps_and_punctuation(self):
        r = DualRunner()
        self.assertEqual(self.decode(r, [0x12, 0x59, 0xF0, 0x12, 0x1C, 0xF0, 0x59, 0x1C]), b'Aa')
        self.assertEqual(self.decode(r, [0x58, 0x58, 0x1C, 0x12, 0x1C, 0x16, 0xF0, 0x12,
                                        0xF0, 0x58, 0x58, 0x1C]), b'Aa!a')
        self.assertEqual(self.decode(r, [0x12, 0x16, 0x1E, 0x25, 0x2E, 0x36, 0x3D,
                                        0x3E, 0x46, 0x45, 0x5B, 0x5D, 0x41, 0x49,
                                        0x4A, 0x61, 0xF0, 0x12]), b'!"$%&/()=*\';:_>')

    def test_altgr_ctrl_and_non_ascii(self):
        r = DualRunner()
        self.assertEqual(self.decode(r, [0xE0, 0x11, 0x15, 0x3D, 0x3E, 0x46,
                                        0x45, 0x4E, 0x5B, 0x61, 0xE0, 0xF0, 0x11]),
                         b'@{[]}\\~|')
        self.assertEqual(self.decode(r, [0x14, 0xE0, 0x14, 0xF0, 0x14, 0x21, 0x29,
                                        0xE0, 0xF0, 0x14, 0x21]), b'\x03\0c')
        self.assertEqual(self.decode(r, [0x54, 0x4C, 0x52, 0x4E, 0x12, 0x26, 0xF0, 0x12]), b'')

    def test_pause_print_screen_status_and_recovery(self):
        r = DualRunner()
        pause = [0xE1, 0x14, 0x77, 0xE1, 0xF0, 0x14, 0xF0, 0x77]
        screen = [0xE0, 0x12, 0xE0, 0x7C, 0xE0, 0xF0, 0x7C, 0xE0, 0xF0, 0x12]
        self.assertEqual(self.decode(r, pause + screen + [0x1C]), b'a')
        self.assertEqual(r.get('kbd_shift'), 0)
        self.assertEqual(self.decode(r, [0x12, 0x58, 0xAA, 0xFA, 0xFE, 0xFC, 0xFD, 0x00, 0xFF, 0x1C]), b'a')
        r.set('kbd_extended', 1)
        r.set('kbd_break', 1)
        r.set('kbd_shift', 3)
        r.invoke('kbd_reset')
        self.assertEqual(self.decode(r, [0x1C]), b'a')
        self.assertLessEqual(r.max_data, 3)


if __name__ == '__main__':
    unittest.main()
