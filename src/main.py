"""Entrada CLI/GUI e adaptação de caminhos para código-fonte e distribuição autônoma."""
# Ponto de entrada do simulador.
#
# Uso:
#   python3 src/main.py [arquivo_de_configuracao]              abre a janela
#   python3 src/main.py [arquivo_de_configuracao] --console    roda sem janela e salva o SVG
#
# O programa tem duas partes separadas:
#   core/  a simulação (não sabe nada de janelas nem de desenho)
#   gui/   a janela e o gráfico de Gantt (não sabe nada de como a simulação funciona)
# Este arquivo só liga uma parte na outra.

import argparse
import os
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SRC_DIR)

# Os arquivos de core/ importam uns aos outros pelo nome simples (import TCB, ...).
# Esta linha é parecida com o -I do gcc: diz ao Python em qual pasta procurá-los.
sys.path.insert(0, os.path.join(SRC_DIR, 'core'))

from simulator import Simulator
from gui.window import run_gui
from gui.gantt import build_gantt
from gui.svg_export import save_svg


# Descobre o arquivo de configuração padrão e a pasta de saída.
# Devolve (config_padrão, pasta_de_saída).
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


# Modo sem janela: executa tudo, imprime o log, gera o SVG e termina.
def run_console(file_path, output_dir):
    engine = Simulator()
    try:
        engine.load(file_path)
    except ValueError as error:
        print(error)
        exit(1)

    state = engine.run_to_end()
    print("\n".join(state.log))

    shapes, width, height = build_gantt(state.result)
    os.makedirs(output_dir, exist_ok=True)
    image_path = os.path.join(output_dir, 'gantt.svg')
    save_svg(shapes, width, height, image_path)
    print(f"Imagem salva em: {image_path}")


# A mesma entrada funciona a partir do código-fonte e da distribuição Windows.
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
