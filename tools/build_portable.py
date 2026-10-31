"""Gera a pasta e o ZIP autônomos para Windows, usando o ambiente de compilação."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def build():
    if sys.platform != 'win32':
        raise SystemExit('A distribuição Windows deve ser compilada no Windows.')
    destination = ROOT / 'output' / 'distribuicao'
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                    '--distpath', str(destination), '--workpath', str(ROOT / 'build'),
                    str(ROOT / 'packaging' / 'Simulador.spec')], cwd=ROOT, check=True)
    bundle = destination / 'SimuladorEscalonamento'
    shutil.copytree(ROOT / 'configs', bundle / 'configs', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'README.md', bundle / 'LEIA-ME.md')
    licenses = bundle / 'licenses'
    licenses.mkdir(exist_ok=True)
    for name in ('LICENSE.txt', 'LICENSE'):
        original = Path(sys.base_prefix) / name
        if original.is_file():
            shutil.copy2(original, licenses / 'Python-LICENSE.txt')
            break
    manifest = dict(python=sys.version, pyinstaller=importlib.metadata.version('pyinstaller'),
                    fontes={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted((ROOT / 'src').rglob('*.py'))})
    (bundle / 'manifesto.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.make_archive(str(destination / 'SimuladorEscalonamento-Windows-x64'), 'zip',
                        root_dir=destination, base_dir=bundle.name)
    print(f'Distribuição: {bundle}')


if __name__ == '__main__':
    build()
