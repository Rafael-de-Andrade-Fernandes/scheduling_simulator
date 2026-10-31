# Monta os textos mostrados ao usuário: estado do sistema no tick atual, períodos em que
# cada processador ficou desligado e perdas de prazo. Só lê o resultado da simulação.

def make_report(result):
    lines = []
    if result.finished:
        lines.append(f"Algoritmo: {result.algorithm} | Processadores: {result.num_cpus} | "
                     f"Simulação terminada no tick {result.tick}")
    else:
        lines.append(f"Algoritmo: {result.algorithm} | Processadores: {result.num_cpus} | "
                     f"Tick atual: {result.tick}")
    lines.append("")

    for warning in result.warnings:
        lines.append(warning)
    if len(result.warnings) > 0:
        lines.append("")

    # Estado do sistema agora (o "debugger")
    lines.append("Estado do sistema:")
    lines.append("  Fila de prontos: " + format_instances(result.ready))
    if result.tick > 0:
        last_tick = result.timeline[result.tick - 1]
        for cpu in range(result.num_cpus):
            if last_tick[cpu] is None:
                lines.append(f"  CPU {cpu + 1} (último tick): desligada")
            else:
                lines.append(f"  CPU {cpu + 1} (último tick): tarefa {last_tick[cpu][0]} (instância {last_tick[cpu][1]})")
    waiting = ""
    for item in result.waiting:
        waiting += f"T{item[0]}({item[1]}) no tick {item[2]}  "
    lines.append("  Aguardando chegada: " + (waiting.strip() if waiting else "nenhuma"))
    lines.append("  Terminadas: " + format_instances(result.terminated))
    lines.append("")

    lines.append("Processadores desligados (OFF):")
    for cpu in range(result.num_cpus):
        periods = find_off_periods(result, cpu)
        if len(periods) == 0:
            lines.append(f"  CPU {cpu + 1}: nunca ficou desligado")
        else:
            text = ""
            total = 0
            for period in periods:
                text += f"[{period[0]}, {period[1]}) "
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


# "T1(2) T3(1)" ou "nenhuma"
def format_instances(instances):
    if len(instances) == 0:
        return "nenhuma"
    text = ""
    for item in instances:
        text += f"T{item[0]}({item[1]}) "
    return text.strip()


# Devolve a lista de pares (inicio, fim) dos períodos em que a CPU ficou sem tarefa.
# O intervalo é aberto no fim: [2, 5) quer dizer ticks 2, 3 e 4.
def find_off_periods(result, cpu):
    periods = []
    tick = 0
    while tick < result.total_ticks:
        if result.timeline[tick][cpu] is None:
            start = tick
            while tick < result.total_ticks and result.timeline[tick][cpu] is None:
                tick = tick + 1
            periods.append((start, tick))
        else:
            tick = tick + 1
    return periods


# Situação de uma tarefa no tick atual, como lista de pares (nome, valor)
# para mostrar no menu lateral.
def make_task_status(task):
    cpus = ", ".join(str(c) for c in task.cpus_used) if task.cpus_used else "nenhum"

    status = []
    status.append(("Situação", task.situation))
    status.append(("Instância atual", str(task.instance)))
    status.append(("Prazo absoluto", str(task.absolute_deadline)))
    if task.is_late:
        status.append(("Atrasada", "sim"))
    status.append(("Instâncias que chegaram", str(task.arrivals)))
    status.append(("Instâncias concluídas", str(task.finishes)))
    status.append(("Perdas de prazo", str(task.misses)))
    status.append(("Ticks executados", str(task.ticks_executed)))
    status.append(("Processadores usados", cpus))
    return status
