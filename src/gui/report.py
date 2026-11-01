"""Relatórios de execução derivados exclusivamente dos resultados históricos."""
def make_report(result):
    lines = []
    lines.append(f"Algoritmo: {result.algorithm} | Processadores: {result.num_cpus} | Duração: {result.total_ticks} ticks")
    lines.append("")

    lines.append("Processadores desligados (OFF):")
    for cpu in range(result.max_cpus):
        periods = find_off_periods(result, cpu)
        if not periods:
            lines.append(f"  CPU {cpu + 1}: sem intervalos OFF registrados")
        else:
            text = " ".join(f"[{start}, {end})" for start, end in periods)
            total = sum(end - start for start, end in periods)
            lines.append(f"  CPU {cpu + 1}: {text}  (total: {total} ticks)")
    lines.append("")

    lines.append("Perdas de prazo:")
    misses = 0
    for event in result.events:
        if event.kind == "deadline_miss":
            lines.append(f"  Tarefa {event.task_id} (instância {event.instance}) no tick {event.tick}")
            misses += 1
    if misses == 0:
        lines.append("  nenhuma")

    return "\n".join(lines)


def find_off_periods(result, cpu):
    """Retorna intervalos [início, fim), excluindo ticks em que a CPU não existia."""
    periods = []
    tick = 0
    while tick < result.total_ticks:
        if cpu < len(result.timeline[tick]) and result.timeline[tick][cpu] is None:
            start = tick
            while (tick < result.total_ticks and cpu < len(result.timeline[tick])
                   and result.timeline[tick][cpu] is None):
                tick = tick + 1
            periods.append((start, tick))
        else:
            tick = tick + 1
    return periods


def make_task_status(result, task_id):
    arrivals = 0
    finishes = 0
    misses = 0
    for event in result.events:
        if event.task_id != task_id:
            continue
        if event.kind == "arrival":
            arrivals += 1
        elif event.kind == "finish":
            finishes += 1
        elif event.kind == "deadline_miss":
            misses += 1

    executed_ticks = 0
    cpus_used = set()
    for row in result.timeline:
        for cpu, running in enumerate(row):
            if running is not None and running[0] == task_id:
                executed_ticks += 1
                cpus_used.add(cpu + 1)

    return [
        ("Instâncias que chegaram", str(arrivals)),
        ("Instâncias concluídas", str(finishes)),
        ("Perdas de prazo", str(misses)),
        ("Ticks executados", str(executed_ticks)),
        ("Processadores usados", ", ".join(str(cpu) for cpu in sorted(cpus_used)) if cpus_used else "nenhum"),
    ]
