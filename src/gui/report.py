"""Relatórios de execução derivados exclusivamente dos resultados históricos."""
# Monta o texto de resumo mostrado ao usuário: períodos em que cada processador
# ficou desligado e lista de perdas de prazo. Só lê o resultado da simulação.

def make_report(result):
    """Resume configuração, períodos OFF e perdas de prazo sem alterar o resultado."""
    lines = []
    lines.append(f"Algoritmo: {result.algorithm} | Processadores: {result.num_cpus} | Duração: {result.total_ticks} ticks")
    lines.append("")

    lines.append("Processadores desligados (OFF):")
    for cpu in range(result.max_cpus):
        periods = find_off_periods(result, cpu)
        if len(periods) == 0:
            lines.append(f"  CPU {cpu + 1}: sem intervalos OFF registrados")
        else:
            text = ""
            for period in periods:
                text += f"[{period[0]}, {period[1]}) "
            total = 0
            for period in periods:
                total += period[1] - period[0]
            lines.append(f"  CPU {cpu + 1}: {text.strip()}  (total: {total} ticks)")
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


# Devolve a lista de pares (inicio, fim) dos períodos em que a CPU ficou sem tarefa.
# O intervalo é aberto no fim: [2, 5) quer dizer ticks 2, 3 e 4.
def find_off_periods(result, cpu):
    """Calcula intervalos semiabertos apenas enquanto a CPU realmente existia."""
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


# Situação de uma tarefa ao final da simulação, calculada a partir do resultado.
# Devolve uma lista de pares (nome, valor) para mostrar no menu lateral.
def make_task_status(result, task_id):
    """Acumula chegadas, conclusões e execução de todas as instâncias de uma tarefa."""
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
    cpus_used = []
    for tick in range(result.total_ticks):
        for cpu, running in enumerate(result.timeline[tick]):
            if running is not None and running[0] == task_id:
                executed_ticks += 1
                if (cpu + 1) not in cpus_used:
                    cpus_used.append(cpu + 1)
    cpus_used.sort()

    status = []
    status.append(("Instâncias que chegaram", str(arrivals)))
    status.append(("Instâncias concluídas", str(finishes)))
    status.append(("Perdas de prazo", str(misses)))
    status.append(("Ticks executados", str(executed_ticks)))
    status.append(("Processadores usados", ", ".join(str(c) for c in cpus_used) if cpus_used else "nenhum"))
    return status
