"""Teste de integração opcional com Tkinter real: python -B tests/gui_smoke.py."""
import contextlib
import ctypes
import io
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import main
from gui.window import SimulatorWindow
from simulator import state_list


def replace(entry, value):
    entry.delete(0, 'end')
    entry.insert(0, str(value))


def main_test():
    if sys.platform == 'win32':
        # Alinha as coordenadas do Tkinter e da captura em monitores com escala DPI.
        ctypes.windll.user32.SetProcessDPIAware()
    state_list.clear()
    with tempfile.TemporaryDirectory(prefix='simulator-live-edit-') as output:
        window = SimulatorWindow(main.initialize_file, main.advance_state, state_list,
                                 main.DEFAULT_CONFIG, output)
        try:
            window.root.withdraw()
            assert state_list[-1].tick == 0
            window.select_task(2)
            assert window.task_state.get() == 'Nova'
            replace(window.system_entries['algorithm'], 'edf')
            replace(window.system_entries['num_cpus'], 3)
            window.on_apply_system()
            assert state_list[-1].algorithm == 'EDF'
            assert len(state_list[-1].processors_list) == 3
            window.on_step_forward()
            assert window.task_state.get() == 'Executando'
            replace(window.entries['duration'], 4)
            replace(window.entries['color'], '8E44AD')
            window.task_state.set('Suspensa')
            window.on_apply_task()
            assert state_list[-1].current_task(2)[1] == 'Suspensa'
            window.on_step_forward()
            assert state_list[-1].current_task(2)[0].computational_time == 1
            patterned = [item for item in window.canvas.find_all()
                         if window.canvas.type(item) == 'rectangle'
                         and window.canvas.itemcget(item, 'stipple') == 'gray25']
            assert len(patterned) >= 3
            replace(window.system_entries['num_cpus'], 1)
            window.on_apply_system()
            assert window.result.num_cpus == 1
            assert window.result.max_cpus == 3

            # A verificação visual é opcional e não adiciona dependências ao app.
            try:
                from PIL import ImageGrab
            except ImportError:
                pass
            else:
                window.root.geometry('1180x860+30+30')
                window.root.deiconify()
                window.root.attributes('-topmost', True)
                window.root.lift()
                window.root.update()
                time.sleep(0.2)
                image_path = ROOT / 'output' / 'validation' / 'live-editing.png'
                image_path.parent.mkdir(parents=True, exist_ok=True)
                x, y = window.root.winfo_rootx(), window.root.winfo_rooty()
                ImageGrab.grab(bbox=(x, y, x + window.root.winfo_width(),
                                    y + window.root.winfo_height())).save(image_path)
                window.root.attributes('-topmost', False)
                assert window.apply_task_button.winfo_ismapped()
                assert window.edit_hint.winfo_ismapped()
                assert window.apply_task_button.winfo_rooty() + window.apply_task_button.winfo_height() < y + window.root.winfo_height()
                print(f'Prévia visual: {image_path}')
                window.root.withdraw()

            # Valores inválidos deixam o mesmo retrato no histórico.
            original = state_list[-1]
            replace(window.system_entries['algorithm'], 'rr')
            with patch('gui.window.messagebox.showerror') as error:
                window.on_apply_system()
            assert state_list[-1] is original
            assert error.call_count == 1
            replace(window.system_entries['algorithm'], 'rm')
            replace(window.system_entries['num_cpus'], 2)
            window.on_apply_system()
            window.task_state.set('Pronta')
            window.on_apply_task()
            assert state_list[-1].current_task(2)[1] == 'Pronta'

            # Pausar cancela o callback, e retomar não cria duas sequências de ticks.
            window.on_run()
            assert window.is_running
            window.on_edit_focus()
            tick = state_list[-1].tick
            window.root.update()
            assert not window.is_running and state_list[-1].tick == tick
            window.on_run()
            deadline = time.monotonic() + 10
            while window.is_running:
                assert time.monotonic() < deadline
                window.root.update()
                time.sleep(0.002)
            assert state_list[-1].is_finished
            image = Path(output) / 'gantt.svg'
            ET.parse(image)
            final_tick = state_list[-1].tick
            assert window.task_state.get() == 'Finalizada'
            window.on_step_back()
            assert state_list[-1].tick == final_tick - 1
            window.on_step_forward()
            assert state_list[-1].is_finished
            assert state_list[-1].tick == final_tick
            # Inclusão e remoção reais, inclusive depois de terminar a simulação.
            window.on_add_task()
            assert window.add_task_dialog.winfo_exists()
            values = dict(id=99, color='224466', arrival=final_tick, duration=1, period=3, deadline=2, events='[]')
            for key, value in values.items():
                replace(window.add_task_fields[key], value)
            window.add_task_submit()
            assert window.selected_task_id == 99
            assert state_list[-1].current_task(99)[1] == 'Nova'
            window.on_step_forward()
            assert state_list[-1].current_task(99)[0].instance_number == 2
            window.on_remove_task()
            assert state_list[-1].current_task(99)[1] == 'Removida'
            assert str(window.apply_task_button.cget('state')) == 'disabled'
            assert str(window.remove_task_button.cget('state')) == 'disabled'
            assert any(event.description.startswith('Tarefa 99 removida') for event in state_list[-1].result.system_events)
            print(f'Tkinter real: edição de sistema/tarefa, suspensão, retomada, pausa, retorno e SVG OK (t={final_tick}).')
        finally:
            window.root.destroy()

        main.OUTPUT_DIR = output
        with contextlib.redirect_stdout(io.StringIO()):
            main.run_console(main.DEFAULT_CONFIG)
        ET.parse(Path(output) / 'gantt.svg')
        print('Modo console e SVG: OK.')


if __name__ == '__main__':
    main_test()
