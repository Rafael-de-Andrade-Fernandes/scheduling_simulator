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
import simulator
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
                self.assertEqual(state.current_task(1)[1], 'Finalizada')
                self.assertTrue(state.is_finished)
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
        with self.assertRaisesRegex(ValueError, 'ainda não chegou'):
            state.edit(task_id=1, task_state='Executando')
        for target in ('Pronta', 'Suspensa'):
            future = state.edit(task_id=1, task_state=target)
            self.assertEqual(future.current_task(1)[1], 'Nova')
            self.assertEqual(future.current_task(1)[0].release_state, target)
            self.assertEqual(future.result.events, [])
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
        self.assertFalse(suspended.is_blocked)  # As próximas liberações chegarão já suspensas.
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
        self.assertEqual(state.running_tasks, [])
        self.assertEqual(sorted(item.instance_number for item in state.suspended_tasks), [1, 2, 3])
        state = state.edit(task_id=1, task_state='Finalizada')
        self.assertEqual(state.current_task(1)[1], 'Finalizada')
        self.assertTrue(state.is_finished)
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
        self.assertEqual(state.running_tasks, [])
        self.assertEqual([job.instance_number for job in state.suspended_tasks], [1, 2])
        shapes, _, _ = build_gantt(state.result)
        self.assertTrue(any(shape.task_id == 1 and shape.pattern == 'dots' for shape in shapes))

    def test_current_instance_falls_back_to_latest_finished_instance(self):
        state = self.complete(start_simulation('RM', 1, [task()]))
        current, name = state.current_task(1)
        self.assertEqual((current.instance_number, name), (10, 'Finalizada'))
        self.assertEqual(len(state.terminated_tasks), 10)
        with self.assertRaisesRegex(ValueError, 'não pode ser reaberta'):
            state.edit(task_id=1, task_state='Pronta')

    def test_manual_finish_records_current_tick_and_cancels_future_releases(self):
        state = scale(start_simulation('RM', 1, [task(duration=3, period=5)]))
        state = state.edit(task_id=1, task_state='Finalizada')
        self.assertEqual(state.tick, 1)
        self.assertEqual(state.result.events[-1].kind, 'finish')
        self.assertEqual(state.result.events[-1].tick, 1)
        self.assertEqual(state.tasks_to_arrival, [])
        self.assertTrue(state.is_finished)
        state = self.complete(state)
        self.assertEqual([event.instance for event in state.result.events if event.kind == 'arrival'], [1])

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

    def overlapping_family(self, cpus=3):
        """Cria três instâncias admitidas com progresso distinto e uma futura."""
        state = start_simulation('RM', cpus, [task(duration=6, period=2)])
        for _ in range(5):
            state = scale(state)
        return state

    def test_global_suspension_covers_running_ready_and_future_instances(self):
        for cpus in (1, 3):
            with self.subTest(cpus=cpus):
                state = self.overlapping_family(cpus)
                original_state = state
                before = pickle.dumps(state)
                progress = {job.instance_number: job.computational_time
                            for job in state.running_tasks + state.ready_queue}
                state = state.edit(task_id=1, task_state='Suspensa')
                self.assertEqual(sorted(job.instance_number for job in state.suspended_tasks), [1, 2, 3])
                self.assertEqual(state.running_tasks + state.ready_queue, [])
                self.assertTrue(all(cpu.task_running is None for cpu in state.processors_list))
                for _ in range(4):
                    with patch('simulator._schedule', wraps=simulator._schedule) as schedule:
                        state = scale(state)
                    schedule.assert_not_called()
                    self.assertEqual(state.result.timeline[-1], [None] * cpus)
                self.assertEqual(sorted(job.instance_number for job in state.suspended_tasks), [1, 2, 3, 4, 5])
                self.assertEqual({job.instance_number: job.computational_time for job in state.suspended_tasks
                                  if job.instance_number <= 3}, progress)
                self.assertTrue(all(job.computational_time == 0 for job in state.suspended_tasks if job.instance_number > 3))
                self.assertTrue(all(job.release_state == 'Suspensa' for job in state.tasks_to_arrival))
                # A edição e os passos seguintes não modificam o retrato anterior.
                self.assertEqual(pickle.dumps(original_state), before)

    def test_global_resume_preserves_each_progress_and_restores_future_releases(self):
        state = self.overlapping_family()
        state = state.edit(task_id=1, task_state='Suspensa')
        for _ in range(2):
            state = scale(state)
        progress = {job.instance_number: job.computational_time for job in state.suspended_tasks}
        resumed = state.edit(task_id=1, task_state='Pronta')
        self.assertEqual(resumed.suspended_tasks, [])
        self.assertEqual({job.instance_number: job.computational_time for job in resumed.ready_queue}, progress)
        self.assertTrue(all(job.release_state == 'Pronta' for _, queue in resumed.task_queues()
                            for job in queue if job.id == 1))
        resumed = scale(resumed)
        self.assertEqual(resumed.result.suspended_timeline[-1], [])
        resumed = scale(resumed)
        self.assertFalse(any(job.instance_number == 5 for job in resumed.suspended_tasks))
        self.assertTrue(any(job.instance_number == 5 for job in resumed.ready_queue + resumed.running_tasks))

    def test_suspension_before_first_arrival_is_inherited_by_all_releases(self):
        state = start_simulation('RM', 2, [task(arrival=3, duration=1, period=2)])
        state = state.edit(task_id=1, task_state='Suspensa')
        self.assertEqual(state.current_task(1)[1], 'Nova')
        self.assertEqual(state.result.events, [])
        for _ in range(22):
            state = scale(state)
        self.assertEqual(len(state.suspended_tasks), 10)
        self.assertTrue(state.is_blocked)
        self.assertEqual([event.tick for event in state.result.events if event.kind == 'arrival'], list(range(3, 23, 2)))
        self.assertTrue(all(job.computational_time == 0 for job in state.suspended_tasks))
        self.assertTrue(all(row == [None, None] for row in state.result.timeline))

    def test_all_attributes_propagate_to_active_and_new_generations_without_rewriting_past(self):
        state = self.overlapping_family()
        prior = pickle.dumps((state.result.timeline, state.result.events, state.result.task_colors))
        state = state.edit(task_id=1, changes={'color': '8888ff', 'duration': 8, 'period': 3,
                                              'deadline': 10, 'events': "['entrada']"})
        self.assertEqual(pickle.dumps((state.result.timeline, state.result.events, state.result.task_colors)), prior)
        for _, queue in state.task_queues():
            for job in queue:
                self.assertEqual((job.color, job.duration, job.period, job.deadline, job.events),
                                 ('8888FF', 8, 3, 10, ['entrada']))
        state = state.edit(task_id=1, task_state='Suspensa')
        while state.tick <= 9:
            state = scale(state)
        newest = next(job for job in state.tasks_to_arrival if job.instance_number == 5)
        self.assertEqual((newest.arrival, newest.color, newest.duration, newest.period, newest.deadline, newest.events),
                         (12, '8888FF', 8, 3, 10, ['entrada']))
        self.assertEqual(newest.release_state, 'Suspensa')

    def test_global_execution_requires_room_for_every_admitted_instance_atomically(self):
        state = self.overlapping_family(1).edit(task_id=1, task_state='Suspensa')
        before = pickle.dumps(state)
        with self.assertRaisesRegex(ValueError, 'todas as instâncias'):
            state.edit(task_id=1, task_state='Executando', changes={'color': '8888FF'})
        self.assertEqual(pickle.dumps(state), before)
        state = state.edit(num_cpus=3)
        state = state.edit(task_id=1, task_state='Executando')
        self.assertEqual({job.instance_number for job in state.running_tasks}, {1, 2, 3})
        self.assertEqual(state.suspended_tasks + state.ready_queue, [])
        self.assertTrue(all(cpu.task_running is not None for cpu in state.processors_list))
        self.assertEqual([(job.instance_number, job.arrival) for job in state.tasks_to_arrival], [(4, 6)])

    def test_global_finish_ends_all_active_instances_and_cancels_future_calendar(self):
        state = self.overlapping_family()
        past = [row[:] for row in state.result.timeline]
        state = state.edit(task_id=1, task_state='Finalizada')
        self.assertTrue(state.is_finished)
        self.assertEqual(state.tasks_to_arrival, [])
        self.assertEqual([job.instance_number for job in state.terminated_tasks], [1, 2, 3])
        self.assertEqual([(event.instance, event.tick) for event in state.result.events if event.kind == 'finish'],
                         [(1, 5), (2, 5), (3, 5)])
        self.assertEqual(state.result.timeline, past)
        self.assertIs(scale(state), state)
        self.assertTrue(all(cpu.task_running is None for cpu in state.processors_list))

    def test_global_finish_before_arrival_cancels_without_fake_events(self):
        state = start_simulation('RM', 1, [task(arrival=10)])
        state = state.edit(task_id=1, task_state='Finalizada')
        self.assertTrue(state.is_finished)
        self.assertEqual(state.current_task(1)[1], 'Finalizada')
        self.assertEqual(state.result.events, [])

    def test_gui_color_edit_does_not_implicitly_force_all_instances_into_execution(self):
        window = debug_tests.DebugModeTests().make_window()
        state = self.overlapping_family(1)
        state_list[:] = [state]
        window.selected_task_id = 1
        window.entries = {'color': Mock(get=Mock(return_value='8888FF'))}
        window.task_state = Mock(get=Mock(return_value='Executando'))
        window.on_apply_task()
        edited = state_list[-1]
        self.assertEqual([job.instance_number for job in edited.running_tasks], [1])
        self.assertEqual([job.instance_number for job in edited.ready_queue], [2, 3])
        self.assertTrue(all(job.color == '8888FF' for _, queue in edited.task_queues() for job in queue))
        self.assertFalse(edited.reschedule_needed)

    def test_global_edit_and_replay_keep_suspension_policy_inside_each_snapshot(self):
        state = self.overlapping_family()
        original = pickle.dumps(state)
        edited = state.edit(task_id=1, task_state='Suspensa')
        first = scale(scale(edited))
        second = scale(scale(edited))
        self.assertEqual(pickle.dumps(state), original)
        self.assertEqual(pickle.dumps(first), pickle.dumps(second))
        unchanged_future = scale(scale(state))
        self.assertEqual(unchanged_future.suspended_tasks, [])
        self.assertTrue(unchanged_future.running_tasks)

    def test_completed_instances_keep_their_original_attributes(self):
        state = scale(start_simulation('RM', 2, [task(duration=1, period=3)]))
        completed = pickle.dumps(state.terminated_tasks)
        state = state.edit(task_id=1, changes={'color': '8888FF', 'duration': 3}, task_state='Suspensa')
        self.assertEqual(pickle.dumps(state.terminated_tasks), completed)
        for _ in range(3):
            state = scale(state)
        self.assertEqual([(job.instance_number, job.color, job.duration) for job in state.suspended_tasks],
                         [(2, '8888FF', 3)])


class TaskIdEditingTests(unittest.TestCase):
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

    def test_rename_before_arrival_is_inherited_by_all_ten_instances(self):
        state = start_simulation('RM', 1, [task(arrival=2)])
        edited = state.edit(task_id=1, changes={'id': ' 50 '})
        self.assertEqual(edited.tick, 0)
        self.assertEqual(edited.current_task(50)[0].id, 50)
        self.assertEqual(state.current_task(1)[0].id, 1)
        final = self.finish(edited)
        self.assertEqual({job.id for job in final.terminated_tasks}, {50})
        self.assertEqual(len(final.terminated_tasks), 10)
        self.assertEqual([event.tick for event in final.result.events if event.kind == 'arrival'], list(range(2, 42, 4)))

    def test_running_rename_preserves_past_data_and_does_not_dispatch_again(self):
        for algorithm in ('RM', 'EDF'):
            with self.subTest(algorithm=algorithm):
                state = scale(start_simulation(algorithm, 1, [task(1, duration=5, period=20),
                                                               task(2, duration=5, period=30)]))
                original = pickle.dumps(state)
                history = pickle.dumps((state.result.timeline, state.result.events, state.result.task_colors,
                                        state.result.suspended_timeline, state.random_state))
                edited = state.edit(task_id=1, changes={'id': 50})
                self.assertEqual(pickle.dumps(state), original)
                self.assertEqual(pickle.dumps((edited.result.timeline, edited.result.events, edited.result.task_colors,
                                              edited.result.suspended_timeline, edited.random_state)), history)
                self.assertFalse(edited.reschedule_needed)
                self.assertIs(edited.processors_list[0].task_running, edited.current_task(50)[0])
                with patch('simulator._schedule', wraps=simulator._schedule) as schedule:
                    advanced = scale(edited)
                schedule.assert_not_called()
                self.assertEqual(advanced.result.timeline[:1], [[(1, 1)]])
                self.assertEqual(advanced.result.timeline[1:], [[(50, 1)]])
                self.assertEqual(dict(make_task_status(advanced.result, 50))['Ticks executados'], '2')

    def test_completed_instances_and_future_calendar_keep_the_same_family(self):
        state = start_simulation('RM', 1, [task()])
        for _ in range(6):
            state = scale(state)
        edited = state.edit(task_id=1, changes={'id': 50})
        self.assertEqual({job.id for _, queue in edited.task_queues() for job in queue}, {50})
        final = self.finish(edited)
        self.assertEqual(dict(make_task_status(final.result, 50))['Instâncias concluídas'], '10')
        self.assertEqual([event.tick for event in final.result.events if event.kind == 'arrival'], list(range(0, 40, 4)))
        self.assertEqual(final.result.events[0].task_id, 1)
        self.assertEqual(final.result.events[-1].task_id, 50)

    def test_finished_task_can_be_renamed_without_reopening_it(self):
        state = self.finish(start_simulation('RM', 1, [task()]))
        edited = state.edit(task_id=1, changes={'id': 50})
        self.assertTrue(edited.is_finished)
        self.assertEqual(edited.current_task(50)[1], 'Finalizada')
        self.assertEqual(dict(make_task_status(edited.result, 50))['Instâncias concluídas'], '10')
        self.assertEqual(edited.result.timeline, state.result.timeline)
        self.assertIs(scale(edited), edited)
        self.assertTrue(build_gantt(edited.result)[0])

    def test_invalid_or_duplicate_id_does_not_partially_change_anything(self):
        state = scale(start_simulation('RM', 1, [task(1, duration=3), task(2, duration=3)]))
        original = pickle.dumps(state)
        for value in (0, -1, '1.5', '', 'abc', 2):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    state.edit(algorithm='edf', num_cpus=3, task_id=1, changes={'id': value, 'color': '445566'})
                self.assertEqual(pickle.dumps(state), original)

    def test_old_ids_are_reserved_and_a_task_can_return_to_its_own_id(self):
        state = start_simulation('RM', 1, [task(1), task(2)])
        state = state.edit(task_id=1, changes={'id': 50})
        state = state.edit(task_id=50, changes={'id': 6})
        with self.assertRaisesRegex(ValueError, 'histórico'):
            state.edit(task_id=2, changes={'id': 50})
        with self.assertRaisesRegex(ValueError, 'histórico'):
            state.edit(add_task=dict(id=1, color='445566'))
        state = state.edit(task_id=6, changes={'id': 1})
        self.assertEqual(state.result.task_key(1), 1)
        self.assertTrue(all(state.result.resolve_task_id(alias) == 1 for alias in (1, 6, 50)))
        self.assertEqual([info.id for info in state.result.tasks], [1, 2])

    def test_rename_keeps_ownership_of_historical_colors(self):
        state = scale(start_simulation('RM', 1, [task(1, duration=3), task(2, duration=3)]))
        state = state.edit(task_id=1, changes={'id': 50, 'color': '445566'})
        state = state.edit(task_id=50, changes={'color': 'FF0000'})
        with self.assertRaisesRegex(ValueError, 'cor'):
            state.edit(task_id=2, changes={'color': 'FF0000'})
        self.assertEqual(state.result.task_colors[0][1], 'FF0000')

    def test_reorders_y_axis_and_preserves_past_bars_events_and_cpu_labels(self):
        state = start_simulation('RM', 2, [task(1, duration=3, period=8), task(10, duration=3, period=9)])
        for _ in range(2):
            state = scale(state)
        old_shapes, _, _ = build_gantt(state.result)
        edited = state.edit(task_id=1, changes={'id': 20})
        shapes, width, height = build_gantt(edited.result)
        labels = sorted((shape.y1, shape.text) for shape in shapes if shape.kind == 'text'
                        and shape.text in ('T10', 'T20'))
        self.assertEqual([text for _, text in labels], ['T20', 'T10'])
        old_bars = [(s.x1, s.x2, s.fill) for s in old_shapes if s.kind == 'rect' and s.task_id == 1 and not s.is_background]
        new_bars = [(s.x1, s.x2, s.fill) for s in shapes if s.kind == 'rect' and s.task_id == 20 and not s.is_background]
        self.assertEqual(new_bars, old_bars)
        self.assertFalse(any(shape.task_id == 1 for shape in shapes))
        self.assertTrue(any(s.kind == 'text' and s.text == 'T1(1)' and s.task_id == 20 for s in shapes))
        self.assertTrue(any(s.kind == 'text' and 'ID 1 → 20' in s.text for s in shapes))
        self.assertEqual(edited.result.timeline, state.result.timeline)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'renomeada.svg'
            save_svg(shapes, width, height, path)
            self.assertTrue(ET.parse(path).getroot().tag.endswith('svg'))

    def test_overlapping_instances_and_suspension_stay_visible_after_rename(self):
        state = start_simulation('RM', 2, [task(duration=5, period=2)])
        for _ in range(3):
            state = scale(state)
        state = state.edit(task_id=1, task_state='Suspensa')
        state = scale(state)
        edited = state.edit(task_id=1, changes={'id': 50})
        self.assertEqual(edited.result.suspended_timeline, state.result.suspended_timeline)
        self.assertEqual(edited.result.current_suspended, [(50, 1), (50, 2)])
        shapes, _, _ = build_gantt(edited.result)
        self.assertTrue(any(s.pattern == 'dots' and s.task_id == 50 for s in shapes))
        self.assertTrue(any(s.text == 'P1/I1' and s.task_id == 50 for s in shapes))
        edited = edited.edit(task_id=50, task_state='Pronta')
        self.assertEqual(sum(event.kind == 'arrival' and event.instance == 1 for event in edited.result.events), 1)

    def test_manual_admission_can_be_undone_after_renaming_without_duplicate_events(self):
        state = start_simulation('RM', 1, [task()])
        state = state.edit(task_id=1, task_state='Pronta')
        state = state.edit(task_id=1, changes={'id': 50}, task_state='Nova')
        self.assertFalse(any(event.kind == 'arrival' and event.instance == 1 for event in state.result.events))
        state = scale(state)
        self.assertEqual([(e.task_id, e.instance) for e in state.result.events if e.kind == 'arrival'], [(50, 1)])
        self.assertEqual([(job.id, job.instance_number) for job in state.tasks_to_arrival], [(50, 2)])

if __name__ == '__main__':
    unittest.main()
