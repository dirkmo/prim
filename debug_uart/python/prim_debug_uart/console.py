"""POSIX terminal UI. One reader owns serial RX, independent of the local prompt."""
import os
import queue
import select
import shutil
import sys
import threading

HELP = """CPU mode: keys go to the seven-bit CPU channel (no local echo).
Ctrl+B       Open local debug prompt
Ctrl+D       Quit the console in either mode; CPU state is unchanged
Ctrl+V key   Send the next byte literally (including Ctrl+B or Ctrl+D)
Debug mode: Enter submits a command; empty Enter returns to CPU mode.
Up / Down                Browse command history; Down restores the draft
help / ?                 Show all commands and keybindings
halt / stop              Halt CPU at an instruction boundary
step                     Execute one instruction (CPU must be halted)
reset-halt               Reset CPU and remain halted
run                      Resume CPU at current PC
pc                       Read halted CPU's PC
status                   Show CPU halt/BREAK status
uart-status              Show RX received / TX buffer free
sram-check               Halt CPU and test/restore the scratch SRAM region
read <addr> [len]        Hex/ASCII dump (default: one byte)
write <addr> <bytes...>  Write consecutive bytes (0..255)
                         Numbers: decimal, or hex with 0x prefix
load FILE [--skip-mmio] [--verify] [--write-delay SECONDS] [--run]
                         Stream CPU image; optional readback/pacing; no automatic retry
quit                     Close console; CPU state is unchanged
"""


class Console:
    def __init__(self, execute, *, output=None):
        self.execute = execute
        self.output = output or sys.stdout
        self.session = None
        self.running = True
        self.debug_mode = False
        self.quoted = False
        self.line = bytearray()
        self._history = []
        self._history_index = None
        self._history_draft = b''
        self._escape = bytearray()
        self._partial = ''
        self._shown_partial = False
        self._progress_active = False
        self._lock = threading.RLock()
        self._commands = queue.Queue()

    def _prompt(self):
        if self.debug_mode:
            self.output.write('debug> ' + self.line.decode('ascii'))

    def cpu_output(self, data):
        with self._lock:
            if self._progress_active:
                self.output.write('\r\x1b[2K')
                self._progress_active = False
            text = data.decode('ascii')
            if self.debug_mode:
                self.output.write('\r\x1b[2K')
                if self._shown_partial:
                    self.output.write('\x1b[1A\r\x1b[2K')
                lines = (self._partial + text.replace('\r', '')).split('\n')
                width = max(1, shutil.get_terminal_size((80, 24)).columns - 1)
                for index, line in enumerate(lines):
                    line = line.expandtabs(8)
                    while len(line) >= width:
                        self.output.write(line[:width] + '\r\n')
                        line = line[width:]
                    if index < len(lines) - 1:
                        self.output.write(line + '\r\n')
                    else:
                        self._partial = line
                self._shown_partial = bool(self._partial)
                if self._partial:
                    self.output.write(self._partial + '\r\n')
                self._prompt()
            else:
                self.output.write(text)
            self.output.flush()

    def message(self, text):
        with self._lock:
            self._progress_active = False
            self._partial = ''
            self._shown_partial = False
            self.output.write('\r\x1b[2K' + text.replace('\n', '\r\n') + '\r\n')
            self._prompt()
            self.output.flush()

    def progress(self, text):
        """Replace the current status line without adding a newline."""
        with self._lock:
            self._progress_active = bool(text)
            self.output.write('\r\x1b[2K' + text)
            if not text:
                self._prompt()
            self.output.flush()

    def _browse_history(self, direction):
        if not self._history:
            return
        if self._history_index is None:
            if direction > 0:
                return
            self._history_draft = bytes(self.line)
            self._history_index = len(self._history)
        self._history_index = max(0, min(len(self._history), self._history_index + direction))
        if self._history_index == len(self._history):
            self.line[:] = self._history_draft
            self._history_index = None
        else:
            self.line[:] = self._history[self._history_index].encode('ascii')
        self.output.write('\r\x1b[2K')
        self._prompt()

    def _escape_key(self, byte):
        """Consume terminal CSI/SS3 sequences, including split arrow-key input."""
        if byte == 27:
            self._escape[:] = b'\x1b'
            return True
        if not self._escape:
            return False
        if self._escape == b'\x1b':
            if byte in (ord('['), ord('O')):
                self._escape.append(byte)
                return True
        elif 0x40 <= byte <= 0x7e:
            sequence = bytes(self._escape) + bytes([byte])
            self._escape.clear()
            if sequence in (b'\x1b[A', b'\x1bOA'):
                self._browse_history(-1)
            elif sequence in (b'\x1b[B', b'\x1bOB'):
                self._browse_history(1)
            return True
        elif 0x20 <= byte <= 0x3f and len(self._escape) < 32:
            self._escape.append(byte)
            return True
        self._escape.clear()
        return False

    def key(self, byte):
        with self._lock:
            if self._progress_active:
                self._progress_active = False
                self.output.write('\r\x1b[2K')
                self._prompt()
            if self.quoted:
                self.quoted = False
                self.session.queue_cpu(bytes([byte]))
            elif byte == 4:
                self._escape.clear()
                self.running = False
            elif byte == 22:
                self._escape.clear()
                self.quoted = True
            elif byte == 2 and not self.debug_mode:
                self.debug_mode = True
                self.output.write('\r\n')
                self._prompt()
            elif not self.debug_mode:
                self.session.queue_cpu(bytes([byte]))
            elif self._escape_key(byte):
                pass
            elif byte in (10, 13):
                self._partial = ''
                self._shown_partial = False
                command = self.line.decode('ascii').strip()
                self.line.clear()
                if command:
                    self._history.append(command)
                self._history_index = None
                self._history_draft = b''
                self.output.write('\r\n')
                if not command:
                    self.debug_mode = False
                elif command == 'quit':
                    self.running = False
                elif command in ('help', '?'):
                    self.message(HELP.rstrip())
                else:
                    self._commands.put(command)
                    self._prompt()
            elif byte in (8, 127):
                if self.line:
                    self.line.pop()
                    self.output.write('\b \b')
            elif 32 <= byte < 127:
                self.line.append(byte)
                self.output.write(chr(byte))
            else:
                self.message('Command prompt accepts ASCII text; use Ctrl+V for a literal CPU byte')
            self.output.flush()

    def _worker(self):
        while self.running:
            try:
                command = self._commands.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                result = self.session.transact(lambda: self.execute(command))
                if result:
                    self.message(result)
            except Exception as exc:
                self.message(str(exc))
                if self.session.error:
                    self.running = False

    def run(self, session, *, input_fd=None):
        import termios
        import tty
        self.session = session
        fd = sys.stdin.fileno() if input_fd is None else input_fd
        if not os.isatty(fd):
            raise ValueError('console requires a terminal on stdin')
        previous = termios.tcgetattr(fd)
        worker = threading.Thread(target=self._worker, daemon=True)
        try:
            # Raw mode distinguishes Enter (CR) from Ctrl+B (STX), and handles Ctrl+D locally.
            tty.setraw(fd)
            settings = termios.tcgetattr(fd)
            settings[1] = previous[1]  # Preserve normal terminal output processing.
            termios.tcsetattr(fd, termios.TCSANOW, settings)
            worker.start()
            self.message('Prim UART console: Ctrl+B debug, Ctrl+D quit; Ctrl+B then help for commands')
            while self.running:
                if session.error:
                    raise OSError(f'UART session failed: {session.error}')
                if select.select([fd], [], [], 0.05)[0]:
                    data = os.read(fd, 1)
                    if not data:
                        break
                    try:
                        self.key(data[0])
                    except ValueError as exc:
                        self.message(str(exc))
        finally:
            self.running = False
            session.close()  # Wake pending operations; do not send HALT/RESET on exit.
            worker.join(timeout=1)
            termios.tcsetattr(fd, termios.TCSANOW, previous)
            self.output.write('\r\n')
            self.output.flush()
