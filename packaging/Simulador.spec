# PyInstaller 6.22.3: duas entradas compartilham o mesmo Python/Tcl/Tk embarcado.
from pathlib import Path

project = Path(SPECPATH).parent
analysis = Analysis(
    [str(project / 'src' / 'main.py')],
    pathex=[str(project / 'src'), str(project / 'src' / 'core')],
    binaries=[], datas=[(str(project / 'configs'), 'configs')],
    hiddenimports=['runtime_check'], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False,
)
archive = PYZ(analysis.pure)
window = EXE(archive, analysis.scripts, [], exclude_binaries=True,
             name='Simulador', debug=False, strip=False, upx=False, console=False)
console = EXE(archive, analysis.scripts, [], exclude_binaries=True,
              name='SimuladorConsole', debug=False, strip=False, upx=False, console=True)
bundle = COLLECT(window, console, analysis.binaries, analysis.datas,
                 strip=False, upx=False, name='SimuladorEscalonamento')
