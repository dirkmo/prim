"""Explicit external-tool overrides used by the integrated test runner."""
import os
from support.config import Tools


def configured_tools():
    return Tools(iverilog=os.environ.get('FORTH_IVERILOG', 'iverilog'),
                 vvp=os.environ.get('FORTH_VVP', 'vvp'))
