"""Valida o ZIP pronto sem usar Python/Tcl/Tk do PATH ou das variáveis externas."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def verify(execute=True):
    out = ROOT / 'output' / 'validacao_final'
    stage = out / ('isolado-' + uuid.uuid4().hex[:8])
    stage.mkdir(parents=True, exist_ok=False)
    archive = ROOT / 'output' / 'distribuicao' / 'SimuladorEscalonamento-Windows-x64.zip'
    with zipfile.ZipFile(archive) as bundle_zip:
        # O arquivo é nosso, mas a extração ainda confere que os destinos ficam
        # dentro da área de teste; nenhum caminho externo pode ser sobrescrito.
        for member in bundle_zip.infolist():
            if not (stage / member.filename).resolve().is_relative_to(stage.resolve()):
                raise RuntimeError('Caminho inválido no ZIP da distribuição')
        bundle_zip.extractall(stage)
    bundle = stage / 'SimuladorEscalonamento'
    manifest = json.loads((bundle / 'manifesto.json').read_text(encoding='utf-8'))
    for name, expected in manifest['fontes'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, f'Binário desatualizado: {name}'
    runtime_files = ('python312.dll', '_tkinter.pyd', 'tcl86t.dll', 'tk86t.dll')
    included = {name: [str(path.relative_to(bundle)) for path in bundle.rglob(name)] for name in runtime_files}
    assert all(included.values()), included
    if not execute:
        result = dict(ok=False, static_ok=True, executado=False, arquivos_runtime=included,
                      diretorio_isolado=str(stage), zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                      motivo='Verificação de composição apenas; execução pendente da política do Windows.')
        (out / 'composicao_portatil.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Composição validada: fontes atuais e Python/Tcl/Tk incluídos. Execução não foi realizada.')
        return result
    env = os.environ.copy()
    env['PATH'] = str(Path(env.get('SystemRoot', r'C:\Windows')) / 'System32')
    missing = str(stage / 'runtime-externo-inexistente')
    env.update(PYTHONHOME=missing, PYTHONPATH=missing, PYTHONUSERBASE=missing,
               PYTHONNOUSERSITE='1', TCL_LIBRARY=missing, TK_LIBRARY=missing)
    diagnostics = []
    for executable in ('Simulador.exe', 'SimuladorConsole.exe'):
        report = stage / (executable + '.json')
        try:
            completed = subprocess.run([str(bundle / executable), '--verify-runtime', str(report)],
                                       cwd=stage, env=env, capture_output=True, text=True,
                                       timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as error:
            result = dict(ok=False, static_ok=True, executado=False, bloqueado=True,
                          winerror=getattr(error, 'winerror', None), motivo=str(error),
                          executavel=str(bundle / executable), arquivos_runtime=included,
                          zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
            (out / 'runtime_portatil.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'Execução bloqueada pelo Windows: {error}')
            return result
        if completed.returncode:
            raise RuntimeError(f'{executable}: {completed.stdout}\n{completed.stderr}')
        result = json.loads(report.read_text(encoding='utf-8'))
        assert result['ok'] and result['frozen'] and result['finishes'] == 10
        assert result['arrivals'] == list(range(0, 30, 3))
        for key in ('bundle', 'tkinter_module', 'tcl_library', 'tk_library'):
            assert Path(result[key]).resolve().is_relative_to(bundle.resolve()), (key, result[key])
        for name, library in result['loaded_libraries'].items():
            assert library and Path(library).resolve().is_relative_to(bundle.resolve()), (name, library)
        diagnostics.append(result)
    config = stage / 'prazo independente.txt'
    config.write_text('edf;1;2\n1;FF0000;0;5;3;6;[]\n', encoding='utf-8-sig')
    console = subprocess.run([str(bundle / 'SimuladorConsole.exe'), str(config), '--console',
                              '--output-dir', str(stage / 'resultado')], cwd=stage, env=env,
                             capture_output=True, text=True, timeout=45,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    assert console.returncode == 0, console.stderr
    assert ET.parse(stage / 'resultado' / 'gantt.svg').getroot().tag.endswith('svg')
    (out / 'console_portatil.log').write_text(console.stdout + console.stderr, encoding='utf-8')
    result = dict(ok=True, executaveis=diagnostics, path_usado=env['PATH'],
                  variaveis_externas_invalidas=missing, diretorio_isolado=str(stage),
                  zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                  verificacao='Runtime embarcado e CLI/GUI exercitados; sem VM/máquina física separada.')
    (out / 'runtime_portatil.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Distribuição validada: dois executáveis, Python/Tcl/Tk embarcados, calendário de dez instâncias e SVG.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--static-only', action='store_true', help='Conferir a composição sem executar binários')
    args = parser.parse_args()
    result = verify(execute=not args.static_only)
    raise SystemExit(0 if result.get('ok') or (args.static_only and result.get('static_ok')) else 2)
