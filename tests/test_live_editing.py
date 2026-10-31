import contextlib
import io
from pathlib import Path
import pickle
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'src/core'))

from gui.gantt import BAR_TOP, LEFT, TOP, build_gantt
from gui.report import find_off_periods, make_report, make_task_status
from gui.svg_export import save_svg
from simulator import scale, start_simulation, state_list
import test_debug_mode as debug_tests


task = debug_tests.task


class LiveEditingTests(unittest.TestCase):
    def setUp(self):
        state_list.clear()
        self.addCleanup(state_list.clear)
        capture = contextlib.redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)

    def complete(self, state):
        while not state.is_finished:
            self.assertLess(state.tick, 200)
            state = scale(state)
        return state

    def test_edit_system_is_atomic_and_does_not_advance_clock(self):
        state = scale(start_simulation('RM', 1, [task(duration=3)]))
        before = pickle.dumps(state)
        edited = state.edit(algorithm=' eDf ', num_cpus='3')
        self.assertEqual(edited.tick, state.tick)
        self.assertEqual(edited.result.algorithm, 'EDF')
        self.assertEqual(edited.result.num_cpus, 3)
        self.assertEqual(len(edited.processors_list), 3)
        self.assertEqual(edited.result.timeline, state.result.timeline)
        self.assertEqual(pickle.dumps(state), before)
        self.assertEqual(len(state_list), 1)

    def test_reducing_cpus_requeues_displaced_tasks_and_preserves_history(self):
        state = scale(start_simulation('RM', 3, [task(1, duration=3), task(2, duration=3),
                                                task(3, duration=3)]))
        retained = state.processors_list[0].task_running.id
        edited = state.edit(num_cpus=1)
        self.assertEqual(len(edited.running_tasks), 1)
        self.assertEqual(edited.running_tasks[0].id, retained)
        self.assertEqual(len(edited.ready_queue), 2)
        self.assertTrue(all(item.processor is None for item in edited.ready_queue))
        self.assertTrue(all(item.computational_time == 1 for item in edited.ready_queue))
        edited = scale(edited)
        self.assertEqual([len(row) for row in edited.result.timeline], [3, 1])
        self.assertEqual(edited.result.max_cpus, 3)
        self.assertIn('CPU 3', make_report(edited.result))
        self.assertTrue(build_gantt(edited.result)[0])
        edited = scale(edited.edit(num_cpus=4))
        self.assertEqual([len(row) for row in edited.result.timeline], [3, 1, 4])
        for running in edited.running_tasks:
            self.assertIs(running.processor.task_running, running)

    def test_algorithm_change_affects_next_scheduling_decision(self):
        state = start_simulation('RM', 1, [task(1, duration=3, period=4),
                                          task(2, duration=3, period=6)])
        for _ in range(4):
            state = scale(state)
        rm = scale(state)
        edf = scale(state.edit(algorithm='edf'))
        self.assertEqual(rm.result.timeline[-1][0][0], 1)
        self.assertEqual(edf.result.timeline[-1][0][0], 2)
        self.assertEqual(edf.result.timeline[:-1], rm.result.timeline[:-1])

    def test_task_characteristics_are_validated_and_inherited(self):
        state = start_simulation('RM', 1, [task(arrival=2)])
        edited = state.edit(task_id=1, changes={'color': '#aabbcc', 'arrival': '0',
                            'duration': '2', 'period': '6', 'deadline': '6',
                            'events': "['evento1', 'evento2']"})
        current, name = edited.current_task(1)
        self.assertEqual(name, 'Nova')
        self.assertEqual(current.color, 'AABBCC')
        self.assertEqual(current.events, ['evento1', 'evento2'])
        self.assertEqual(current.absolute_deadline, 6)
        edited = scale(scale(edited))
        current, name = edited.current_task(1)
        self.assertEqual((current.instance_number, current.arrival, name), (2, 6, 'Nova'))
        self.assertEqual((current.duration, current.color, current.events),
                         (2, 'AABBCC', ['evento1', 'evento2']))

    def test_invalid_edits_do_not_partially_change_state(self):
        state = start_simulation('RM', 1, [task()])
        before = pickle.dumps(state)
        invalid = [dict(algorithm='rr', num_cpus=3), dict(algorithm='edf', num_cpus=0),
                   dict(num_cpus='1.5'), dict(task_id=99), dict(task_id=1, task_state='x'),
                   dict(task_id=1, changes={'color': '123'}),
                   dict(task_id=1, changes={'duration': 0}),
                   dict(task_id=1, changes={'period': 0}),
                   dict(task_id=1, changes={'events': '[1]'}),
                   dict(task_id=1, changes={'events': '__import__("os")'}),
                   dict(task_id=1, changes={'unknown': 1})]
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    state.edit(**changes)
                self.assertEqual(pickle.dumps(state), before)

    def test_all_states_are_reflected_by_actual_queues(self):
        state = start_simulation('RM', 1, [task(duration=2)])
        for name in ('Pronta', 'Executando', 'Suspensa', 'Pronta', 'Nova', 'Finalizada'):
            state = state.edit(task_id=1, task_state=name)
            if name == 'Finalizada':
                self.assertEqual(state.terminated_tasks[0].instance_number, 1)
                self.assertEqual(state.current_task(1)[0].instance_number, 2)
            else:
                current, actual = state.current_task(1)
                self.assertEqual(actual, name)
                self.assertIn(current, dict(state.task_queues())[name])
                self.assertEqual(current.processor is not None, name == 'Executando')

    def test_returning_to_new_at_same_tick_does_not_duplicate_arrival(self):
        state = start_simulation('RM', 1, [task()])
        state = state.edit(task_id=1, task_state='Pronta')
        state = state.edit(task_id=1, task_state='Nova')
        state = scale(state)
        self.assertEqual(sum(event.kind == 'arrival' for event in state.result.events), 1)

    def test_finishing_new_task_records_arrival_and_finish_at_current_tick(self):
        state = start_simulation('RM', 1, [task()])
        state = state.edit(task_id=1, task_state='Finalizada')
        self.assertEqual([(event.kind, event.tick) for event in state.result.events],
                         [('arrival', 0), ('finish', 0)])

    def test_executing_requires_a_free_cpu(self):
        state = start_simulation('RM', 1, [task(1), task(2)])
        state = state.edit(task_id=1, task_state='Executando')
        before = pickle.dumps(state)
        with self.assertRaisesRegex(ValueError, 'ocupados'):
            state.edit(task_id=2, task_state='Executando')
        self.assertEqual(pickle.dumps(state), before)
        state = state.edit(task_id=1, task_state='Pronta')
        state = state.edit(task_id=2, task_state='Executando')
        self.assertEqual(state.processors_list[0].task_running.id, 2)

    def test_future_arrival_and_already_executed_work_cannot_be_overridden(self):
        state = start_simulation('RM', 1, [task(arrival=3, duration=4, period=10)])
        for target in ('Pronta', 'Executando', 'Suspensa', 'Finalizada'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'ainda não chegou'):
                state.edit(task_id=1, task_state=target)
        state = state.edit(task_id=1, changes={'arrival': 0})
        state = scale(scale(state))
        with self.assertRaisesRegex(ValueError, 'já ocorreu'):
            state.edit(task_id=1, changes={'arrival': 2})
        with self.assertRaisesRegex(ValueError, 'já executados'):
            state.edit(task_id=1, changes={'duration': 2})
        with self.assertRaisesRegex(ValueError, 'já executados'):
            state.edit(task_id=1, changes={'duration': 1}, task_state='Finalizada')
        with self.assertRaisesRegex(ValueError, 'não pode voltar'):
            state.edit(task_id=1, task_state='Nova')
        state = state.edit(task_id=1, changes={'duration': 2}, task_state='Finalizada')
        self.assertEqual(len(state.terminated_tasks), 1)

    def test_suspension_retains_progress_and_releases_cpu(self):
        state = scale(scale(start_simulation('RM', 1, [task(duration=4, period=10)])))
        before = pickle.dumps(state)
        suspended = state.edit(task_id=1, task_state='suspensa')
        self.assertFalse(suspended.is_finished)
        self.assertFalse(suspended.is_blocked)  # As próximas liberações periódicas continuam agendadas.
        self.assertIsNone(suspended.processors_list[0].task_running)
        advanced = scale(suspended)
        self.assertEqual(advanced.current_task(1)[0].computational_time, 2)
        self.assertEqual(advanced.result.timeline[-1], [None])
        self.assertEqual(advanced.result.suspended_timeline[-1], [(1, 1)])
        resumed = scale(advanced.edit(task_id=1, task_state='Pronta'))
        self.assertEqual(resumed.current_task(1)[0].computational_time, 3)
        self.assertEqual(resumed.result.suspended_timeline[-1], [])
        self.assertEqual(pickle.dumps(state), before)

    def test_oldest_unfinished_instance_remains_selected_when_instances_overlap(self):
        state = start_simulation('RM', 1, [task(duration=6, period=2)])
        for _ in range(5):
            state = scale(state)
        self.assertEqual(state.current_task(1)[0].instance_number, 1)
        state = state.edit(task_id=1, task_state='Suspensa')
        state = scale(state)
        current, name = state.current_task(1)
        self.assertEqual((current.instance_number, name), (1, 'Suspensa'))
        self.assertTrue(any(item.instance_number == 2 for item in state.running_tasks))
        state = state.edit(task_id=1, task_state='Finalizada')
        self.assertEqual(state.current_task(1)[0].instance_number, 2)
        numbers = [item.instance_number for _, queue in state.task_queues() for item in queue]
        self.assertEqual(sorted(numbers), [1, 2, 3, 4])

    def test_suspended_instance_can_miss_deadline_without_running(self):
        state = start_simulation('RM', 1, [task(duration=3, period=2)])
        state = state.edit(task_id=1, task_state='Suspensa')
        for _ in range(3):
            state = scale(state)
        misses = [event for event in state.result.events if event.kind == 'deadline_miss']
        self.assertEqual([(event.instance, event.tick) for event in misses], [(1, 2)])
        self.assertEqual(state.suspended_tasks[0].computational_time, 0)
        self.assertEqual(state.running_tasks[0].instance_number, 2)
        shapes, _, _ = build_gantt(state.result)
        self.assertTrue(any(shape.task_id == 1 and shape.pattern == 'dots' for shape in shapes))

    def test_current_instance_falls_back_to_latest_finished_instance(self):
        state = self.complete(start_simulation('RM', 1, [task()]))
        current, name = state.current_task(1)
        self.assertEqual((current.instance_number, name), (10, 'Finalizada'))
        self.assertEqual(len(state.terminated_tasks), 10)
        with self.assertRaisesRegex(ValueError, 'não pode ser reaberta'):
            state.edit(task_id=1, task_state='Pronta')

    def test_manual_finish_records_current_tick_and_schedules_next_once(self):
        state = scale(start_simulation('RM', 1, [task(duration=3, period=5)]))
        state = state.edit(task_id=1, task_state='Finalizada')
        self.assertEqual(state.tick, 1)
        self.assertEqual(state.result.events[-1].kind, 'finish')
        self.assertEqual(state.result.events[-1].tick, 1)
        self.assertEqual([(item.instance_number, item.arrival) for item in state.tasks_to_arrival], [(2, 5)])
        state = self.complete(state)
        self.assertEqual([event.instance for event in state.result.events if event.kind == 'arrival'], list(range(1, 11)))

    def test_completed_task_characteristics_can_be_inspected_and_edited(self):
        state = self.complete(start_simulation('RM', 1, [task()]))
        edited = state.edit(task_id=1, changes={'color': '0000ff'})
        self.assertTrue(edited.is_finished)
        self.assertEqual(edited.current_task(1)[0].color, '0000FF')
        self.assertEqual(edited.result.task_colors, state.result.task_colors)

    def test_color_changes_only_affect_new_intervals(self):
        state = scale(start_simulation('RM', 1, [task(duration=4, period=10)]))
        state = scale(state.edit(task_id=1, changes={'color': '0000FF'}))
        self.assertEqual(state.result.task_colors, [{1: 'FF0000'}, {1: '0000FF'}])
        shapes, _, _ = build_gantt(state.result)
        bars = [shape for shape in shapes if shape.task_id == 1 and shape.kind == 'rect'
                and shape.y1 == TOP + BAR_TOP]
        self.assertEqual([(shape.x1, shape.fill) for shape in bars], [(LEFT, '#FF0000'), (LEFT + 34, '#0000FF')])

    def test_absent_cpus_are_not_reported_as_off(self):
        state = scale(start_simulation('RM', 1, [task(duration=4, period=10)]))
        state = scale(state.edit(num_cpus=3))
        state = scale(state.edit(num_cpus=1))
        self.assertEqual(find_off_periods(state.result, 1), [(1, 2)])
        self.assertEqual(find_off_periods(state.result, 2), [(1, 2)])
        self.assertEqual(dict(make_task_status(state.result, 1))['Ticks executados'], '3')
        self.assertTrue(build_gantt(state.result)[0])

    def test_svg_contains_black_dot_pattern_in_legend_and_task_row(self):
        state = scale(start_simulation('RM', 1, [task(duration=3)]))
        state = scale(state.edit(task_id=1, task_state='Suspensa'))
        shapes, width, height = build_gantt(state.result)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gantt.svg'
            save_svg(shapes, width, height, path)
            root = ET.parse(path).getroot()
        ns = {'s': 'http://www.w3.org/2000/svg'}
        circle = root.find('s:defs/s:pattern/s:circle', ns)
        self.assertEqual(circle.attrib['fill'], '#000000')
        patterned = [rect for rect in root.findall('s:rect', ns)
                     if rect.attrib.get('fill') == 'url(#suspended-dots)']
        self.assertGreaterEqual(len(patterned), 3)  # Intervalo, estado atual e legenda.

    def test_gui_applies_edit_to_current_snapshot_and_back_restores_previous(self):
        window = debug_tests.DebugModeTests().make_window()
        window.on_step_forward()
        previous = state_list[0]
        before = pickle.dumps(previous)
        current_tick = state_list[-1].tick
        window.apply_edit(algorithm='edf', num_cpus='3')
        self.assertEqual(len(state_list), 2)
        self.assertEqual(state_list[-1].tick, current_tick)
        self.assertEqual(state_list[-1].algorithm, 'EDF')
        self.assertEqual(pickle.dumps(previous), before)
        window.on_step_back()
        self.assertIs(state_list[-1], previous)
        self.assertEqual(state_list[-1].algorithm, 'RM')

    def test_gui_invalid_edit_reports_reason_and_keeps_original_snapshot(self):
        window = debug_tests.DebugModeTests().make_window()
        window.on_step_forward()
        previous = state_list[-1]
        with patch('gui.window.messagebox.showerror') as error:
            window.apply_edit(algorithm='rr', num_cpus=3)
        self.assertIs(state_list[-1], previous)
        self.assertIn('RM ou EDF', error.call_args.args[1])

    def test_gui_focus_pauses_execution_and_cancels_scheduled_tick(self):
        window = debug_tests.DebugModeTests().make_window()
        window.on_step_forward()
        window.on_run()
        timer = window.after_id
        tick = state_list[-1].tick
        window.on_edit_focus()
        self.assertFalse(window.is_running)
        window.root.after_cancel.assert_called_once_with(timer)
        window.pending.pop(0)()  # Mesmo um callback pendente não executa após a pausa.
        self.assertEqual(state_list[-1].tick, tick)

    def test_gui_can_edit_task_fields_and_state_through_existing_form(self):
        window = debug_tests.DebugModeTests().make_window()
        start_simulation('RM', 1, [task(duration=3)])
        window.selected_task_id = 1
        window.entries = {'color': Mock(get=Mock(return_value='00ff00')),
                          'duration': Mock(get=Mock(return_value='4'))}
        window.task_state = Mock(get=Mock(return_value='Suspensa'))
        window.on_apply_task()
        current, name = state_list[-1].current_task(1)
        self.assertEqual((current.color, current.duration, name), ('00FF00', 4, 'Suspensa'))

    def test_gui_blocks_unattended_run_with_only_suspended_tasks(self):
        window = debug_tests.DebugModeTests().make_window()
        start_simulation('RM', 1, [task(duration=3)])
        window.apply_edit(task_id=1, task_state='Suspensa')
        window.on_run()
        while window.pending:
            window.pending.pop(0)()
        self.assertFalse(window.is_running)
        self.assertTrue(state_list[-1].is_blocked)
        tick = state_list[-1].tick
        self.assertIn('aguardando retomada', window.state_message(state_list[-1]))
        window.on_step_forward()
        self.assertEqual(state_list[-1].tick, tick + 1)


if __name__ == '__main__':
    unittest.main()
