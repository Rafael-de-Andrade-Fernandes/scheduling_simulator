"""Critérios do PDF, independentes de constantes internas e de arquivos de auditoria."""
import contextlib
import io
from pathlib import Path
import pickle
import random
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'src/core'))

import main
from TCB import TCB
from choose_task import ALGORITHMS, available_algorithms, register_algorithm
from gui.gantt import build_gantt
from gui.window import SimulatorWindow
from simulator import scale, start_simulation, state_list
from test_event_scheduling import reference_run
import test_debug_mode as debug_tests


def task(index=1, arrival=0, duration=1, period=4, deadline=None):
    return TCB([str(index), 'FF0000' if index == 1 else f'{index:06X}', str(arrival),
                str(duration), str(period), str(period if deadline is None else deadline), '[]'])


class ProjectAConformanceTests(unittest.TestCase):
    def setUp(self):
        state_list.clear()
        self.addCleanup(state_list.clear)
        capture = contextlib.redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)

    def finish(self, state):
        while not state.is_finished:
            self.assertLess(state.tick, 1000)
            state = scale(state)
        return state

    def test_pdf_requires_ten_instances_and_period_calendar(self):
        state = self.finish(start_simulation('RM', 1, [task()]))
        self.assertEqual([event.tick for event in state.result.events if event.kind == 'arrival'],
                         list(range(0, 40, 4)))
        self.assertEqual([event.instance for event in state.result.events if event.kind == 'finish'],
                         list(range(1, 11)))
        self.assertEqual(state.tick, 37)

    def test_deadlines_independent_from_period_in_both_algorithms(self):
        for algorithm in ('RM', 'EDF'):
            for deadline in (2, 3, 6):
                with self.subTest(algorithm=algorithm, deadline=deadline):
                    state = self.finish(start_simulation(algorithm, 2, [task(duration=5, period=3, deadline=deadline)]))
                    self.assertEqual([event.tick for event in state.result.events if event.kind == 'arrival'],
                                     list(range(0, 30, 3)))
                    self.assertEqual(len(state.terminated_tasks), 10)
                    self.assertEqual(state.tick, 32)
                    misses = [event for event in state.result.events if event.kind == 'deadline_miss']
                    self.assertEqual(len(misses), 10 if deadline < 5 else 0)

    def test_config_accepts_bom_and_independent_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'configuração com espaço.conf'
            path.write_text('eDf;1;2;\n1;FF0000;0;5;3;6;[];\n', encoding='utf-8-sig')
            result, log = main.simulate_file(str(path))
        self.assertIsNotNone(result, log)
        self.assertEqual(result.algorithm, 'EDF')
        self.assertEqual(sum(event.kind == 'finish' for event in result.events), 10)

    def test_colors_are_unique_on_load_core_and_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cores.txt'
            path.write_text('RM;1;1\n1;AABBCC;0;1;4;4;[]\n2;aabbcc;0;1;5;5;[]\n', encoding='utf-8')
            result, log = main.simulate_file(str(path))
        self.assertIsNone(result)
        self.assertIn('color', log)
        duplicate = task(2)
        duplicate.color = 'FF0000'
        with self.assertRaises(ValueError):
            start_simulation('RM', 1, [task(), duplicate])
        state = start_simulation('RM', 1, [task(), task(2)])
        before = pickle.dumps(state)
        with self.assertRaisesRegex(ValueError, 'cor'):
            state.edit(task_id=2, changes={'color': '#ff0000'})
        self.assertEqual(pickle.dumps(state), before)

    def test_historical_colors_cannot_be_reused_by_another_task(self):
        state = scale(start_simulation('RM', 1, [task(), task(2)]))
        state = state.edit(task_id=1, changes={'color': '00AAFF'})
        with self.assertRaisesRegex(ValueError, 'cor'):
            state.edit(task_id=2, changes={'color': 'FF0000'})

    def test_edit_deadline_does_not_require_changing_period(self):
        state = start_simulation('EDF', 1, [task()])
        state = state.edit(task_id=1, changes={'deadline': 2})
        current, _ = state.current_task(1)
        self.assertEqual((current.period, current.deadline, current.absolute_deadline), (4, 2, 2))

    def test_add_remove_and_back_preserve_history(self):
        state = scale(start_simulation('RM', 1, [task(duration=3)]))
        before = pickle.dumps(state)
        added = state.edit(add_task=dict(id=2, color='00FF00', arrival=state.tick,
                                        duration=2, period=3, deadline=5))
        self.assertEqual(added.tick, 1)
        self.assertEqual(pickle.dumps(state), before)
        advanced = scale(added)
        self.assertIn((2, 1), advanced.result.timeline[-1])
        removed = advanced.edit(remove_task_id=2)
        self.assertEqual(removed.current_task(2)[1], 'Removida')
        self.assertFalse(any(job.id == 2 for job in removed.tasks_to_arrival + removed.ready_queue + removed.running_tasks))
        after = self.finish(removed)
        self.assertTrue(any(job.id == 2 for job in after.removed_tasks))
        self.assertTrue(any(event.kind == 'remove' and event.task_id == 2 for event in after.result.events))
        self.assertNotIn(2, state.removed_task_ids)
        self.assertEqual(advanced.current_task(2)[1], 'Executando')

    def test_add_invalid_or_duplicate_task_is_atomic(self):
        state = start_simulation('RM', 1, [task()])
        for fields in (dict(id=1, color='00FF00'), dict(id=2, color='FF0000'),
                       dict(id=2, color='00FF00', period=0), dict(id=2, color='00FF00', arrival=-1)):
            before = pickle.dumps(state)
            with self.assertRaises(ValueError):
                state.edit(add_task=fields)
            self.assertEqual(pickle.dumps(state), before)

    def test_adding_after_completion_restarts_from_current_clock(self):
        state = self.finish(start_simulation('RM', 1, [task()]))
        clock = state.tick
        state = state.edit(add_task=dict(id=2, color='00FF00', arrival=clock,
                                        duration=1, period=3, deadline=2))
        state = self.finish(state)
        self.assertEqual([event.tick for event in state.result.events if event.kind == 'arrival' and event.task_id == 2],
                         list(range(clock, clock + 30, 3)))

    def test_new_algorithm_is_accepted_without_changing_other_modules(self):
        register_algorithm('TEST', lambda job: -job.id)
        self.addCleanup(ALGORITHMS.pop, 'TEST')
        self.assertIn('TEST', available_algorithms())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.txt'
            path.write_text('test;1;1\n1;FF0000;0;3;10;10;[]\n2;00FF00;0;3;20;20;[]', encoding='utf-8')
            state, log = main.initialize_file(str(path))
        self.assertIsNotNone(state, log)
        state = scale(state)
        self.assertEqual(state.result.timeline[0], [(2, 1)])
        state = state.edit(algorithm='rm')
        state = scale(state)
        self.assertEqual(state.result.timeline[-1], [(1, 1)])

    def test_registered_tick_event_is_optional_and_policy_owned(self):
        def select(jobs, state, rng):
            ready = [job for job in jobs if job.processor is None]
            return ready[0] if state.tick % 2 == 0 and ready else jobs[0]
        register_algorithm('CUSTOM', selector=select, tick_event=lambda state: state.tick % 2 == 0)
        self.addCleanup(ALGORITHMS.pop, 'CUSTOM')
        state = scale(start_simulation('CUSTOM', 1, [task(1, duration=6, period=20), task(2, duration=6, period=30)]))
        state = scale(scale(state))
        self.assertEqual(state.result.timeline[0], [(1, 1)])
        self.assertEqual(state.result.timeline[2], [(2, 1)])

    def test_simultaneous_instances_have_distinct_graph_positions(self):
        state = scale(scale(scale(start_simulation('RM', 2, [task(duration=5, period=2)]))))
        shapes, _, _ = build_gantt(state.result)
        labels = [shape for shape in shapes if shape.kind == 'text' and shape.task_id == 1
                  and shape.text in ('P1/I1', 'P2/I2')]
        at_tick_two = [shape for shape in labels if shape.x1 == 185]
        self.assertEqual(len(at_tick_two), 2)
        self.assertEqual(len({shape.y1 for shape in at_tick_two}), 2)

    def test_reconfiguration_is_visible_and_does_not_recolor_history(self):
        state = scale(start_simulation('RM', 1, [task(duration=3)]))
        state = state.edit(algorithm='edf', num_cpus=2, task_id=1, changes={'color': '00AAFF'})
        shapes, _, _ = build_gantt(state.result)
        self.assertEqual(state.result.task_colors[0][1], 'FF0000')
        self.assertEqual(len(state.result.system_events), 3)
        self.assertTrue(any(shape.kind == 'text' and 'RM → EDF' in shape.text for shape in shapes))
        self.assertTrue(any(shape.kind == 'text' and shape.text == 'S1+' for shape in shapes))

    def test_manual_save_io_error_is_shown_without_exception(self):
        window = SimulatorWindow.__new__(SimulatorWindow)
        window.shapes = [object()]
        window.chart_width = window.chart_height = 100
        with patch('gui.window.filedialog.asksaveasfilename', return_value='destino.svg'), \
             patch('gui.window.save_svg', side_effect=PermissionError('Acesso negado')), \
             patch('gui.window.messagebox.showerror') as error:
            window.on_save()
        error.assert_called_once()
        self.assertIn('Acesso negado', error.call_args.args[1])

    def test_complete_mode_draws_only_the_final_state(self):
        window = debug_tests.DebugModeTests().make_window()
        window.on_run()
        while window.pending:
            window.pending.pop(0)()
        drawn = [call.args[0].tick for call in window.draw_state.call_args_list]
        self.assertEqual(drawn, [0, state_list[-1].tick])
        self.assertTrue(state_list[-1].is_finished)

    def test_general_deadlines_match_independent_reference(self):
        rng = random.Random(907)
        for case in range(8):
            periods = rng.sample([3, 5, 7, 11], 3)
            deadlines = rng.sample([2, 4, 6, 15], 3)
            specs = [(index + 1, rng.randint(0, 3), rng.randint(1, 5), periods[index], deadlines[index])
                     for index in range(3)]
            for algorithm in ('RM', 'EDF'):
                for cpus in (1, 2, 3):
                    with self.subTest(case=case, algorithm=algorithm, cpus=cpus):
                        rows, events = reference_run(specs, algorithm, cpus)
                        state = self.finish(start_simulation(algorithm, cpus,
                            [task(index, arrival, duration, period, deadline)
                             for index, arrival, duration, period, deadline in specs]))
                        self.assertEqual(state.result.timeline, rows)
                        self.assertEqual(sorted((event.kind, event.tick, event.task_id, event.instance)
                                                for event in state.result.events), sorted(events))


if __name__ == '__main__':
    unittest.main()
