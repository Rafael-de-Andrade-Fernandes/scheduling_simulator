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

DEFAULT_CONFIG = os.path.join(BASE_DIR, 'configs', 'config_test.txt')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')


# Modo sem janela: executa tudo, imprime o log, gera o SVG e termina.
def run_console(file_path):
    engine = Simulator()
    ok, text = engine.load(file_path)
    if not ok:
        print(text)
        exit(1)

    engine.run_to_end()
    result = engine.view()
    print("\n".join(result.log))

    shapes, width, height = build_gantt(result)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    image_path = os.path.join(OUTPUT_DIR, 'gantt.svg')
    save_svg(shapes, width, height, image_path)
    print(f"Imagem salva em: {image_path}")


def main():
    config_path = DEFAULT_CONFIG
    console_mode = False

    for arg in sys.argv[1:]:
        if arg == '--console':
            console_mode = True
        else:
            config_path = arg

    if console_mode:
        run_console(config_path)
    else:
        run_gui(Simulator(), config_path, OUTPUT_DIR)


main()
