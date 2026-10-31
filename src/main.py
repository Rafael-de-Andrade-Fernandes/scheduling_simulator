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

import contextlib
import io
import os
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SRC_DIR)

# Os arquivos de core/ importam uns aos outros pelo nome simples (import TCB, ...).
# Esta linha é parecida com o -I do gcc: diz ao Python em qual pasta procurá-los.
sys.path.insert(0, os.path.join(SRC_DIR, 'core'))

from simulator import load_system, run_simulation, start_simulation, scale, state_list
from gui.window import run_gui
from gui.gantt import build_gantt
from gui.svg_export import save_svg

DEFAULT_CONFIG = os.path.join(BASE_DIR, 'configs', 'config.txt')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')


# Lê o arquivo e executa a simulação completa.
# Devolve (resultado, log). Se algo der errado, resultado é None e o log tem o motivo.
# As funções do core imprimem mensagens e chamam exit(1) em caso de erro;
# aqui guardamos tudo que foi impresso em "log" e capturamos o exit.
def simulate_file(file_path):
    log = io.StringIO()
    result = None
    try:
        with contextlib.redirect_stdout(log):
            algorithm, quantum, num_cpus, task_list = load_system(file_path)
            result = run_simulation(algorithm, num_cpus, task_list)
    except SystemExit:
        result = None
    return result, log.getvalue()


# Inicia apenas o estado de tempo zero para a interface.
def initialize_file(file_path):
    log = io.StringIO()
    state = None
    state_list.clear()
    try:
        with contextlib.redirect_stdout(log):
            algorithm, quantum, num_cpus, task_list = load_system(file_path)
            state = start_simulation(algorithm, num_cpus, task_list)
    except SystemExit:
        pass
    if state is not None:
        state.log = log.getvalue()
    return state, log.getvalue()


# O log pertence ao estado, para que o retorno descarte também as mensagens futuras.
def advance_state(current_state):
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        next_state = scale(current_state)
    next_state.log = current_state.log + log.getvalue()
    return next_state


# Modo sem janela: imprime o log, gera o SVG e termina.
def run_console(file_path):
    result, log = simulate_file(file_path)
    print(log)
    if result is None:
        exit(1)

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
        run_gui(initialize_file, advance_state, state_list, config_path, OUTPUT_DIR)


if __name__ == "__main__":
    main()
