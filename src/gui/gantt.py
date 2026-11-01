"""Primitivas do Gantt completo; o desenho consulta o resultado sem modificá-lo."""
import textwrap

# Layout (pixels)
CELL_W = 34
ROW_H = 54
CPU_ROW_H = 30
LEFT = 100
TOP = 50
RIGHT = 30
MIN_WIDTH = 820     # Inclui a legenda completa mesmo em simulações curtas
TIME_LABEL_SPACE = 90
# Estimativa de largura de um caractere na fonte de 11 px usada no rodapé.
SYSTEM_TEXT_CHAR_WIDTH = 6.2

# Offsets verticais da barra de execução (relativos a ROW_H)
BAR_TOP = 18        # Topo da barra (0..BAR_TOP: término / deadline miss)
BAR_BOTTOM = 38     # Base da barra (BAR_BOTTOM..ROW_H: chegada / sorteio)

# Cores
COLOR_ARRIVAL = "#1565c0"
COLOR_FINISH = "#2e7d32"
COLOR_MISS = "#d32f2f"
COLOR_DRAW = "#f9a825"
COLOR_OFF = "#d0d0d0"
COLOR_GRID = "#e3e3e3"
COLOR_AXIS = "#000000"
COLOR_TEXT = "#000000"
COLOR_SUSPENDED = "#000000"
COLOR_SYSTEM = "#7b1fa2"
CPU_ABSENT = "absent"
LANE_H = ROW_H


class TaskRow:
    """Linha da família; lanes associa cada ocorrência à sua faixa vertical.

    A sobreposição considera toda a vida da instância, incluindo espera e
    suspensão, para que seus eventos e barras não ocultem os de outra.
    """
    def __init__(self, top, height, lanes):
        self.top = top
        self.height = height
        self.lanes = lanes

    def instance_y(self, instance):
        return self.top + self.lanes.get(instance, 0) * LANE_H


def find_instance_spans(result):
    """Mapeia (id, instância) para [primeiro tick, último tick], com limites inclusivos."""
    spans = {}
    for event in result.events:
        if event.instance <= 0:
            continue
        key = (event.task_id, event.instance)
        if event.kind == 'arrival':
            # Sem término, a faixa continua reservada até o instante mostrado.
            spans.setdefault(key, [event.tick, result.total_ticks])
        elif event.kind == 'finish':
            # Um término em t permite reutilizar a faixa desde t, não apenas t+1.
            span = spans.setdefault(key, [event.tick, event.tick])
            span[1] = max(event.tick - 1, span[0])
    return spans


def assign_lanes(spans, task_id):
    """Reutiliza a primeira faixa desocupada; retorna o mapa de ocorrências e a contagem."""
    jobs = []
    for (index, instance), (start, end) in spans.items():
        if index == task_id:
            jobs.append((start, end, instance))
    jobs.sort()

    lanes = {}
    lane_ends = []      # lane_ends[i] = último tick ocupado na faixa i
    for start, end, instance in jobs:
        lane = len(lane_ends)
        for index, previous_end in enumerate(lane_ends):
            if previous_end < start:
                lane = index
                break
        if lane == len(lane_ends):
            lane_ends.append(end)
        else:
            lane_ends[lane] = end
        lanes[instance] = lane
    return lanes, len(lane_ends)


def build_rows(result):
    spans = find_instance_spans(result)
    rows = {}
    offset = TOP
    # O menor ID precisa ficar junto do eixo X, na parte inferior do gráfico.
    for task_id in sorted((info.id for info in result.tasks), reverse=True):
        lanes, lane_count = assign_lanes(spans, task_id)
        height = ROW_H + max(0, lane_count - 1) * LANE_H
        rows[task_id] = TaskRow(offset, height, lanes)
        offset += height
    return rows


class Shape:
    """Geometria e estilo compartilhados pelo Canvas e pelo SVG.

    kind determina os campos usados: coordenadas, points ou text. task_id e
    is_background são metadados de seleção da GUI; não mudam a geometria exportada.
    As âncoras de texto seguem os nomes do SVG: start, middle e end.
    """
    def __init__(self, kind):
        self.kind = kind
        self.x1 = 0
        self.y1 = 0
        self.x2 = 0
        self.y2 = 0
        self.points = []
        self.fill = ""
        self.outline = ""
        self.width = 1
        self.text = ""
        self.size = 11
        self.anchor = "start"
        self.task_id = 0
        self.is_background = False
        self.pattern = ""   # "dots" = pontos pretos sobre o fundo


def add_rect(shapes, x1, y1, x2, y2, fill, outline, task_id=0, is_background=False, pattern=""):
    shape = Shape("rect")
    shape.x1, shape.y1, shape.x2, shape.y2 = x1, y1, x2, y2
    shape.fill = fill
    shape.outline = outline
    shape.task_id = task_id
    shape.is_background = is_background
    shape.pattern = pattern
    shapes.append(shape)


def add_line(shapes, x1, y1, x2, y2, color, width=1):
    shape = Shape("line")
    shape.x1, shape.y1, shape.x2, shape.y2 = x1, y1, x2, y2
    shape.outline = color
    shape.width = width
    shapes.append(shape)


def add_polygon(shapes, points, fill, outline):
    shape = Shape("polygon")
    shape.points = points
    shape.fill = fill
    shape.outline = outline
    shapes.append(shape)


def add_text(shapes, x, y, text, size=11, anchor="start", color=COLOR_TEXT, task_id=0):
    shape = Shape("text")
    shape.x1, shape.y1 = x, y
    shape.text = text
    shape.size = size
    shape.anchor = anchor
    shape.fill = color
    shape.task_id = task_id
    shapes.append(shape)


# ---------- Símbolos dos eventos ----------

# Seta para cima: a ponta fica em y_tip e a base em y_base (y_base > y_tip)
def add_arrow_up(shapes, x, y_base, y_tip, color):
    add_line(shapes, x, y_base, x, y_tip + 4, color, 2)
    add_polygon(shapes, [(x, y_tip), (x - 4, y_tip + 7), (x + 4, y_tip + 7)], color, color)


# Seta para baixo: a ponta fica em y_tip e a base em y_base (y_base < y_tip)
def add_arrow_down(shapes, x, y_base, y_tip, color):
    add_line(shapes, x, y_base, x, y_tip - 4, color, 2)
    add_polygon(shapes, [(x, y_tip), (x - 4, y_tip - 7), (x + 4, y_tip - 7)], color, color)


def add_cross(shapes, x, y, color):
    add_line(shapes, x - 5, y - 5, x + 5, y + 5, color, 2)
    add_line(shapes, x - 5, y + 5, x + 5, y - 5, color, 2)


def add_diamond(shapes, x, y, color):
    add_polygon(shapes, [(x, y - 6), (x + 6, y), (x, y + 6), (x - 6, y)], color, "#000000")


# ---------- Funções auxiliares ----------

def to_css_color(hex_color):
    return "#" + hex_color


def text_color_for(hex_color):
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    # A luminância pondera mais o verde, ao qual a visão é mais sensível.
    brightness = 0.299 * red + 0.587 * green + 0.114 * blue
    if brightness > 150:
        return "#000000"
    return "#ffffff"


def tick_x(tick):
    return LEFT + tick * CELL_W


def cpu_at(result, tick, cpu):
    # None significa OFF. Ausência da coluna significa CPU inexistente naquele tick.
    row = result.timeline[tick]
    return row[cpu] if cpu < len(row) else CPU_ABSENT


# ---------- Montagem do gráfico ----------

# Fundo branco de cada linha de tarefa. Serve para o clique "pegar" em qualquer
# ponto da linha e para destacar a tarefa selecionada.
def build_row_backgrounds(shapes, result, rows_by_id):
    for task_id in rows_by_id:
        row = rows_by_id[task_id]
        add_rect(shapes, LEFT, row.top, tick_x(result.total_ticks), row.top + row.height,
                 "#ffffff", "#ffffff", task_id, True)


def build_task_rows(shapes, result, rows_by_id, color_by_id):
    for task_id in rows_by_id:
        row = rows_by_id[task_id]
        add_line(shapes, LEFT, row.top + row.height, tick_x(result.total_ticks), row.top + row.height, COLOR_GRID)
        add_text(shapes, LEFT - 10, row.top + row.height / 2, f"T{task_id}", 13, "end", COLOR_TEXT, task_id)

    for tick in range(result.total_ticks):
        for cpu, running in enumerate(result.timeline[tick]):
            if running is None:
                continue
            task_id = running[0]
            row = rows_by_id[task_id]
            row_y = row.instance_y(running[1])
            x = tick_x(tick)
            hex_color = color_by_id[task_id]
            add_rect(shapes, x, row_y + BAR_TOP, x + CELL_W, row_y + BAR_BOTTOM,
                     to_css_color(hex_color), "#000000", task_id)
            label = f"P{cpu + 1}/I{running[1]}" if row.height > ROW_H else f"P{cpu + 1}"
            add_text(shapes, x + CELL_W / 2, row_y + (BAR_TOP + BAR_BOTTOM) / 2,
                     label, 8 if row.height > ROW_H else 11, "middle", text_color_for(hex_color), task_id)


def build_suspended_rows(shapes, result, rows_by_id):
    for tick, suspended in enumerate(result.suspended_timeline):
        for task_id, instance in suspended:
            row_y = rows_by_id[task_id].instance_y(instance)
            add_rect(shapes, tick_x(tick), row_y + BAR_TOP, tick_x(tick + 1), row_y + BAR_BOTTOM,
                     COLOR_SUSPENDED, COLOR_SUSPENDED, task_id, pattern="dots")
    # Marcador no limite do relógio: indica a suspensão atual sem inventar um
    # intervalo de execução futuro antes que o usuário avance o próximo passo.
    for task_id, instance in result.current_suspended:
        row_y = rows_by_id[task_id].instance_y(instance)
        x = tick_x(result.total_ticks) + 5
        add_rect(shapes, x, row_y + BAR_TOP, x + 12, row_y + BAR_BOTTOM,
                 COLOR_SUSPENDED, COLOR_SUSPENDED, task_id, pattern="dots")


def build_events(shapes, result, rows_by_id):
    for event in result.events:
        row = rows_by_id[event.task_id]
        row_y = row.instance_y(event.instance)
        x = tick_x(event.tick)

        if event.kind == "arrival":
            add_arrow_up(shapes, x, row_y + ROW_H - 1, row_y + BAR_BOTTOM, COLOR_ARRIVAL)
        elif event.kind == "finish":
            add_arrow_down(shapes, x, row_y + 1, row_y + BAR_TOP, COLOR_FINISH)
        elif event.kind == "deadline_miss":
            add_cross(shapes, x, row_y + BAR_TOP / 2, COLOR_MISS)
        elif event.kind == "draw":
            # o sorteio vale para o tick inteiro: o losango fica no meio da célula
            add_diamond(shapes, x + CELL_W / 2, row_y + BAR_BOTTOM + (ROW_H - BAR_BOTTOM) / 2, COLOR_DRAW)
        elif event.kind == 'remove':
            add_cross(shapes, x, row.top + row.height / 2, '#000000')


def build_axis(shapes, result, axis_y):
    add_line(shapes, LEFT, axis_y, tick_x(result.total_ticks), axis_y, COLOR_AXIS, 2)
    for tick in range(result.total_ticks + 1):
        x = tick_x(tick)
        add_line(shapes, x, axis_y, x, axis_y + 5, COLOR_AXIS)
        add_text(shapes, x, axis_y + 17, str(tick), 11, "middle")
    add_text(shapes, tick_x(result.total_ticks) + 20, axis_y + 17, "tempo (ticks)", 11, "start")


# Uma linha por processador. Períodos seguidos na mesma situação viram um retângulo só.
# Processador sem tarefa aparece em cinza com o texto OFF (processador desligado).
def build_cpu_rows(shapes, result, cpu_top, color_by_id):
    add_text(shapes, LEFT - 10, cpu_top - 10, "Processadores", 12, "end")

    for cpu in range(result.max_cpus):
        row_y = cpu_top + cpu * CPU_ROW_H
        add_text(shapes, LEFT - 10, row_y + CPU_ROW_H / 2, f"CPU {cpu + 1}", 12, "end")

        start = 0
        while start < result.total_ticks:
            current = cpu_at(result, start, cpu)
            end = start + 1
            while end < result.total_ticks and cpu_at(result, end, cpu) == current:
                end += 1

            x1 = tick_x(start)
            x2 = tick_x(end)
            if current == CPU_ABSENT:
                add_rect(shapes, x1, row_y + 3, x2, row_y + CPU_ROW_H - 3, "#ffffff", COLOR_GRID)
                add_text(shapes, (x1 + x2) / 2, row_y + CPU_ROW_H / 2, "-", 10, "middle", "#808080")
            elif current is None:
                add_rect(shapes, x1, row_y + 3, x2, row_y + CPU_ROW_H - 3, COLOR_OFF, "#808080")
                add_text(shapes, (x1 + x2) / 2, row_y + CPU_ROW_H / 2, "OFF", 10, "middle")
            else:
                task_id = current[0]
                hex_color = color_by_id[task_id]
                add_rect(shapes, x1, row_y + 3, x2, row_y + CPU_ROW_H - 3, to_css_color(hex_color), "#000000", task_id)
                add_text(shapes, (x1 + x2) / 2, row_y + CPU_ROW_H / 2, f"T{current[0]}({current[1]})",
                         10, "middle", text_color_for(hex_color), task_id)
            start = end


# Desenhos de exemplo da legenda. Todos recebem o centro (x, y) do exemplo.
def sample_running(shapes, x, y):
    add_rect(shapes, x - 14, y - 9, x + 14, y + 9, "#4e79a7", "#000000")
    add_text(shapes, x, y, "P1", 11, "middle", "#ffffff")


def sample_ready(shapes, x, y):
    add_rect(shapes, x - 14, y - 9, x + 14, y + 9, "#ffffff", COLOR_GRID)


def sample_suspended(shapes, x, y):
    add_rect(shapes, x - 14, y - 9, x + 14, y + 9, COLOR_SUSPENDED, COLOR_SUSPENDED, pattern="dots")


def sample_arrival(shapes, x, y):
    add_arrow_up(shapes, x, y + 10, y - 10, COLOR_ARRIVAL)


def sample_finish(shapes, x, y):
    add_arrow_down(shapes, x, y - 10, y + 10, COLOR_FINISH)


def sample_miss(shapes, x, y):
    add_cross(shapes, x, y, COLOR_MISS)


def sample_draw(shapes, x, y):
    add_diamond(shapes, x, y, COLOR_DRAW)


def sample_off(shapes, x, y):
    add_rect(shapes, x - 14, y - 9, x + 14, y + 9, COLOR_OFF, "#808080")
    add_text(shapes, x, y, "OFF", 10, "middle")


def sample_absent(shapes, x, y):
    add_rect(shapes, x - 14, y - 9, x + 14, y + 9, "#ffffff", COLOR_GRID)
    add_text(shapes, x, y, "-", 10, "middle", "#808080")


def sample_system(shapes, x, y):
    add_diamond(shapes, x, y, COLOR_SYSTEM)


def sample_removed(shapes, x, y):
    add_cross(shapes, x, y, '#000000')


LEGEND_ITEMS = [
    (sample_running, "Tarefa executando (cor da tarefa; P# indica o processador usado)"),
    (sample_ready, "Tarefa na fila de prontos (sem cor)"),
    (sample_suspended, "Tarefa suspensa (preto pontilhado; marcador à direita = estado atual)"),
    (sample_arrival, "Chegada de uma instância da tarefa"),
    (sample_finish, "Término da execução da instância"),
    (sample_miss, "Perda de prazo (deadline)"),
    (sample_draw, "Sorteio no desempate (a tarefa escolhida começa a executar)"),
    (sample_off, "Processador desligado (não há tarefa para executar)"),
    (sample_absent, "Processador inexistente nesse intervalo (quantidade alterada)"),
    (sample_system, "Reconfiguração S# (+ agrupa alterações no mesmo instante)"),
    (sample_removed, "Tarefa removida; instâncias restantes canceladas"),
]


def build_legend(shapes, legend_top):
    add_text(shapes, LEFT, legend_top, "Legenda", 13, "start")

    line_h = 26
    y = legend_top + 22
    sample_x = LEFT + 20
    text_x = LEFT + 60

    for draw_sample, description in LEGEND_ITEMS:
        draw_sample(shapes, sample_x, y)
        add_text(shapes, text_x, y, description, 12)
        y += line_h

    add_text(shapes, LEFT, y, "Em faixas simultâneas, P#/I# identifica processador e instância.", 11)
    y += line_h
    return y


def build_system_events(shapes, result, system_top, axis_y, width):
    """Retorna o fim do rodapé; eventos no mesmo tick compartilham um marcador S#+."""
    add_text(shapes, LEFT, system_top,
             f"Configuração inicial: {result.initial_algorithm}, {result.initial_num_cpus} CPU(s)", 11)
    next_y = system_top + 20

    markers = {}
    for index, event in enumerate(result.system_events, start=1):
        markers.setdefault(event.tick, []).append(index)
        description = f"S{index} | t={event.tick}: {event.description}"
        text_width = max(40, int((width - LEFT - RIGHT) / SYSTEM_TEXT_CHAR_WIDTH))
        for line in textwrap.wrap(description, width=text_width):
            add_text(shapes, LEFT, next_y, line, 11)
            next_y += 17

    for tick, numbers in markers.items():
        add_diamond(shapes, tick_x(tick), axis_y + 35, COLOR_SYSTEM)
        label = f"S{numbers[0]}" + ('+' if len(numbers) > 1 else '')
        add_text(shapes, tick_x(tick), axis_y + 49, label, 9, 'middle', COLOR_SYSTEM)
    return next_y


def build_gantt(result):
    """Retorna (formas, largura, altura), abrangendo todo o histórico disponível."""
    shapes = []

    rows_by_id = build_rows(result)

    color_by_id = {}
    for info in result.tasks:
        color_by_id[info.id] = info.color

    axis_y = TOP + sum(row.height for row in rows_by_id.values())
    cpu_top = axis_y + 70
    system_top = cpu_top + result.max_cpus * CPU_ROW_H + 30
    width = max(MIN_WIDTH, tick_x(result.total_ticks) + RIGHT + TIME_LABEL_SPACE)

    add_text(shapes, LEFT, 24,
             f"Gráfico de Gantt - algoritmo atual {result.algorithm} - {result.num_cpus} CPU(s) - {result.total_ticks} ticks",
             15, "start")

    build_row_backgrounds(shapes, result, rows_by_id)

    # linhas verticais da grade (desenhadas primeiro para ficarem atrás das barras)
    for tick in range(result.total_ticks + 1):
        add_line(shapes, tick_x(tick), TOP, tick_x(tick), axis_y, COLOR_GRID)

    build_task_rows(shapes, result, rows_by_id, color_by_id)
    build_suspended_rows(shapes, result, rows_by_id)
    build_axis(shapes, result, axis_y)
    build_events(shapes, result, rows_by_id)
    build_cpu_rows(shapes, result, cpu_top, color_by_id)
    next_y = build_system_events(shapes, result, system_top, axis_y, width)
    height = build_legend(shapes, next_y + 15) + 10

    return shapes, width, height
