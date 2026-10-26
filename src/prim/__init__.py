"""Prim stack CPU and TokenForth tools; optional tools load only on demand."""
from importlib import import_module

_EXPORTS = {'Prim': 'cpu', 'MemoryIf': 'cpu', 'PrimAsm': 'assembler',
            'Consts': 'isa', 'PrimOpcodes': 'isa'}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(f'.{_EXPORTS[name]}', __name__), name)
    globals()[name] = value
    return value
