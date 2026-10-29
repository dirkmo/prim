"""Compatibility import for the standalone FPGA UART host library."""
from prim_debug_uart import DebugUART, DebugTimeout, Status, encode_number

__all__ = ["DebugUART", "DebugTimeout", "Status", "encode_number"]
