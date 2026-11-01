"""Entrada CLI/GUI e adaptação de caminhos para código-fonte e distribuição autônoma."""
# Uso:
#   python -B src/main.py [arquivo_de_configuracao]              abre a janela
#   python -B src/main.py [arquivo_de_configuracao] --console    roda sem janela e salva o SVG

import argparse
import os
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SRC_DIR)

# O script pode ser iniciado de outro diretório. Os módulos do núcleo usam
# imports diretos entre si, por isso o caminho precisa partir deste arquivo.
sys.path.insert(0, os.path.join(SRC_DIR, 'core'))

from simulator import Simulator
from gui.window import run_gui
from gui.gantt import build_gantt
from gui.svg_export import save_svg


def default_paths():
    config = os.path.join(BASE_DIR, 'configs', 'config.txt')
    output = os.path.join(BASE_DIR, 'output')
    if getattr(sys, 'frozen', False):
        # Distribuição empacotada: dados graváveis ficam ao lado do executável,
        # não dentro do runtime embarcado.
        app_dir = os.path.dirname(sys.executable)
        external_config = os.path.join(app_dir, 'configs', 'config.txt')
        if os.path.exists(external_config):
            config = external_config
        else:
            config = os.path.join(sys._MEIPASS, 'configs', 'config.txt')
        output = os.path.join(app_dir, 'output')
    return config, output


def run_console(file_path, output_dir):
    engine = Simulator()
    try:
        engine.load(file_path)
    except ValueError as error:
        print(error)
        raise SystemExit(1)

    state = engine.run_to_end()
    print("\n".join(state.log))

    shapes, width, height = build_gantt(state.result)
    os.makedirs(output_dir, exist_ok=True)
    image_path = os.path.join(output_dir, 'gantt.svg')
    save_svg(shapes, width, height, image_path)
    print(f"Imagem salva em: {image_path}")


def main(argv=None):
    default_config, default_output = default_paths()

    parser = argparse.ArgumentParser(description='Simulador de escalonamento do Projeto A')
    parser.add_argument('config', nargs='?', default=default_config, help='Arquivo de configuração')
    parser.add_argument('--console', action='store_true', help='Executar sem interface e salvar SVG')
    parser.add_argument('--output-dir', default=default_output, help='Diretório de saída do gráfico')
    args = parser.parse_args(argv)
    output_dir = os.path.abspath(args.output_dir)

    if not args.console:
        run_gui(Simulator(), args.config, output_dir)
        return 0

    try:
        run_console(args.config, output_dir)
    except OSError as error:
        print(f'Erro ao gravar a imagem: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
