"""Line-paced source upload using the existing Forth echo and text prompts."""
from pathlib import Path
import re
import threading
import time


def source_error(filename, number, line, message):
    """Render a kernel-provided byte span; never guess a token from the message."""
    match = re.search(r' \[source ([0-9A-F]{2}) ([0-9A-F]{2})\]$', message)
    if line is None or match is None:
        return f'{filename}:{number}: {message}'
    column, length = (int(value, 16) for value in match.groups())
    start = column - 1
    if not (0 <= start < len(line) and 0 < length <= len(line) - start):
        return f'{filename}:{number}: {message}'
    text = line.decode('ascii')
    word = text[start:start + length]
    visible = text.replace('\v', ' ').replace('\f', ' ')
    # Match the terminal's tab expansion, including a tab inside a source span.
    prefix = visible[:start].expandtabs(8)
    marked = visible[:start + length].expandtabs(8)
    return (f'{filename}:{number}:{column}: {message[:match.start()]} (word {word!r})\n'
            f'  {visible.expandtabs(8)}\n  {" " * len(prefix)}^{"~" * (len(marked) - len(prefix) - 1)}')


def read_source(filename):
    """Validate the whole file before sending anything to the interpreter."""
    data = Path(filename).expanduser().read_bytes()
    lines = data.replace(b'\r\n', b'\n').replace(b'\r', b'\n').split(b'\n')
    if lines[-1] == b'':
        lines.pop()
    for number, line in enumerate(lines, 1):
        if len(line) > 127:
            raise ValueError(f'{filename}:{number}: line exceeds 127 bytes')
        if any(byte >= 127 or (byte < 32 and byte not in (9, 11, 12)) for byte in line):
            raise ValueError(f'{filename}:{number}: expected seven-bit ASCII Forth text')
    return lines


class ForthUpload:
    def __init__(self, *, timeout=10.0):
        self.timeout = timeout
        self.cancel = threading.Event()
        self._condition = threading.Condition()
        self._line = bytearray()
        self._echo = None
        self._echo_seen = False
        self._reply = None
        self._discard = threading.Event()

    def feed(self, data):
        with self._condition:
            for byte in data:
                if byte == 13:
                    continue
                if byte != 10:
                    # Output from a user program need not contain newlines.
                    self._line.append(byte)
                    if len(self._line) > 4096:
                        del self._line[:-4096]
                    continue
                line = bytes(self._line)
                self._line.clear()
                if self._echo is None or self._reply is not None:
                    continue
                if not self._echo_seen:
                    if line == self._echo:
                        self._echo_seen = True
                elif b'error: ' in line:
                    self._reply = line.decode('ascii')
                elif line.endswith(b'compiled'):
                    self._reply = 'compiled'
                elif line.endswith(b'ok'):
                    self._reply = 'ok'
                self._condition.notify_all()

    def _send_line(self, session, line, alive):
        with self._condition:
            self._line.clear()
            self._echo = line
            self._echo_seen = False
            self._reply = None
            session.queue_cpu(line + b'\r', cancel=self._discard)
            deadline = time.monotonic() + self.timeout
            while self._reply is None:
                if session.error:
                    raise OSError(f'UART session failed: {session.error}')
                if not alive():
                    raise RuntimeError('console closed')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('no Forth response within %.1f seconds; '
                                       'check interpreter/input state before continuing' % self.timeout)
                self._condition.wait(min(remaining, 0.05))
            if self._reply not in ('ok', 'compiled'):
                raise RuntimeError(self._reply)
            return self._reply

    def run(self, session, filename, *, alive=lambda: True, progress=lambda text: None):
        lines = read_source(filename)
        number = 0
        try:
            if not lines:
                return f'{filename}: empty file; nothing sent'
            # Drain prior input and establish a fresh echo/prompt boundary.
            self._send_line(session, b'', alive)
            reply = 'ok'
            for number, line in enumerate(lines, 1):
                if self.cancel.is_set():
                    return f'{filename}: upload cancelled before line {number}; earlier lines remain loaded'
                progress(f'Forth upload: {filename}:{number}/{len(lines)} (Ctrl+C to cancel)')
                reply = self._send_line(session, line, alive)
            if reply == 'compiled':
                raise RuntimeError('file ends inside an unfinished definition')
            return f'{filename}: {len(lines)} lines loaded'
        except Exception as exc:
            line = lines[number - 1] if number else None
            raise RuntimeError(source_error(filename, number, line, str(exc))) from exc
        finally:
            # In particular, a timed-out line must not resume sending much later.
            self._discard.set()
