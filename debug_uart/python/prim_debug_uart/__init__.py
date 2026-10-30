"""Blocking client for the FPGA debug UART (115200, 8N1).

Pass a byte transport with read(size), write(data), and a bounded read timeout,
for example serial.Serial(port, 115200, timeout=0.1). No pyserial dependency is
needed unless connect() is used. One caller/operation at a time.
"""
from dataclasses import dataclass
import time
import threading
from functools import wraps


class DebugTimeout(TimeoutError):
    """The FPGA did not complete a debug response before the deadline."""


@dataclass(frozen=True)
class Status:
    halted: bool
    break_reason: bool


@dataclass(frozen=True)
class UARTStatus:
    received: bool
    tx_free: bool


def transaction(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._operation_lock:
            return method(self, *args, **kwargs)
    return locked


def encode_number(value: int, digits: int) -> str:
    if not 0 <= value < 1 << (4 * digits):
        raise ValueError(f'value must fit in {digits * 4} bits')
    return f'{value:0{digits}x}'[::-1]


class DebugUART:
    def __init__(self, transport, *, timeout=2.0, on_output=None, on_break=None):
        if timeout <= 0:
            raise ValueError('timeout must be positive')
        self._operation_lock = threading.RLock()
        self.transport = transport
        self.timeout = timeout
        if hasattr(transport, 'timeout'):
            transport.timeout = min(timeout, 0.1)
        self.on_output, self.on_break = on_output, on_break
        self.output = bytearray()
        self.break_events = 0

    @classmethod
    def connect(cls, port, **kwargs):
        """Open at 115200/8N1 and request low USB latency where supported."""
        import serial
        transport = serial.Serial(port, baudrate=115200, bytesize=8,
                                  parity='N', stopbits=1, timeout=0.1,
                                  write_timeout=kwargs.get('timeout', 2.0))
        low_latency = False
        latency_error = 'not supported by this transport'
        try:
            configure = getattr(transport, 'set_low_latency_mode', None)
            if configure is not None:
                try:
                    # Linux FTDI: ASYNC_LOW_LATENCY selects a 1-ms timer.
                    # Configure before UARTSession starts its reader/sender.
                    configure(True)
                    low_latency = True
                    latency_error = None
                except (OSError, ValueError) as exc:
                    latency_error = str(exc)
            client = cls(transport, **kwargs)
        except Exception:
            transport.close()
            raise
        client.low_latency = low_latency
        client.low_latency_error = latency_error
        return client

    def _send(self, text):
        data = bytes(ord(c) | 0x80 for c in text)
        while data:
            count = self.transport.write(data)
            if not count:
                raise OSError('debug UART transport could not write command')
            data = data[count:]

    def _debug_char(self, deadline):
        while time.monotonic() < deadline:
            data = self.transport.read(1)
            if not data:
                continue
            byte = data[0]
            if not byte & 0x80:
                self.output.append(byte)
                if self.on_output:
                    self.on_output(bytes([byte]))
            elif byte == (ord('B') | 0x80):
                self.break_events += 1
                if self.on_break:
                    self.on_break()
            else:
                return chr(byte & 0x7f)
        raise DebugTimeout('Timed out waiting for FPGA debug UART response')

    def _response(self, prefix='K', digits=0):
        deadline = time.monotonic() + self.timeout
        if prefix is not None:
            char = self._debug_char(deadline)
            if char != prefix:
                raise RuntimeError(f'Expected debug response {prefix!r}, received {char!r}')
        text = ''.join(self._debug_char(deadline) for _ in range(digits))
        if any(c not in '0123456789abcdef' for c in text):
            raise RuntimeError(f'Invalid debug hex response: {text!r}')
        return int(text[::-1], 16) if digits else None

    @transaction
    def halt(self):
        self._send('H')
        self._response()

    @transaction
    def run(self):
        self._send('G')
        self._response()

    @transaction
    def step(self):
        """Requires a halted CPU; BREAK notifications are handled while waiting."""
        self._send('S')
        self._response()

    @transaction
    def reset_halt(self):
        self._send('Z')
        self._response()

    @transaction
    def status(self):
        """Also resets an incomplete address/write input; does not abort a bus access."""
        self._send('?')
        value = self._response('T', 1)
        return Status(bool(value & 1), bool(value & 2))

    @transaction
    def uart_status(self):
        """UART RX-valid and pending-TX-free flags; does not acquire the CPU bus."""
        self._send('q')
        value = self._response(digits=1)
        return UARTStatus(bool(value & 1), bool(value & 2))

    @transaction
    def read_pc(self):
        """Requires a halted CPU."""
        self._send('P')
        return self._response(digits=4)

    @transaction
    def set_address(self, address):
        self._send('A' + encode_number(address, 4))

    @transaction
    def read8(self, address=None):
        if address is not None:
            self.set_address(address)
        self._send('r')
        return self._response(prefix=None, digits=2)

    @transaction
    def read16(self, address=None):
        if address is not None:
            self.set_address(address)
        self._send('R')
        return self._response(prefix=None, digits=4)

    @transaction
    def read_words(self, count, address=None, *, on_progress=None):
        """Read consecutive words, sending the next R after the third hex digit.

        At most one following read is in flight. The last word is fully drained
        before return. Progress counts complete words received.
        """
        if not isinstance(count, int) or count < 0:
            raise ValueError('count must be a nonnegative integer')
        if not count:
            return []
        if address is not None:
            self.set_address(address)
        words = []
        self._send('R')
        for index in range(count):
            low = self._response(prefix=None, digits=3)
            if index + 1 < count:
                self._send('R')
            high = self._response(prefix=None, digits=1)
            words.append(low | (high << 12))
            if on_progress:
                on_progress(len(words))
        return words

    def _write(self, values, digits, address):
        if address is not None:
            self.set_address(address)
        self._send('w' if digits == 2 else 'W')
        for value in values:
            self._send(encode_number(value, digits))
            self._response()  # never send the next value before its predecessor's ACK

    @transaction
    def write_bytes(self, values, address=None):
        self._write(values, 2, address)

    @transaction
    def write_words(self, values, address=None):
        self._write(values, 4, address)

    @transaction
    def write_words_stream(self, values, address=None, *, write_delay=0, on_progress=None):
        """SRAM loader: send ahead while counting OKs, with no automatic retry.

        This deliberately relaxes the per-value wait rule. A missed character
        may corrupt subsequent writes; a failed transfer must be reloaded in full.
        """
        if write_delay < 0 or not float(write_delay) < float('inf'):
            raise ValueError('write_delay must be finite and nonnegative')
        words = [encode_number(value, 4) for value in values]
        if not words:
            return
        if address is not None:
            self.set_address(address)
        self._send('W')
        stop = threading.Event()
        errors = []

        def send():
            try:
                if write_delay:
                    for word in words:
                        if stop.is_set():
                            return
                        self._send(word)
                        # Delay after the physical write, rather than filling
                        # the USB output queue with nominally spaced writes.
                        flush = getattr(self.transport, 'flush', None)
                        if flush:
                            flush()
                        if stop.wait(write_delay):
                            return
                else:
                    for offset in range(0, len(words), 256):
                        if stop.is_set():
                            return
                        self._send(''.join(words[offset:offset + 256]))
            except Exception as exc:
                errors.append(exc)

        sender = threading.Thread(target=send, daemon=True)
        received = 0
        sender.start()
        try:
            while received < len(words):
                char = self._debug_char(time.monotonic() + self.timeout + write_delay)
                if char != 'K':
                    raise RuntimeError(f'Expected write OK, received {char!r}')
                received += 1
                if on_progress:
                    on_progress(received)
            sender.join(timeout=self.timeout + write_delay)
            if sender.is_alive():
                raise DebugTimeout('UART sender did not finish')
            if errors:
                raise errors[0]
        except Exception as exc:
            stop.set()
            for method in ('cancel_write', 'reset_output_buffer'):
                cleanup = getattr(self.transport, method, None)
                if cleanup:
                    try:
                        cleanup()
                    except OSError:
                        pass  # Preserve the transfer error if USB is already gone.
            if errors:
                exc = errors[0]
            raise RuntimeError(f'Streaming load failed after {received}/{len(words)} word OKs: {exc}. '
                               'No retry performed; restart the connection and reload the complete image.') from exc
        finally:
            stop.set()
            sender.join(timeout=self.timeout)
