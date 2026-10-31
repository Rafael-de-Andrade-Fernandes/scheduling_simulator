"""Escalonamento por eventos: chamadas, mutações, prioridades e histórico."""
import contextlib
from copy import deepcopy
import io
from pathlib import Path
import pickle
import random
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'src/core'))

import simulator
# O oráculo usa o limite literal do PDF, sem importar a constante de produção.
EXPECTED_INSTANCES = 10
from simulator import scale, start_simulation, state_list
import test_debug_mode as debug_tests


task = debug_tests.task


def job_ids(tasks):
    return [(item.id, item.instance_number) for item in tasks]


class EventSchedulingTests(unittest.TestCase):
    def setUp(self):
        state_list.clear()
        self.addCleanup(state_list.clear)
        old_random = random.getstate()
        self.addCleanup(random.setstate, old_random)
        random.seed(42)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def step(self, state):
        before = pickle.dumps(state)
        trace = SimpleNamespace(ticks=[])
        real_schedule = simulator._schedule

        def clone(original):
            copied = deepcopy(original)
            trace.queues = {name: queue for name, queue in copied.task_queues()}
            trace.contents = {name: tuple(queue) for name, queue in copied.task_queues()}
            trace.cpus = copied.processors_list
            return copied

        def dispatch(copied):
            trace.ticks.append(copied.tick)
            real_schedule(copied)

        with patch('simulator.deepcopy', side_effect=clone), \
             patch('simulator._schedule', side_effect=dispatch), \
             patch('simulator.choose_task', wraps=simulator.choose_task) as choose, \
             patch('simulator.pair_cpus_tasks', wraps=simulator.pair_cpus_tasks) as pair:
            next_state = scale(state)
        trace.choices = choose.call_count
        trace.pairings = pair.call_count
        self.assertEqual(pickle.dumps(state), before, 'O passo alterou um estado anterior')
        if not state.is_finished:
            for name, queue in next_state.task_queues():
                self.assertIs(queue, trace.queues[name], f'A lista {name} foi reconstruída')
            self.assertIs(next_state.processors_list, trace.cpus)
        return next_state, trace

    def assert_quiet(self, state):
        next_state, trace = self.step(state)
        self.assertEqual(trace.ticks, [])
        self.assertEqual((trace.choices, trace.pairings), (0, 0))
        self.assertEqual(tuple(next_state.ready_queue), trace.contents['Pronta'])
        self.assertEqual(tuple(next_state.running_tasks), trace.contents['Executando'])
        self.assertEqual(next_state.random_state, state.random_state)
        return next_state

    def test_idle_ticks_and_future_creation_do_not_dispatch(self):
        for algorithm in ('RM', 'EDF'):
            with self.subTest(algorithm=algorithm):
                state = start_simulation(algorithm, 2, [task(arrival=5, duration=2, period=20)])
                for _ in range(5):
                    state = self.assert_quiet(state)
                state, trace = self.step(state)
                self.assertEqual(trace.ticks, [5])
                self.assertEqual(trace.choices, 1)  # Não chama choose_task para a CPU sem candidata.
                state, trace = self.step(state)  # Conclusão em 7; próxima chegada somente em 25.
                self.assertEqual(trace.ticks, [])
                self.assertEqual(state.tick, 7)
                self.assertEqual(job_ids(state.tasks_to_arrival), [(1, 2)])
                state = self.assert_quiet(state)

    def test_ticks_with_running_and_waiting_jobs_preserve_both_queues(self):
        for algorithm in ('RM', 'EDF'):
            with self.subTest(algorithm=algorithm):
                state = scale(start_simulation(algorithm, 1, [task(1, duration=5, period=10),
                                                              task(2, duration=4, period=20)]))
                for _ in range(3):
                    state = self.assert_quiet(state)
                    self.assertEqual(job_ids(state.running_tasks), [(1, 1)])
                    self.assertEqual(job_ids(state.ready_queue), [(2, 1)])
                    self.assertIs(state.processors_list[0].task_running, state.running_tasks[0])

    def test_higher_priority_arrival_preempts_immediately(self):
        for algorithm in ('RM', 'EDF'):
            with self.subTest(algorithm=algorithm):
                state = scale(start_simulation(algorithm, 1, [task(1, duration=5, period=20),
                                                              task(2, arrival=2, duration=2, period=5)]))
                state = self.assert_quiet(state)
                state, trace = self.step(state)
                self.assertEqual(trace.ticks, [2])
                self.assertEqual(trace.pairings, 1)
                self.assertEqual(state.result.timeline[-1], [(2, 1)])
                self.assertEqual(job_ids(state.ready_queue), [(1, 1)])
                self.assertEqual(state.ready_queue[0].computational_time, 2)
                self.assertIsNone(state.ready_queue[0].processor)

    def test_lower_priority_arrival_does_not_reorder_or_reassign(self):
        state = scale(start_simulation('RM', 1, [task(1, duration=5, period=10),
                                                task(3, duration=4, period=30),
                                                task(2, arrival=2, duration=4, period=20)]))
        state = self.assert_quiet(state)
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [2])
        self.assertEqual(trace.pairings, 0)
        self.assertEqual(tuple(state.running_tasks), trace.contents['Executando'])
        self.assertEqual(job_ids(state.ready_queue), [(3, 1), (2, 1)])
        self.assertIs(state.running_tasks[0].processor, trace.cpus[0])

    def test_cpu_release_dispatches_waiter_without_an_idle_interval(self):
        state = scale(start_simulation('RM', 1, [task(1, duration=2, period=10),
                                                task(2, duration=4, period=20)]))
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [])
        self.assertTrue(state.reschedule_needed)
        self.assertEqual(state.result.events[-1].tick, 2)
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [2])
        self.assertEqual(state.result.timeline, [[(1, 1)], [(1, 1)], [(2, 1)]])
        self.assertFalse(state.reschedule_needed)
        self.assert_quiet(state)

    def test_simultaneous_arrivals_and_completions_dispatch_once(self):
        state = scale(start_simulation('RM', 2, [task(1, duration=2, period=10),
                                                task(2, duration=2, period=11),
                                                task(3, duration=5, period=30),
                                                task(4, arrival=2, duration=2, period=5)]))
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [])
        self.assertEqual(len(state.terminated_tasks), 2)
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [2])
        self.assertEqual(trace.choices, 2)
        self.assertEqual(trace.pairings, 1)
        self.assertEqual(set(state.result.timeline[-1]), {(3, 1), (4, 1)})

    def test_multicore_preemption_preserves_unaffected_cpu_affinity(self):
        state = scale(start_simulation('RM', 2, [task(1, duration=6, period=10),
                                                task(2, duration=6, period=20),
                                                task(3, arrival=2, duration=2, period=5)]))
        state = self.assert_quiet(state)
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [2])
        self.assertEqual(state.result.timeline[-1], [(1, 1), (3, 1)])
        self.assertEqual(job_ids(state.ready_queue), [(2, 1)])
        self.assertEqual(state.processors_list[0].task_running.computational_time, 3)

    def test_unchanged_multicore_selection_keeps_incumbent_list_order(self):
        state = scale(start_simulation('RM', 2, [task(1, duration=5, period=20),
                                                task(2, duration=5, period=10),
                                                task(3, arrival=2, duration=3, period=30)]))
        self.assertEqual(job_ids(state.running_tasks), [(2, 1), (1, 1)])
        state = self.assert_quiet(state.edit(task_id=1, changes={'period': 5, 'deadline': 5}))
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [2])
        self.assertEqual(trace.pairings, 0)
        self.assertEqual(tuple(state.running_tasks), trace.contents['Executando'])
        self.assertEqual(job_ids(state.running_tasks), [(2, 1), (1, 1)])
        self.assertEqual(state.result.timeline[-1], [(2, 1), (1, 1)])

    def test_deadline_miss_does_not_remove_or_reschedule_last_instance(self):
        for algorithm in ('RM', 'EDF'):
            with self.subTest(algorithm=algorithm):
                state = start_simulation(algorithm, 1, [task(duration=24, period=2)])
                for _ in range(20):
                    state = scale(state)
                state, trace = self.step(state)  # Prazo da instância 3, sem sucessora a admitir.
                self.assertEqual(trace.ticks, [])
                self.assertEqual(trace.choices, 0)
                self.assertEqual(job_ids(state.running_tasks), [(1, 1)])
                self.assertEqual(job_ids(state.ready_queue), [(1, number) for number in range(2, 11)])
                self.assertIn(('deadline_miss', 20, 10),
                              [(event.kind, event.tick, event.instance) for event in state.result.events])

    def test_successor_arrival_after_missed_deadline_is_a_dispatch_event(self):
        state = scale(scale(start_simulation('RM', 1, [task(duration=6, period=2)])))
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [2])
        self.assertEqual(trace.pairings, 0)  # A instância atrasada continua executando.
        self.assertEqual(job_ids(state.ready_queue), [(1, 2)])

    def test_quantum_is_not_a_dispatch_event(self):
        for algorithm in ('RM', 'EDF'):
            state = start_simulation(algorithm, 1, [task(duration=6, period=20)])
            state.quantum = 1
            state = scale(state)
            for _ in range(4):
                state = self.assert_quiet(state)

    def test_cosmetic_noop_and_future_edits_do_not_dispatch(self):
        state = scale(start_simulation('RM', 1, [task(1, duration=6, period=10),
                                                task(2, duration=5, period=20),
                                                task(3, arrival=12, duration=2, period=30)]))
        for changes in (dict(algorithm='rm', num_cpus='1'),
                        dict(task_id=1, changes={'color': '001122', 'events': "['x']"}),
                        dict(task_id=3, changes={'arrival': 15, 'period': 31, 'deadline': 31})):
            with self.subTest(changes=changes):
                edited = state.edit(**changes)
                self.assertFalse(edited.reschedule_needed)
                self.assert_quiet(edited)

    def test_algorithm_edit_dispatches_once_when_a_waiter_exists(self):
        state = start_simulation('RM', 1, [task(1, duration=3, period=4),
                                          task(2, duration=3, period=6)])
        for _ in range(5):
            state = scale(state)
        edited = state.edit(algorithm='edf')
        self.assertTrue(edited.reschedule_needed)
        state, trace = self.step(edited)
        self.assertEqual(trace.ticks, [5])
        self.assertEqual(state.result.timeline[-1], [(2, 1)])
        self.assertFalse(state.reschedule_needed)

    def test_priority_edit_can_preempt_but_does_not_repeat_next_tick(self):
        state = scale(start_simulation('RM', 1, [task(1, duration=6, period=10),
                                                task(2, duration=6, period=20)]))
        state = state.edit(task_id=2, changes={'period': 5, 'deadline': 5})
        self.assertTrue(state.reschedule_needed)
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [1])
        self.assertEqual(state.result.timeline[-1], [(2, 1)])
        self.assert_quiet(state)

    def test_suspension_and_resumption_dispatch_only_as_needed(self):
        state = scale(start_simulation('RM', 1, [task(1, duration=6, period=10),
                                                task(2, duration=6, period=20)]))
        waiting_suspended = state.edit(task_id=2, task_state='Suspensa')
        self.assertFalse(waiting_suspended.reschedule_needed)
        self.assert_quiet(waiting_suspended)
        running_suspended = state.edit(task_id=1, task_state='Suspensa')
        state, trace = self.step(running_suspended)
        self.assertEqual(trace.ticks, [1])
        self.assertEqual(state.result.timeline[-1], [(2, 1)])
        state = state.edit(task_id=1, task_state='Pronta')
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [2])
        self.assertEqual(state.result.timeline[-1], [(1, 1)])

    def test_manual_finish_releases_cpu_for_waiter(self):
        state = scale(start_simulation('RM', 1, [task(1, duration=6, period=10),
                                                task(2, duration=6, period=20)]))
        state = state.edit(task_id=1, task_state='Finalizada')
        state, trace = self.step(state)
        self.assertEqual(trace.ticks, [1])
        self.assertEqual(state.result.timeline[-1], [(2, 1)])

    def test_increasing_cpus_dispatches_waiters_and_decreasing_idle_cpus_does_not(self):
        state = scale(start_simulation('RM', 1, [task(1, duration=6, period=10),
                                                task(2, duration=6, period=20)]))
        state, trace = self.step(state.edit(num_cpus=3))
        self.assertEqual(trace.ticks, [1])
        self.assertEqual(state.result.timeline[-1], [(1, 1), (2, 1), None])
        state = self.assert_quiet(state.edit(num_cpus=2))
        self.assertEqual(state.result.timeline[-1], [(1, 1), (2, 1)])

    def test_reducing_busy_cpus_requeues_jobs_then_dispatches_once(self):
        state = scale(start_simulation('RM', 2, [task(1, duration=6, period=10),
                                                task(2, duration=6, period=20)]))
        state, trace = self.step(state.edit(num_cpus=1))
        self.assertEqual(trace.ticks, [1])
        self.assertEqual(trace.pairings, 0)  # O incumbente continua na CPU 1.
        self.assertEqual(job_ids(state.ready_queue), [(2, 1)])
        self.assert_quiet(state)

    def test_removing_cpu_of_higher_priority_job_preempts_retained_cpu(self):
        state = scale(start_simulation('RM', 2, [task(1, duration=6, period=20),
                                                task(2, arrival=1, duration=6, period=10)]))
        state = scale(state)
        self.assertEqual(state.result.timeline[-1], [(1, 1), (2, 1)])
        state, trace = self.step(state.edit(num_cpus=1))
        self.assertEqual(trace.ticks, [2])
        self.assertEqual(trace.pairings, 1)
        self.assertEqual(state.result.timeline[-1], [(2, 1)])
        self.assertEqual(job_ids(state.ready_queue), [(1, 1)])

    def test_edits_without_waiters_do_not_invoke_selection(self):
        state = scale(start_simulation('RM', 2, [task(duration=6, period=20)]))
        for changes in (dict(algorithm='edf'), dict(num_cpus=3),
                        dict(task_id=1, changes={'duration': 7}),
                        dict(task_id=1, task_state='Suspensa')):
            with self.subTest(changes=changes):
                self.assert_quiet(state.edit(**changes))

    def test_pending_completion_is_not_lost_by_a_cosmetic_edit(self):
        state = scale(scale(start_simulation('RM', 1, [task(1, duration=2, period=10),
                                                      task(2, duration=5, period=20)])))
        edited = state.edit(task_id=2, changes={'color': '001122'})
        self.assertTrue(edited.reschedule_needed)
        state, trace = self.step(edited)
        self.assertEqual(trace.ticks, [2])

    def test_unchanged_ties_do_not_draw_again_or_duplicate_gantt_events(self):
        state = scale(start_simulation('RM', 1, [task(1, duration=5, period=20),
                                                task(2, duration=5, period=20),
                                                task(3, duration=5, period=20)]))
        draws_before = [(event.tick, event.task_id) for event in state.result.events if event.kind == 'draw']
        self.assertTrue(draws_before)
        for _ in range(3):
            state = self.assert_quiet(state)
        self.assertEqual([(event.tick, event.task_id) for event in state.result.events if event.kind == 'draw'],
                         draws_before)

    def test_back_and_replay_restore_pending_dispatch_and_random_state(self):
        state = scale(scale(start_simulation('RM', 1, [task(1, duration=2, period=10),
                                                      task(2, duration=5, period=20),
                                                      task(3, duration=5, period=20)])))
        original, first = self.step(state)
        replay, second = self.step(state)
        self.assertEqual(first.ticks, [2])
        self.assertEqual(first.ticks, second.ticks)
        self.assertEqual(pickle.dumps(original), pickle.dumps(replay))

    def test_final_state_never_dispatches(self):
        state = start_simulation('EDF', 1, [task()])
        while not state.is_finished:
            state = scale(state)
        result, trace = self.step(state)
        self.assertIs(result, state)
        self.assertEqual(trace.ticks, [])
        self.assertEqual(trace.choices, 0)

    def test_reference_model_matches_both_algorithms_and_all_cpu_counts(self):
        # Modelo independente: resolve prioridades a cada tick como um oráculo,
        # com períodos distintos para evitar qualquer desempate por sorteio.
        rng = random.Random(2026)
        for case in range(24):
            specs = [(index + 1, rng.randint(0, 5), rng.randint(1, 8), period)
                     for index, period in enumerate(rng.sample([3, 5, 7, 11, 13], rng.randint(1, 5)))]
            for algorithm in ('RM', 'EDF'):
                for cpus in (1, 2, 3):
                    with self.subTest(case=case, algorithm=algorithm, cpus=cpus, specs=specs):
                        expected_rows, expected_events = reference_run(specs, algorithm, cpus)
                        state = start_simulation(algorithm, cpus,
                                                 [task(index, arrival, duration, period)
                                                  for index, arrival, duration, period in specs])
                        calls = []
                        real_schedule = simulator._schedule

                        def dispatch(copied):
                            calls.append(copied.tick)
                            real_schedule(copied)

                        with patch('simulator._schedule', side_effect=dispatch):
                            while not state.is_finished:
                                self.assertLess(state.tick, 1000)
                                state = scale(state)
                        self.assertEqual(state.result.timeline, expected_rows)
                        self.assertEqual(sorted((event.kind, event.tick, event.task_id, event.instance)
                                                for event in state.result.events), sorted(expected_events))
                        trigger_ticks = {tick for kind, tick, _, _ in expected_events
                                         if kind in ('arrival', 'finish')}
                        self.assertTrue(set(calls) <= trigger_ticks)
                        self.assertEqual(len(calls), len(set(calls)), 'Mais de um despacho no mesmo instante')


def reference_run(specs, algorithm, cpus):
    """Oráculo simples, separado dos TCBs, filas, comparadores e helpers do core."""
    jobs = []
    created = set()
    rows, events = [], []
    processors = [None] * cpus

    def create(spec, instance, arrival):
        index, _, duration, period = spec[:4]
        relative_deadline = spec[4] if len(spec) > 4 else period
        if instance > EXPECTED_INSTANCES or (index, instance) in created:
            return
        created.add((index, instance))
        jobs.append(dict(spec=spec, id=index, instance=instance, arrival=arrival,
                         duration=duration, period=period, relative_deadline=relative_deadline, deadline=arrival + relative_deadline,
                         executed=0, late=False, status='new'))

    for spec in specs:
        for instance in range(1, EXPECTED_INSTANCES + 1):
            create(spec, instance, spec[1] + (instance - 1) * spec[3])
    tick = 0
    while any(job['status'] != 'finished' for job in jobs):
        if tick > 1000:
            raise AssertionError('O modelo de referência não terminou')
        for job in list(jobs):
            if job['status'] == 'active' and not job['late'] and job['deadline'] <= tick:
                job['late'] = True
                events.append(('deadline_miss', tick, job['id'], job['instance']))
        for job in jobs:
            if job['status'] == 'new' and job['arrival'] <= tick:
                job['status'] = 'active'
                events.append(('arrival', tick, job['id'], job['instance']))
        running = {id(job) for job in processors if job is not None}

        def priority(job):
            return (job['period'] if algorithm == 'RM' else job['deadline'],
                    -int(id(job) in running), job['relative_deadline'], job['arrival'], job['duration'])

        chosen = sorted((job for job in jobs if job['status'] == 'active'), key=priority)[:cpus]
        chosen_ids = {id(job) for job in chosen}
        processors = [job if job is not None and id(job) in chosen_ids else None for job in processors]
        assigned = {id(job) for job in processors if job is not None}
        for job in chosen:
            if id(job) not in assigned:
                processors[processors.index(None)] = job
                assigned.add(id(job))
        row = []
        for cpu, job in enumerate(processors):
            row.append(None if job is None else (job['id'], job['instance']))
            if job is not None:
                job['executed'] += 1
                if job['executed'] >= job['duration']:
                    job['status'] = 'finished'
                    events.append(('finish', tick + 1, job['id'], job['instance']))
                    processors[cpu] = None
        rows.append(row)
        tick += 1
    return rows, events


if __name__ == '__main__':
    unittest.main()
