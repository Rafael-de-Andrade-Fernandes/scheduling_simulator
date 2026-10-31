"""Primitivas do Gantt completo, com faixas para instâncias simultâneas."""
# Gera o gráfico de Gantt como formas primitivas (independente de biblioteca).
# Consome os dados de 'result' apenas em modo leitura.
from dataclasses import dataclass
import textwrap

# Layout (pixels)
CELL_W = 34         # Largura por tick
ROW_H = 54          # Altura por tarefa
CPU_ROW_H = 30      # Altura por CPU
LEFT = 100          # Margem esquerda (rótulos)
TOP = 50            # Margem superior (título)
RIGHT = 30          # Margem direita
MIN_WIDTH = 820     # Inclui a legenda completa mesmo em simulações curtas

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


@dataclass
class TaskRow:
    """Faixas separadas impedem que duas instâncias ocultem a execução uma da outra."""
    top: int
    height: int
    lanes: dict

    def instance_y(self, instance):
        """Resolve a posição vertical da instância na sua faixa, sem sobrepor outras."""
        return self.top + self.lanes.get(instance, 0) * LANE_H


def build_rows(result):
    """Empacota intervalos ativos em faixas e mantém IDs decrescentes no eixo vertical."""
    spans = {}
    for event in result.events:
        if event.instance <= 0:
            continue
        key = (result.resolve_task_id(event.task_id), event.instance)
        if event.kind == 'arrival':
            spans.setdefault(key, [event.tick, result.total_ticks])
        elif event.kind == 'finish':
            spans.setdefault(key, [event.tick, event.tick])[1] = max(event.tick - 1, spans.get(key, [event.tick])[0])
    rows, offset = {}, TOP
    for task_id in sorted((info.id for info in result.tasks), reverse=True):
        lanes, ends = {}, []
        jobs = sorted(((start, end, instance) for (index, instance), (start, end) in spans.items()
                       if index == task_id))
        for start, end, instance in jobs:
            lane = next((index for index, previous_end in enumerate(ends) if previous_end < start), len(ends))
            if lane == len(ends):
                ends.append(end)
            else:
                ends[lane] = end
            lanes[instance] = lane
        height = ROW_H + max(0, len(ends) - 1) * LANE_H
        rows[task_id] = TaskRow(offset, height, lanes)
        offset += height
    return rows


# Uma forma desenhável. O campo "kind" diz quais
# outros campos valem:
#   "rect"    -> x1, y1, x2, y2, fill, outline
#   "line"    -> x1, y1, x2, y2, outline (cor), width
#   "polygon" -> points (lista de pares (x, y)), fill, outline
#   "text"    -> x1, y1 (posição), text, size, anchor ("start", "middle" ou "end"), fill (cor)
# task_id: se for maior que 0, a forma pertence a essa tarefa (o clique nela seleciona a tarefa).
# is_background: marca o retângulo de fundo da linha da tarefa (usado para destacar a seleção).
class Shape:
    """Primitiva comum ao Canvas e ao SVG, independente da janela e do núcleo."""
    def __init__(self, kind):
        """Inicializa os dados de Shape com vínculos e valores próprios deste objeto."""
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
    """Acrescenta uma área com cor/padrão e etiquetas de seleção da tarefa."""
    s = Shape("rect")
    s.x1, s.y1, s.x2, s.y2 = x1, y1, x2, y2
    s.fill = fill
    s.outline = outline
    s.task_id = task_id
    s.is_background = is_background
    s.pattern = pattern
    shapes.append(s)


def add_line(shapes, x1, y1, x2, y2, color, width=1):
    """Acrescenta uma linha para grades, eixos, setas e símbolos de eventos."""
    s = Shape("line")
    s.x1, s.y1, s.x2, s.y2 = x1, y1, x2, y2
    s.outline = color
    s.width = width
    shapes.append(s)


def add_polygon(shapes, points, fill, outline):
    """Acrescenta um polígono independente do renderizador."""
    s = Shape("polygon")
    s.points = points
    s.fill = fill
    s.outline = outline
    shapes.append(s)


def add_text(shapes, x, y, text, size=11, anchor="start", color=COLOR_TEXT, task_id=0):
    """Acrescenta texto com âncora e identificação opcional da tarefa."""
    s = Shape("text")
    s.x1, s.y1 = x, y
    s.text = text
    s.size = size
    s.anchor = anchor
    s.fill = color
    s.task_id = task_id
    shapes.append(s)


# ---------- Símbolos dos eventos ----------

# Seta para cima: a ponta fica em y_tip e a base em y_base (y_base > y_tip)
def add_arrow_up(shapes, x, y_base, y_tip, color):
    """Representa a chegada exatamente na coordenada horizontal do evento."""
    add_line(shapes, x, y_base, x, y_tip + 4, color, 2)
    add_polygon(shapes, [(x, y_tip), (x - 4, y_tip + 7), (x + 4, y_tip + 7)], color, color)


# Seta para baixo: a ponta fica em y_tip e a base em y_base (y_base < y_tip)
def add_arrow_down(shapes, x, y_base, y_tip, color):
    """Representa a conclusão no limite do intervalo executado."""
    add_line(shapes, x, y_base, x, y_tip - 4, color, 2)
    add_polygon(shapes, [(x, y_tip), (x - 4, y_tip - 7), (x + 4, y_tip - 7)], color, color)


# X vermelho centrado em (x, y)
def add_cross(shapes, x, y, color):
    """Representa perda de prazo ou remoção, diferenciadas pela cor."""
    add_line(shapes, x - 5, y - 5, x + 5, y + 5, color, 2)
    add_line(shapes, x - 5, y + 5, x + 5, y - 5, color, 2)


# Losango centrado em (x, y)
def add_diamond(shapes, x, y, color):
    """Representa sorteio ou reconfiguração conforme a cor da legenda."""
    add_polygon(shapes, [(x, y - 6), (x + 6, y), (x, y + 6), (x - 6, y)], color, "#000000")


# ---------- Funções auxiliares ----------

# "00FF00" -> "#00FF00"
def to_css_color(hex_color):
    """Converte o RGB validado para o formato aceito por Canvas e SVG."""
    return "#" + hex_color


# Escolhe texto preto ou branco, o que ficar mais legível sobre a cor de fundo
def text_color_for(hex_color):
    """Escolhe contraste legível para o rótulo sobre a cor da tarefa."""
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    brightness = 0.299 * red + 0.587 * green + 0.114 * blue
    if brightness > 150:
        return "#000000"
    return "#ffffff"


# Posição horizontal (em pixels) do início de um tick
def tick_x(tick):
    """Converte o relógio em posição sem impor limite máximo de tempo ao gráfico."""
    return LEFT + tick * CELL_W


def color_at(result, tick, task_id, defaults):
    """Lê a cor histórica do intervalo, preservando edições posteriores."""
    default = defaults[result.resolve_task_id(task_id)]
    if tick < len(result.task_colors):
        return result.task_colors[tick].get(task_id, default)
    return default


def cpu_at(result, tick, cpu):
    """Distingue CPU desligada de CPU que ainda não existia naquele intervalo."""
    row = result.timeline[tick]
    return row[cpu] if cpu < len(row) else CPU_ABSENT


# ---------- Montagem do gráfico ----------

# Fundo branco de cada linha de tarefa. Serve para o clique "pegar" em qualquer
# ponto da linha e para destacar a tarefa selecionada.
def build_row_backgrounds(shapes, result, rows_by_id):
    """Cria fundos selecionáveis em toda a altura das faixas da tarefa."""
    for task_id in rows_by_id:
        row = rows_by_id[task_id]
        add_rect(shapes, LEFT, row.top, tick_x(result.total_ticks), row.top + row.height,
                 "#ffffff", "#ffffff", task_id, True)


# Desenha a grade, os rótulos T1, T2... e as barras de execução de cada tarefa
def build_task_rows(shapes, result, rows_by_id, color_by_id):
    """Desenha cada execução na faixa da instância e identifica a CPU usada."""
    for task_id in rows_by_id:
        row = rows_by_id[task_id]
        add_line(shapes, LEFT, row.top + row.height, tick_x(result.total_ticks), row.top + row.height, COLOR_GRID)
        add_text(shapes, LEFT - 10, row.top + row.height / 2, f"T{task_id}", 13, "end", COLOR_TEXT, task_id)

    # Barras: para cada tick e cada CPU, pinta a célula da tarefa que executou
    for tick in range(result.total_ticks):
        for cpu, running in enumerate(result.timeline[tick]):
            if running is None:
                continue
            task_id = result.resolve_task_id(running[0])
            row = rows_by_id[task_id]
            row_y = row.instance_y(running[1])
            x = tick_x(tick)
            hex_color = color_at(result, tick, running[0], color_by_id)
            add_rect(shapes, x, row_y + BAR_TOP, x + CELL_W, row_y + BAR_BOTTOM,
                     to_css_color(hex_color), "#000000", task_id)
            label = f"P{cpu + 1}/I{running[1]}" if row.height > ROW_H else f"P{cpu + 1}"
            add_text(shapes, x + CELL_W / 2, row_y + (BAR_TOP + BAR_BOTTOM) / 2,
                     label, 8 if row.height > ROW_H else 11, "middle", text_color_for(hex_color), task_id)


def build_suspended_rows(shapes, result, rows_by_id):
    """Desenha suspensão pontilhada e um marcador do estado atual no limite do relógio."""
    for tick, suspended in enumerate(result.suspended_timeline):
        for task_id, instance in suspended:
            task_id = result.resolve_task_id(task_id)
            row_y = rows_by_id[task_id].instance_y(instance)
            add_rect(shapes, tick_x(tick), row_y + BAR_TOP, tick_x(tick + 1), row_y + BAR_BOTTOM,
                     COLOR_SUSPENDED, COLOR_SUSPENDED, task_id, pattern="dots")
    # Marcador no limite do relógio: indica a suspensão atual sem inventar um
    # intervalo de execução futuro antes que o usuário avance o próximo passo.
    for task_id, instance in result.current_suspended:
        task_id = result.resolve_task_id(task_id)
        row_y = rows_by_id[task_id].instance_y(instance)
        x = tick_x(result.total_ticks) + 5
        add_rect(shapes, x, row_y + BAR_TOP, x + 12, row_y + BAR_BOTTOM,
                 COLOR_SUSPENDED, COLOR_SUSPENDED, task_id, pattern="dots")


# Desenha as setas, X e losangos dos eventos
def build_events(shapes, result, rows_by_id):
    """Posiciona chegadas, conclusões, perdas, sorteios e remoções por instante/instância."""
    for event in result.events:
        row = rows_by_id[result.resolve_task_id(event.task_id)]
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


# Eixo X com o número de cada tick
def build_axis(shapes, result, axis_y):
    """Desenha o relógio inteiro até o instante final, além da largura da janela."""
    add_line(shapes, LEFT, axis_y, tick_x(result.total_ticks), axis_y, COLOR_AXIS, 2)
    for tick in range(result.total_ticks + 1):
        x = tick_x(tick)
        add_line(shapes, x, axis_y, x, axis_y + 5, COLOR_AXIS)
        add_text(shapes, x, axis_y + 17, str(tick), 11, "middle")
    add_text(shapes, tick_x(result.total_ticks) + 20, axis_y + 17, "tempo (ticks)", 11, "start")


# Uma linha por processador. Períodos seguidos na mesma situação viram um retângulo só.
# Processador sem tarefa aparece em cinza com o texto OFF (processador desligado).
def build_cpu_rows(shapes, result, cpu_top, color_by_id):
    """Agrupa intervalos de mesmo trabalho/cor, incluindo OFF e ausência histórica."""
    add_text(shapes, LEFT - 10, cpu_top - 10, "Processadores", 12, "end")

    for cpu in range(result.max_cpus):
        row_y = cpu_top + cpu * CPU_ROW_H
        add_text(shapes, LEFT - 10, row_y + CPU_ROW_H / 2, f"CPU {cpu + 1}", 12, "end")

        start = 0
        while start < result.total_ticks:
            current = cpu_at(result, start, cpu)
            current_color = (color_at(result, start, current[0], color_by_id)
                             if current not in (None, CPU_ABSENT) else None)
            # avança "end" enquanto a CPU continua fazendo a mesma coisa
            end = start + 1
            while (end < result.total_ticks and cpu_at(result, end, cpu) == current
                   and (current in (None, CPU_ABSENT)
                        or color_at(result, end, current[0], color_by_id) == current_color)):
                end = end + 1

            x1 = tick_x(start)
            x2 = tick_x(end)
            if current == CPU_ABSENT:
                add_rect(shapes, x1, row_y + 3, x2, row_y + CPU_ROW_H - 3, "#ffffff", COLOR_GRID)
                add_text(shapes, (x1 + x2) / 2, row_y + CPU_ROW_H / 2, "-", 10, "middle", "#808080")
            elif current is None:
                add_rect(shapes, x1, row_y + 3, x2, row_y + CPU_ROW_H - 3, COLOR_OFF, "#808080")
                add_text(shapes, (x1 + x2) / 2, row_y + CPU_ROW_H / 2, "OFF", 10, "middle")
            else:
                hex_color = current_color
                task_id = result.resolve_task_id(current[0])
                add_rect(shapes, x1, row_y + 3, x2, row_y + CPU_ROW_H - 3, to_css_color(hex_color), "#000000", task_id)
                add_text(shapes, (x1 + x2) / 2, row_y + CPU_ROW_H / 2, f"T{current[0]}({current[1]})",
                         10, "middle", text_color_for(hex_color), task_id)
            start = end


# Legenda com um exemplo de cada elemento gráfico. Devolve o y onde a legenda termina.
def build_legend(shapes, legend_top):
    """Explica todos os símbolos, padrões e identificadores utilizados no gráfico."""
    add_text(shapes, LEFT, legend_top, "Legenda", 13, "start")

    line_h = 26
    y = legend_top + 22
    sample_x = LEFT + 20     # centro do desenho de exemplo
    text_x = LEFT + 60       # início do texto

    # 1. execução
    add_rect(shapes, sample_x - 14, y - 9, sample_x + 14, y + 9, "#4e79a7", "#000000")
    add_text(shapes, sample_x, y, "P1", 11, "middle", "#ffffff")
    add_text(shapes, text_x, y, "Tarefa executando (cor da tarefa; P# indica o processador usado)", 12)
    y += line_h

    # 2. pronta
    add_rect(shapes, sample_x - 14, y - 9, sample_x + 14, y + 9, "#ffffff", COLOR_GRID)
    add_text(shapes, text_x, y, "Tarefa na fila de prontos (sem cor)", 12)
    y += line_h

    # 3. chegada
    add_rect(shapes, sample_x - 14, y - 9, sample_x + 14, y + 9,
             COLOR_SUSPENDED, COLOR_SUSPENDED, pattern="dots")
    add_text(shapes, text_x, y, "Tarefa suspensa (preto pontilhado; marcador à direita = estado atual)", 12)
    y += line_h

    # Chegada
    add_arrow_up(shapes, sample_x, y + 10, y - 10, COLOR_ARRIVAL)
    add_text(shapes, text_x, y, "Chegada de uma instância da tarefa", 12)
    y += line_h

    # 4. término
    add_arrow_down(shapes, sample_x, y - 10, y + 10, COLOR_FINISH)
    add_text(shapes, text_x, y, "Término da execução da instância", 12)
    y += line_h

    # 5. perda de prazo
    add_cross(shapes, sample_x, y, COLOR_MISS)
    add_text(shapes, text_x, y, "Perda de prazo (deadline)", 12)
    y += line_h

    # 6. sorteio
    add_diamond(shapes, sample_x, y, COLOR_DRAW)
    add_text(shapes, text_x, y, "Sorteio no desempate (a tarefa escolhida começa a executar)", 12)
    y += line_h

    # 7. CPU desligada
    add_rect(shapes, sample_x - 14, y - 9, sample_x + 14, y + 9, COLOR_OFF, "#808080")
    add_text(shapes, sample_x, y, "OFF", 10, "middle")
    add_text(shapes, text_x, y, "Processador desligado (não há tarefa para executar)", 12)
    y += line_h

    add_rect(shapes, sample_x - 14, y - 9, sample_x + 14, y + 9, "#ffffff", COLOR_GRID)
    add_text(shapes, sample_x, y, "-", 10, "middle", "#808080")
    add_text(shapes, text_x, y, "Processador inexistente nesse intervalo (quantidade alterada)", 12)
    y += line_h

    add_diamond(shapes, sample_x, y, COLOR_SYSTEM)
    add_text(shapes, text_x, y, "Reconfiguração S# (+ agrupa alterações no mesmo instante)", 12)
    y += line_h
    add_cross(shapes, sample_x, y, '#000000')
    add_text(shapes, text_x, y, "Tarefa removida; instâncias restantes canceladas", 12)
    y += line_h
    add_text(shapes, LEFT, y, "Em faixas simultâneas, P#/I# identifica processador e instância.", 11)
    y += line_h

    return y


# Função principal: devolve (lista_de_formas, largura, altura) do gráfico completo.
def build_gantt(result):
    """Compõe o gráfico completo somente a partir dos dados do resultado."""
    shapes = []

    # A tarefa de menor ID fica mais perto do eixo X (embaixo); a de maior ID fica no topo.
    rows_by_id = build_rows(result)

    color_by_id = {}
    for info in result.tasks:
        color_by_id[info.id] = info.color

    axis_y = TOP + sum(row.height for row in rows_by_id.values())
    cpu_top = axis_y + 70
    system_top = cpu_top + result.max_cpus * CPU_ROW_H + 30
    width = max(MIN_WIDTH, tick_x(result.total_ticks) + RIGHT + 90)

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
    add_text(shapes, LEFT, system_top,
             f"Configuração inicial: {result.initial_algorithm}, {result.initial_num_cpus} CPU(s)", 11)
    next_y = system_top + 20
    markers = {}
    for index, event in enumerate(result.system_events, start=1):
        markers.setdefault(event.tick, []).append(index)
        description = f"S{index} | t={event.tick}: {event.description}"
        for line in textwrap.wrap(description, width=max(40, int((width - LEFT - RIGHT) / 6.2))):
            add_text(shapes, LEFT, next_y, line, 11)
            next_y += 17
    for tick, numbers in markers.items():
        add_diamond(shapes, tick_x(tick), axis_y + 35, COLOR_SYSTEM)
        label = f"S{numbers[0]}" + ('+' if len(numbers) > 1 else '')
        add_text(shapes, tick_x(tick), axis_y + 49, label, 9, 'middle', COLOR_SYSTEM)
    legend_top = next_y + 15
    height = build_legend(shapes, legend_top) + 10

    width = tick_x(result.total_ticks) + RIGHT + 90    # 90 = espaço do texto "tempo (ticks)"
    if width < MIN_WIDTH:
        width = MIN_WIDTH

    return shapes, width, height
