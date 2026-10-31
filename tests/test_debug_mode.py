import contextlib
import io
from pathlib import Path
import pickle
import random
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'src/core'))

import main
from TCB import TCB
from gui.gantt import build_gantt
from gui.report import make_report
from gui.window import SimulatorWindow
from simulator import run_simulation, scale, start_simulation, state_list


def task(task_id=1, arrival=0, duration=1, period=4):
    return TCB([str(task_id), 'FF0000', str(arrival), str(duration), str(period), str(period)])


def result_data(result):
    return (result.total_ticks, result.timeline,
            [(event.kind, event.tick, event.task_id, event.instance) for event in result.events])


class DebugModeTests(unittest.TestCase):
    def setUp(self):
        state_list.clear()
        previous_random_state = random.getstate()
        self.addCleanup(random.setstate, previous_random_state)
        self.addCleanup(state_list.clear)
        capture = contextlib.redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)
        random.seed(42)

    def complete(self, state):
        while not state.is_finished:
            self.assertLess(state.tick, 200, 'A simulação não terminou')
            state = scale(state)
            state_list.append(state)
        return state

    def test_initial_state_does_not_modify_input_tasks(self):
        original = task(duration=2)
        before = pickle.dumps(original)
        state = start_simulation('RM', 1, [original])
        self.assertIs(state_list[0], state)
        self.assertEqual(state.tick, 0)
        self.assertEqual(state.result.timeline, [])
        next_state = scale(state)
        self.assertEqual(pickle.dumps(original), before)
        self.assertEqual(original.computational_time, 0)
        self.assertEqual(next_state.running_tasks[0].computational_time, 1)

    def test_step_preserves_previous_snapshot_and_cpu_links(self):
        initial = start_simulation('RM', 2, [task(1, duration=3), task(2, duration=2)])
        state = scale(initial)
        before = pickle.dumps(state)
        next_state = scale(state)
        self.assertEqual(pickle.dumps(state), before)
        self.assertEqual(len(state_list), 1, 'scale não deve alterar o histórico')
        self.assertEqual(next_state.tick, 2)
        self.assertEqual(next_state.result.total_ticks, 2)
        self.assertEqual(len(next_state.result.timeline), 2)
        for running in next_state.running_tasks:
            self.assertIs(running.processor.task_running, running)
            self.assertIn(running.processor, next_state.processors_list)
        self.assertIsNot(next_state.processors_list[0], state.processors_list[0])

    def test_periodic_instances_and_idle_ticks(self):
        state = self.complete(start_simulation('RM', 1, [task()]))
        self.assertEqual(state.tick, 9)
        self.assertEqual(state.result.timeline,
                         [[(1, 1)], [None], [None], [None], [(1, 2)],
                          [None], [None], [None], [(1, 3)]])
        self.assertEqual([event.tick for event in state.result.events if event.kind == 'finish'],
                         [1, 5, 9])
        self.assertEqual(len(state_list), 10)
        for tick, snapshot in enumerate(state_list):
            self.assertEqual(snapshot.tick, tick)
            self.assertEqual(len(snapshot.result.timeline), tick)
            self.assertEqual(snapshot.result.total_ticks, tick)
            self.assertTrue(all(event.tick <= tick for event in snapshot.result.events))
            self.assertTrue(build_gantt(snapshot.result)[0])
            self.assertIn('Algoritmo: RM', make_report(snapshot.result))

    def test_deadline_boundary_is_not_a_miss(self):
        state = self.complete(start_simulation('EDF', 1, [task(duration=2, period=2)]))
        self.assertEqual(state.tick, 6)
        self.assertFalse(any(event.kind == 'deadline_miss' for event in state.result.events))

    def test_late_instances_are_not_generated_twice(self):
        state = self.complete(start_simulation('RM', 1, [task(duration=3, period=2)]))
        self.assertEqual(state.tick, 9)
        self.assertEqual([(event.instance, event.tick) for event in state.result.events
                          if event.kind == 'arrival'], [(1, 0), (2, 2), (3, 4)])
        self.assertEqual([event.tick for event in state.result.events if event.kind == 'deadline_miss'],
                         [2, 4, 6])
        self.assertEqual(sum(event.kind == 'finish' for event in state.result.events), 3)

    def test_delayed_first_arrival(self):
        state = self.complete(start_simulation('RM', 2, [task(arrival=3)]))
        self.assertEqual(state.result.timeline[:3], [[None, None]] * 3)
        self.assertEqual(state.tick, 12)

    def test_replay_preserves_random_ties_without_changing_global_rng(self):
        state = start_simulation('RM', 1, [task(1), task(2), task(3)])
        first = scale(state)
        self.assertTrue(any(event.kind == 'draw' for event in first.result.events))
        random.seed(999)
        global_rng = random.getstate()
        replay = scale(state)
        self.assertEqual(pickle.dumps(replay), pickle.dumps(first))
        self.assertEqual(random.getstate(), global_rng)

    def test_full_and_stepwise_runs_match_for_both_algorithms(self):
        tasks = [task(1, duration=5, period=6), task(2, arrival=1, duration=2, period=4),
                 task(3, duration=2, period=5)]
        for algorithm in ('RM', 'EDF'):
            with self.subTest(algorithm=algorithm):
                random.seed(42)
                complete_result = run_simulation(algorithm, 2, tasks)
                random.seed(42)
                state = self.complete(start_simulation(algorithm, 2, tasks))
                self.assertEqual(result_data(state.result), result_data(complete_result))
                for snapshot in state_list:
                    for row in snapshot.result.timeline:
                        active = [entry for entry in row if entry is not None]
                        self.assertEqual(len(active), len(set(active)))
                    for running in snapshot.running_tasks:
                        self.assertIs(running.processor.task_running, running)
                    for cpu in snapshot.processors_list:
                        if cpu.task_running is not None:
                            self.assertIn(cpu.task_running, snapshot.running_tasks)

    def test_finished_state_does_not_create_another_tick(self):
        state = self.complete(start_simulation('RM', 1, [task()]))
        self.assertIs(scale(state), state)

    def test_new_simulation_resets_shared_list_in_place(self):
        shared_list = state_list
        old = start_simulation('RM', 1, [task()])
        state_list.append(scale(old))
        new = start_simulation('EDF', 2, [task(2)])
        self.assertIs(shared_list, state_list)
        self.assertEqual(state_list, [new])

    def make_window(self):
        window = SimulatorWindow.__new__(SimulatorWindow)
        window.state_list = state_list
        window.start_simulation = Mock(wraps=main.initialize_file)
        window.step_simulation = main.advance_state
        window.config_path = str(ROOT / 'configs/config.txt')
        window.is_running = False
        window.after_id = None
        window.result = None
        window.draw_state = Mock(side_effect=lambda state: setattr(window, 'result', state.result))
        window.update_controls = Mock()
        window.finish_simulation = Mock()
        window.show_message = Mock()
        window.pending = []
        window.root = Mock()
        def schedule(delay, callback):
            window.pending.append(callback)
            return f'after{window.root.after.call_count}'
        window.root.after.side_effect = schedule
        return window

    def test_gui_back_discards_future_and_can_return_to_zero(self):
        window = self.make_window()
        window.on_step_back()
        self.assertEqual(state_list, [])
        window.on_step_forward()
        window.on_step_forward()
        discarded = state_list[-1]
        previous = state_list[-2]
        window.on_step_back()
        self.assertIs(state_list[-1], previous)
        window.draw_state.assert_called_with(previous)
        window.on_step_forward()
        replay = state_list[-1]
        self.assertIsNot(replay, discarded)
        self.assertEqual(result_data(replay.result), result_data(discarded.result))
        self.assertEqual(replay.log, discarded.log)
        self.assertNotIn('TICK: 1', previous.log)
        window.on_step_back()
        window.on_step_back()
        window.on_step_back()
        self.assertEqual(len(state_list), 1)
        self.assertEqual(state_list[-1].tick, 0)
        self.assertEqual(window.result.timeline, [])

    def test_gui_run_continues_current_state_and_draws_every_tick(self):
        window = self.make_window()
        window.on_step_forward()
        window.on_step_forward()
        window.on_step_back()
        prefix = list(state_list)
        window.on_run()
        window.on_run()  # Não agenda uma segunda execução.
        self.assertEqual(len(window.pending), 1)
        while window.pending:
            window.pending.pop(0)()
            self.assertLess(len(state_list), 200)
        self.assertFalse(window.is_running)
        self.assertTrue(state_list[-1].is_finished)
        self.assertTrue(all(state_list[index] is state for index, state in enumerate(prefix)))
        self.assertEqual(window.start_simulation.call_count, 1)
        window.finish_simulation.assert_called_once()
        drawn_ticks = [call.args[0].tick for call in window.draw_state.call_args_list]
        self.assertEqual(drawn_ticks[-(state_list[-1].tick - 1):],
                         list(range(2, state_list[-1].tick + 1)))
        length = len(state_list)
        window.on_step_forward()
        window.on_run()
        self.assertEqual(len(state_list), length)

    def test_gui_manual_completion_and_back_from_finished_state(self):
        window = self.make_window()
        window.on_step_forward()
        while not state_list[-1].is_finished:
            window.on_step_forward()
            self.assertLess(len(state_list), 200)
        finished = state_list[-1]
        window.finish_simulation.assert_called_once()
        window.on_step_back()
        self.assertFalse(state_list[-1].is_finished)
        window.on_step_forward()
        self.assertEqual(result_data(state_list[-1].result), result_data(finished.result))
        self.assertEqual(window.finish_simulation.call_count, 2)

    def test_invalid_config_leaves_no_partial_history(self):
        window = self.make_window()
        window.config_path = str(ROOT / 'configs/missing_debug_test.txt')
        with patch('gui.window.messagebox.showerror') as showerror:
            window.on_step_forward()
        self.assertEqual(state_list, [])
        self.assertIsNone(window.result)
        showerror.assert_called_once()
        window.draw_state.assert_not_called()

    def test_open_config_resets_result_and_history(self):
        window = self.make_window()
        window.on_step_forward()
        window.path_label = Mock()
        window.canvas = Mock()
        window.select_task = Mock()
        new_path = str(ROOT / 'configs/config.txt')
        with patch('gui.window.filedialog.askopenfilename', return_value=new_path):
            window.on_open()
        self.assertEqual(len(state_list), 1)
        self.assertEqual(state_list[0].tick, 0)
        self.assertEqual(window.result.timeline, [])
        self.assertEqual(window.shapes, [])
        window.select_task.assert_called_once_with(0)
        window.on_step_forward()
        self.assertEqual(state_list[-1].tick, 1)

    def test_console_result_matches_gui_result_and_logs(self):
        random.seed(42)
        result, log = main.simulate_file(str(ROOT / 'configs/config.txt'))
        self.assertIsNotNone(result)
        random.seed(42)
        state, initial_log = main.initialize_file(str(ROOT / 'configs/config.txt'))
        self.assertEqual(state.log, initial_log)
        while not state.is_finished:
            state = main.advance_state(state)
        self.assertEqual(result_data(state.result), result_data(result))
        self.assertEqual(state.log, log)


if __name__ == '__main__':
    unittest.main()
