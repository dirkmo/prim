"""Ordered standard-image sources and their public stack contracts."""
from pathlib import Path

from forth.bootstrap import CORE_SOURCE, CORE_EFFECTS

ROOT = Path(__file__).resolve().parents[1]
TIMER_EFFECTS = {
    'TIMER-COUNT@': (0, 1), 'TIMER-COUNT!': (1, 0),
    'TIMER-COMPARE@': (0, 1), 'TIMER-COMPARE!': (1, 0),
    'TIMER-STOP': (0, 0), 'TIMER-START': (0, 0), 'TIMER-RESET': (0, 0),
    'TIMER-DONE?': (0, 1), 'TIMER-INIT': (0, 0), 'TIMER-ONCE': (1, 0),
    'TIMER-PERIOD': (1, 0), 'TIMER-WAIT': (1, 0),
}
AUDIO_EFFECTS = {
    **dict.fromkeys(('AUDIO-VOICE', 'AUDIO-MODE', 'AUDIO-VOLUME', 'AUDIO-DUTY',
                     'AUDIO-ATTACK', 'AUDIO-DECAY', 'AUDIO-HZ', 'TONE',
                     'TRI-TONE', 'NOISE'), (1, 0)),
    **dict.fromkeys(('AUDIO-APPLY', 'AUDIO-TRIGGER', 'AUDIO-STOP', 'AUDIO-STOP-ALL',
                     'AUDIO-ON', 'AUDIO-OFF', 'AUDIO-MUTE', 'AUDIO-PULSE',
                     'AUDIO-TRIANGLE', 'AUDIO-SAW', 'AUDIO-CONSTANT', 'AUDIO-INIT'), (0, 0)),
    **dict.fromkeys(('A-XLO', 'A-XHI', 'A-Y', 'A-LO', 'A-HI'), (0, 1)),
    'AUDIO-RATE': (2, 0), 'AUDIO-STATUS': (0, 1), 'A-UM*': (2, 2),
    'AUDIO-ENVELOPE': (2, 0),
}


def standard_sources():
    return [
        (CORE_SOURCE, CORE_EFFECTS),
        (ROOT / 'timer/forth/timer.fs', TIMER_EFFECTS),
        (ROOT / 'timer/forth/callback.fs', {'TIMER-EVERY': (2, 0)}),
        (ROOT / 'timer/forth/ms.fs', {'MS-STEP': (1, 2), 'MS': (1, 0)}),
        (ROOT / 'vga/forth/console.fs', {'VGA-TYPE': (2, 0)}),
        (ROOT / 'audio/forth/audio.fs', AUDIO_EFFECTS),
        (ROOT / 'forth/kernel/standard.fs', {
            'MEM-SRC': (0, 1), 'MEM-DST': (0, 1), 'MEM-LEFT': (0, 1), 'MEM-BYTE': (0, 1),
            'FILL': (3, 0), 'MOVE': (3, 0), 'M-RESTORE': (2, 0), 'MARKER': (0, 0)}),
    ]
