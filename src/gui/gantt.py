# Gera o gráfico de Gantt como formas primitivas (independente de biblioteca).
# Consome os dados de 'result' apenas em modo leitura.

# Layout (pixels)
CELL_W = 34         # Largura por tick
ROW_H = 54          # Altura por tarefa
CPU_ROW_H = 30      # Altura por CPU
LEFT = 100          # Margem esquerda (rótulos)
TOP = 50            # Margem superior (título)
RIGHT = 30          # Margem direita
MIN_WIDTH = 640     # Largura mínima total

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


# Uma forma desenhável. O campo "kind" diz quais
# outros campos valem:
#   "rect"    -> x1, y1, x2, y2, fill, outline
#   "line"    -> x1, y1, x2, y2, outline (cor), width
#   "polygon" -> points (lista de pares (x, y)), fill, outline
#   "text"    -> x1, y1 (posição), text, size, anchor ("start", "middle" ou "end"), fill (cor)
# task_id: se for maior que 0, a forma pertence a essa tarefa (o clique nela seleciona a tarefa).
# is_background: marca o retângulo de fundo da linha da tarefa (usado para destacar a seleção).
class Shape:
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


def add_rect(shapes, x1, y1, x2, y2, fill, outline, task_id=0, is_background=False):
    s = Shape("rect")
    s.x1, s.y1, s.x2, s.y2 = x1, y1, x2, y2
    s.fill = fill
    s.outline = outline
    s.task_id = task_id
    s.is_background = is_background
    shapes.append(s)


def add_line(shapes, x1, y1, x2, y2, color, width=1):
    s = Shape("line")
    s.x1, s.y1, s.x2, s.y2 = x1, y1, x2, y2
    s.outline = color
    s.width = width
    shapes.append(s)


def add_polygon(shapes, points, fill, outline):
    s = Shape("polygon")
    s.points = points
    s.fill = fill
    s.outline = outline
    shapes.append(s)


def add_text(shapes, x, y, text, size=11, anchor="start", color=COLOR_TEXT, task_id=0):
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
    add_line(shapes, x, y_base, x, y_tip + 4, color, 2)
    add_polygon(shapes, [(x, y_tip), (x - 4, y_tip + 7), (x + 4, y_tip + 7)], color, color)


# Seta para baixo: a ponta fica em y_tip e a base em y_base (y_base < y_tip)
def add_arrow_down(shapes, x, y_base, y_tip, color):
    add_line(shapes, x, y_base, x, y_tip - 4, color, 2)
    add_polygon(shapes, [(x, y_tip), (x - 4, y_tip - 7), (x + 4, y_tip - 7)], color, color)


# X vermelho centrado em (x, y)
def add_cross(shapes, x, y, color):
    add_line(shapes, x - 5, y - 5, x + 5, y + 5, color, 2)
    add_line(shapes, x - 5, y + 5, x + 5, y - 5, color, 2)


# Losango centrado em (x, y)
def add_diamond(shapes, x, y, color):
    add_polygon(shapes, [(x, y - 6), (x + 6, y), (x, y + 6), (x - 6, y)], color, "#000000")


# ---------- Funções auxiliares ----------

# "00FF00" -> "#00FF00"
def to_css_color(hex_color):
    return "#" + hex_color


# Escolhe texto preto ou branco, o que ficar mais legível sobre a cor de fundo
def text_color_for(hex_color):
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    brightness = 0.299 * red + 0.587 * green + 0.114 * blue
    if brightness > 150:
        return "#000000"
    return "#ffffff"


# Posição horizontal (em pixels) do início de um tick
def tick_x(tick):
    return LEFT + tick * CELL_W


# ---------- Montagem do gráfico ----------

# Fundo branco de cada linha de tarefa. Serve para o clique "pegar" em qualquer
# ponto da linha e para destacar a tarefa selecionada.
def build_row_backgrounds(shapes, result, rows_by_id):
    for task_id in rows_by_id:
        row_y = TOP + rows_by_id[task_id] * ROW_H
        add_rect(shapes, LEFT, row_y, tick_x(result.total_ticks), row_y + ROW_H,
                 "#ffffff", "#ffffff", task_id, True)


# Desenha a grade, os rótulos T1, T2... e as barras de execução de cada tarefa
def build_task_rows(shapes, result, rows_by_id, color_by_id):
    for task_id in rows_by_id:
        row_y = TOP + rows_by_id[task_id] * ROW_H
        add_line(shapes, LEFT, row_y + ROW_H, tick_x(result.total_ticks), row_y + ROW_H, COLOR_GRID)
        add_text(shapes, LEFT - 10, row_y + (BAR_TOP + BAR_BOTTOM) / 2, f"T{task_id}", 13, "end", COLOR_TEXT, task_id)

    # Barras: para cada tick e cada CPU, pinta a célula da tarefa que executou
    for tick in range(result.total_ticks):
        for cpu in range(result.num_cpus):
            running = result.timeline[tick][cpu]
            if running is None:
                continue
            task_id = running[0]
            row_y = TOP + rows_by_id[task_id] * ROW_H
            x = tick_x(tick)
            hex_color = color_by_id[task_id]
            add_rect(shapes, x, row_y + BAR_TOP, x + CELL_W, row_y + BAR_BOTTOM,
                     to_css_color(hex_color), "#000000", task_id)
            add_text(shapes, x + CELL_W / 2, row_y + (BAR_TOP + BAR_BOTTOM) / 2,
                     f"P{cpu + 1}", 11, "middle", text_color_for(hex_color), task_id)


# Desenha as setas, X e losangos dos eventos
def build_events(shapes, result, rows_by_id):
    for event in result.events:
        row_y = TOP + rows_by_id[event.task_id] * ROW_H
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


# Eixo X com o número de cada tick
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

    for cpu in range(result.num_cpus):
        row_y = cpu_top + cpu * CPU_ROW_H
        add_text(shapes, LEFT - 10, row_y + CPU_ROW_H / 2, f"CPU {cpu + 1}", 12, "end")

        start = 0
        while start < result.total_ticks:
            current = result.timeline[start][cpu]
            # avança "end" enquanto a CPU continua fazendo a mesma coisa
            end = start + 1
            while end < result.total_ticks and result.timeline[end][cpu] == current:
                end = end + 1

            x1 = tick_x(start)
            x2 = tick_x(end)
            if current is None:
                add_rect(shapes, x1, row_y + 3, x2, row_y + CPU_ROW_H - 3, COLOR_OFF, "#808080")
                add_text(shapes, (x1 + x2) / 2, row_y + CPU_ROW_H / 2, "OFF", 10, "middle")
            else:
                hex_color = color_by_id[current[0]]
                add_rect(shapes, x1, row_y + 3, x2, row_y + CPU_ROW_H - 3, to_css_color(hex_color), "#000000", current[0])
                add_text(shapes, (x1 + x2) / 2, row_y + CPU_ROW_H / 2, f"T{current[0]}({current[1]})",
                         10, "middle", text_color_for(hex_color), current[0])
            start = end


# Legenda com um exemplo de cada elemento gráfico. Devolve o y onde a legenda termina.
def build_legend(shapes, legend_top):
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

    return y


# Função principal: devolve (lista_de_formas, largura, altura) do gráfico completo.
def build_gantt(result):
    shapes = []

    # A tarefa de menor ID fica mais perto do eixo X (embaixo); a de maior ID fica no topo.
    sorted_ids = sorted([info.id for info in result.tasks], reverse=True)
    rows_by_id = {}
    for row in range(len(sorted_ids)):
        rows_by_id[sorted_ids[row]] = row

    color_by_id = {}
    for info in result.tasks:
        color_by_id[info.id] = info.color

    axis_y = TOP + len(sorted_ids) * ROW_H
    cpu_top = axis_y + 70
    legend_top = cpu_top + result.num_cpus * CPU_ROW_H + 30

    add_text(shapes, LEFT, 24,
             f"Gráfico de Gantt - algoritmo {result.algorithm} - {result.num_cpus} CPU(s) - {result.total_ticks} ticks",
             15, "start")

    build_row_backgrounds(shapes, result, rows_by_id)

    # linhas verticais da grade (desenhadas primeiro para ficarem atrás das barras)
    for tick in range(result.total_ticks + 1):
        add_line(shapes, tick_x(tick), TOP, tick_x(tick), axis_y, COLOR_GRID)

    build_task_rows(shapes, result, rows_by_id, color_by_id)
    build_axis(shapes, result, axis_y)
    build_events(shapes, result, rows_by_id)
    build_cpu_rows(shapes, result, cpu_top, color_by_id)
    height = build_legend(shapes, legend_top) + 10

    width = tick_x(result.total_ticks) + RIGHT + 90    # 90 = espaço do texto "tempo (ticks)"
    if width < MIN_WIDTH:
        width = MIN_WIDTH

    return shapes, width, height
