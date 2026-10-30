"""One serial owner with continuous reception and credit-controlled CPU input."""
import queue
import threading
import time

from . import DebugUART, DebugTimeout


class UARTSession(DebugUART):
    def __init__(self, transport, *, poll_interval=0.02, **kwargs):
        super().__init__(transport, **kwargs)
        self._stop = threading.Event()
        self._replies = queue.Queue()
        self._input = queue.Queue()
        self._write_lock = threading.Lock()
        self.poll_interval = poll_interval
        self.error = None
        self._closed = False
        self._reader = threading.Thread(target=self._receive, daemon=True)
        self._sender = threading.Thread(target=self._send_input, daemon=True)
        self._reader.start()
        self._sender.start()

    def _fail(self, exc):
        self.error = exc
        self._stop.set()
        self._replies.put(exc)

    def _receive(self):
        try:
            while not self._stop.is_set():
                data = self.transport.read(1)
                if not data:
                    continue
                byte = data[0]
                if not byte & 128:
                    if self.on_output:
                        self.on_output(bytes([byte]))
                    else:
                        self.output.append(byte)
                elif byte == (ord('B') | 128):
                    self.break_events += 1
                    if self.on_break:
                        self.on_break()
                else:
                    self._replies.put(chr(byte & 127))
        except Exception as exc:
            if not self._stop.is_set():
                self._fail(exc)

    def _debug_char(self, deadline):
        if self.error:
            raise OSError(f'UART reader failed: {self.error}')
        if self._stop.is_set():
            raise OSError('UART session is closed')
        try:
            char = self._replies.get(timeout=max(0, deadline - time.monotonic()))
        except queue.Empty:
            exc = DebugTimeout('Timed out waiting for FPGA debug UART response')
            self._fail(exc)  # Do not mistake a late reply for the next command's reply.
            raise exc
        if isinstance(char, Exception):
            raise OSError(f'UART session stopped: {char}')
        return char

    def _response(self, prefix='K', digits=0):
        try:
            return super()._response(prefix, digits)
        except RuntimeError as exc:
            self._fail(exc)
            raise

    def _send(self, text):
        with self._write_lock:
            if self.error:
                raise OSError(f'UART session failed: {self.error}')
            if self._stop.is_set():
                raise OSError('UART session is closed')
            super()._send(text)

    def write_words_stream(self, *args, **kwargs):
        with self._operation_lock:
            try:
                return super().write_words_stream(*args, **kwargs)
            except Exception as exc:
                # Pending replies cannot be associated with later commands safely.
                self._fail(exc)
                raise

    def read_words(self, *args, **kwargs):
        with self._operation_lock:
            try:
                return super().read_words(*args, **kwargs)
            except Exception as exc:
                # A callback failure can leave the following read's reply pending.
                self._fail(exc)
                raise

    def queue_cpu(self, data):
        data = bytes(data)
        if any(byte & 128 for byte in data):
            raise ValueError('CPU UART accepts seven-bit data only; UTF-8 is not supported')
        if self._stop.is_set():
            raise OSError('UART session is closed')
        for byte in data:
            self._input.put(byte)

    def _send_input(self):
        try:
            while not self._stop.is_set():
                try:
                    byte = self._input.get(timeout=0.05)
                except queue.Empty:
                    continue
                while not self._stop.is_set():
                    # A full RX register never holds the debug transaction lock.
                    if self._operation_lock.acquire(timeout=0.05):
                        try:
                            if not self.uart_status().received:
                                with self._write_lock:
                                    if self._stop.is_set():
                                        return
                                    if self.transport.write(bytes([byte])) != 1:
                                        raise OSError('Could not write CPU UART byte')
                                break
                        finally:
                            self._operation_lock.release()
                    self._stop.wait(self.poll_interval)
        except Exception as exc:
            if not self._stop.is_set():
                self._fail(exc)

    def transact(self, operation):
        """Serialize a whole command (including a load) against RX-credit polls."""
        with self._operation_lock:
            return operation()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        self._replies.put(OSError('UART session closed'))
        cancel = getattr(self.transport, 'cancel_read', None)
        if cancel:
            cancel()
        self._reader.join(timeout=1)
        self._sender.join(timeout=1)
        self.transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
