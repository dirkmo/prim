"""Blocking client for the FPGA debug UART (115200, 8N1).

Pass a byte transport with read(size), write(data), and a bounded read timeout,
for example serial.Serial(port, 115200, timeout=0.1). No pyserial dependency is
needed unless connect() is used. One caller/operation at a time.
"""
from dataclasses import dataclass
import time


class DebugTimeout(TimeoutError):
    """The FPGA did not complete a debug response before the deadline."""


@dataclass(frozen=True)
class Status:
    halted: bool
    break_reason: bool


def encode_number(value: int, digits: int) -> str:
    if not 0 <= value < 1 << (4 * digits):
        raise ValueError(f'value must fit in {digits * 4} bits')
    return f'{value:0{digits}x}'[::-1]


class DebugUART:
    def __init__(self, transport, *, timeout=2.0, on_output=None, on_break=None):
        if timeout <= 0:
            raise ValueError('timeout must be positive')
        self.transport = transport
        self.timeout = timeout
        if hasattr(transport, 'timeout'):
            transport.timeout = min(timeout, 0.1)
        self.on_output, self.on_break = on_output, on_break
        self.output = bytearray()
        self.break_events = 0

    @classmethod
    def connect(cls, port, **kwargs):
        """Open pyserial at fixed 115200 baud, 8N1; caller closes transport."""
        import serial
        return cls(serial.Serial(port, baudrate=115200, bytesize=8,
                                 parity='N', stopbits=1, timeout=0.1), **kwargs)

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
        char = self._debug_char(deadline)
        if char != prefix:
            raise RuntimeError(f'Expected debug response {prefix!r}, received {char!r}')
        text = ''.join(self._debug_char(deadline) for _ in range(digits))
        if any(c not in '0123456789abcdef' for c in text):
            raise RuntimeError(f'Invalid debug hex response: {text!r}')
        return int(text[::-1], 16) if digits else None

    def halt(self):
        self._send('H')
        self._response()

    def run(self):
        self._send('G')
        self._response()

    def step(self):
        """Requires a halted CPU; BREAK notifications are handled while waiting."""
        self._send('S')
        self._response()

    def reset_halt(self):
        self._send('Z')
        self._response()

    def status(self):
        """Also resets an incomplete address/write input; does not abort a bus access."""
        self._send('?')
        value = self._response('T', 1)
        return Status(bool(value & 1), bool(value & 2))

    def read_pc(self):
        """Requires a halted CPU."""
        self._send('P')
        return self._response(digits=4)

    def set_address(self, address):
        self._send('A' + encode_number(address, 4))

    def read8(self, address=None):
        if address is not None:
            self.set_address(address)
        self._send('r')
        return self._response(digits=2)

    def read16(self, address=None):
        if address is not None:
            self.set_address(address)
        self._send('R')
        return self._response(digits=4)

    def _write(self, values, digits, address):
        if address is not None:
            self.set_address(address)
        self._send('w' if digits == 2 else 'W')
        for value in values:
            self._send(encode_number(value, digits))
            self._response()  # never send the next value before its predecessor's ACK

    def write_bytes(self, values, address=None):
        self._write(values, 2, address)

    def write_words(self, values, address=None):
        self._write(values, 4, address)
