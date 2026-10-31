"""Diagnóstico usado para comprovar o isolamento do pacote redistribuível."""
import contextlib
import ctypes
import io
import json
from pathlib import Path
import sys
import tkinter
import _tkinter


def loaded_library(name):
    """Obtém o caminho real da DLL carregada, em vez de inferir pelo PATH."""
    if sys.platform != 'win32':
        return None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    kernel.GetModuleFileNameW.restype = ctypes.c_uint
    handle = kernel.GetModuleHandleW(name)
    if not handle:
        return None
    buffer = ctypes.create_unicode_buffer(32768)
    kernel.GetModuleFileNameW(handle, buffer, len(buffer))
    return buffer.value


def write_runtime_report(target):
    """Exercita Python, Tk e o calendário sem abrir janela visível ao usuário."""
    from TCB import TCB
    from simulator import run_simulation
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_simulation('EDF', 2, [TCB(['1', 'FF0000', '0', '5', '3', '6', '[]'])])
    root = tkinter.Tk()
    root.withdraw()
    try:
        tcl_library = root.tk.eval('info library')
        tk_library = root.tk.eval('set tk_library')
        root.update_idletasks()
    finally:
        root.destroy()
    arrivals = [event.tick for event in result.events if event.kind == 'arrival']
    finishes = [event for event in result.events if event.kind == 'finish']
    dll_names = [f'python{sys.version_info.major}{sys.version_info.minor}.dll',
                 'tcl' + _tkinter.TCL_VERSION.replace('.', '') + 't.dll',
                 'tk' + _tkinter.TK_VERSION.replace('.', '') + 't.dll']
    payload = dict(frozen=bool(getattr(sys, 'frozen', False)), executable=sys.executable,
                   bundle=getattr(sys, '_MEIPASS', None), python=sys.version,
                   tkinter_module=_tkinter.__file__, tcl_library=tcl_library, tk_library=tk_library,
                   loaded_libraries={name: loaded_library(name) for name in dll_names},
                   arrivals=arrivals, finishes=len(finishes), total_ticks=result.total_ticks,
                   ok=arrivals == list(range(0, 30, 3)) and len(finishes) == 10)
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if payload['ok'] else 1
