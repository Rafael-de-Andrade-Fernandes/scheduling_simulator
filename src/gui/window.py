import os
import tkinter
from tkinter import filedialog, messagebox

from gui.gantt import build_gantt
from gui.report import make_report, make_task_status
from gui.svg_export import save_svg


# Janela principal do simulador.
#
# Esta parte NÃO conhece o core da simulação. Ela recebe do main.py uma função:
#     simulate(caminho_do_arquivo) -> (resultado, log)
# onde resultado é None se a simulação falhou. Assim o core e a janela ficam separados.
class SimulatorWindow:
    def __init__(self, simulate, config_path, output_dir):
        self.simulate = simulate
        self.config_path = config_path
        self.output_dir = output_dir
        # Último gráfico desenhado (guardado para o botão "Salvar imagem")
        self.shapes = []
        self.chart_width = 0
        self.chart_height = 0
        # Resultado da última simulação e tarefa selecionada (0 = nenhuma)
        self.result = None
        self.selected_task_id = 0
        # Campos editáveis do menu lateral: nome do campo -> caixa de texto
        self.entries = {}

        self.root = tkinter.Tk()
        self.root.title("Simulador de Escalonamento")
        self.root.geometry("1100x760")

        self.build_toolbar()
        self.build_canvas()
        self.build_text_area()
        self.show_message("Escolha um arquivo de configuração e clique em "
                          "\"Executar simulação completa\".")

    # ---------- Montagem da janela ----------

    def build_toolbar(self):
        toolbar = tkinter.Frame(self.root)
        toolbar.pack(side="top", fill="x", padx=6, pady=6)

        tkinter.Button(toolbar, text="Abrir configuração...", command=self.on_open).pack(side="left")
        tkinter.Button(toolbar, text="Executar simulação completa", command=self.on_run).pack(side="left", padx=6)
        tkinter.Button(toolbar, text="<< Voltar", command=self.on_step_back).pack(side="left")
        tkinter.Button(toolbar, text="Passo >>", command=self.on_step_forward).pack(side="left", padx=6)
        tkinter.Button(toolbar, text="Salvar imagem (SVG)...", command=self.on_save).pack(side="left")

        self.path_label = tkinter.Label(toolbar, text=self.config_path, anchor="w")
        self.path_label.pack(side="left", padx=10)

    def build_canvas(self):
        middle = tkinter.Frame(self.root)
        middle.pack(side="top", fill="both", expand=True, padx=6)

        # O menu lateral é empacotado antes para ficar sempre visível à direita
        self.build_side_panel(middle)

        frame = tkinter.Frame(middle)
        frame.pack(side="left", fill="both", expand=True)

        self.canvas = tkinter.Canvas(frame, background="white")
        scroll_x = tkinter.Scrollbar(frame, orient="horizontal", command=self.canvas.xview)
        scroll_y = tkinter.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=scroll_x.set, yscrollcommand=scroll_y.set)

        scroll_x.pack(side="bottom", fill="x")
        scroll_y.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

    # Menu lateral: mostra a situação da tarefa clicada e permite editar suas características
    def build_side_panel(self, parent):
        panel = tkinter.Frame(parent, width=290, borderwidth=1, relief="groove")
        panel.pack(side="right", fill="y", padx=(6, 0))
        panel.pack_propagate(False)

        self.panel_title = tkinter.Label(panel, text="Nenhuma tarefa selecionada",
                                         font=("Helvetica", 12, "bold"))
        self.panel_title.pack(side="top", pady=(8, 2))
        self.panel_hint = tkinter.Label(panel, text="Clique em uma tarefa no gráfico.",
                                        wraplength=260, justify="left")
        self.panel_hint.pack(side="top")

        tkinter.Label(panel, text="Situação", anchor="w", font=("Helvetica", 10, "bold")).pack(
            side="top", fill="x", padx=8, pady=(10, 0))
        self.status_text = tkinter.Text(panel, height=5, width=34, state="disabled", borderwidth=0,
                                        background=panel.cget("background"))
        self.status_text.pack(side="top", fill="x", padx=8)

        tkinter.Label(panel, text="Características (editáveis)", anchor="w",
                      font=("Helvetica", 10, "bold")).pack(side="top", fill="x", padx=8, pady=(10, 2))

        form = tkinter.Frame(panel)
        form.pack(side="top", fill="x", padx=8)
        field_names = [("color", "Cor (RGB hex)"), ("arrival", "Ingresso"), ("duration", "Duração"),
                       ("period", "Período"), ("deadline", "Prazo"), ("events", "Eventos")]
        for row in range(len(field_names)):
            key = field_names[row][0]
            tkinter.Label(form, text=field_names[row][1], anchor="w").grid(row=row, column=0, sticky="w", pady=2)
            entry = tkinter.Entry(form, width=18)
            entry.grid(row=row, column=1, sticky="e", pady=2, padx=(6, 0))
            self.entries[key] = entry

        tkinter.Button(panel, text="Aplicar alterações", command=self.on_apply_task).pack(side="top", pady=10)
        tkinter.Label(panel, text="Aviso: por enquanto as alterações não têm efeito na simulação.",
                      wraplength=260, justify="left", foreground="#a05000").pack(side="top", padx=8)

    def build_text_area(self):
        frame = tkinter.Frame(self.root)
        frame.pack(side="bottom", fill="x", padx=6, pady=6)

        self.text = tkinter.Text(frame, height=8, state="disabled")
        scroll = tkinter.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="x", expand=True)

    # ---------- Ações dos botões ----------

    def on_open(self):
        path = filedialog.askopenfilename(title="Escolha o arquivo de configuração",
                                          filetypes=[("Texto", "*.txt"), ("Todos os arquivos", "*")])
        if path:
            self.config_path = path
            self.path_label.configure(text=path)

    def on_run(self):
        result, log = self.simulate(self.config_path)

        if result is None:
            # O log termina com a mensagem de erro explicando o motivo
            self.show_message(log)
            messagebox.showerror("Erro na simulação", last_lines(log, 3))
            return

        self.result = result
        self.shapes, self.chart_width, self.chart_height = build_gantt(result)
        self.draw_shapes()
        self.select_task(0)

        # O PDF pede que a imagem seja gerada ao final da simulação
        os.makedirs(self.output_dir, exist_ok=True)
        image_path = os.path.join(self.output_dir, "gantt.svg")
        save_svg(self.shapes, self.chart_width, self.chart_height, image_path)

        self.show_message(make_report(result) + "\n\nImagem salva em: " + image_path
                          + "\n\n--- Log da simulação ---\n" + log)

    # Botões do modo passo-a-passo: ainda não implementados (não fazem nada por enquanto).
    def on_step_forward(self):
        pass

    def on_step_back(self):
        pass

    # Botão do menu lateral: ainda não tem efeito (a edição será implementada depois).
    def on_apply_task(self):
        pass

    def on_save(self):
        if len(self.shapes) == 0:
            messagebox.showinfo("Salvar imagem", "Execute uma simulação antes de salvar a imagem.")
            return
        path = filedialog.asksaveasfilename(title="Salvar gráfico de Gantt", defaultextension=".svg",
                                            filetypes=[("SVG", "*.svg")])
        if path:
            save_svg(self.shapes, self.chart_width, self.chart_height, path)

    # ---------- Desenho ----------

    # Converte cada Shape para o comando equivalente do Canvas do Tkinter
    def draw_shapes(self):
        self.canvas.delete("all")

        for s in self.shapes:
            if s.kind == "rect":
                self.canvas.create_rectangle(s.x1, s.y1, s.x2, s.y2, fill=s.fill, outline=s.outline,
                                             tags=tags_for(s))

            elif s.kind == "line":
                self.canvas.create_line(s.x1, s.y1, s.x2, s.y2, fill=s.outline, width=s.width)

            elif s.kind == "polygon":
                self.canvas.create_polygon(s.points, fill=s.fill, outline=s.outline)

            elif s.kind == "text":
                # Nomes de âncora do Tkinter: "w" = esquerda, "center" = meio, "e" = direita
                anchors = {"start": "w", "middle": "center", "end": "e"}
                # Tamanho negativo na fonte = tamanho em pixels (igual ao do SVG)
                self.canvas.create_text(s.x1, s.y1, text=s.text, fill=s.fill,
                                        anchor=anchors[s.anchor], font=("Helvetica", -s.size),
                                        tags=tags_for(s))

        self.canvas.configure(scrollregion=(0, 0, self.chart_width, self.chart_height))
        # Todo item marcado com a etiqueta "task" responde ao clique do mouse
        self.canvas.tag_bind("task", "<Button-1>", self.on_task_click)
        self.canvas.tag_bind("task", "<Enter>", lambda event: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind("task", "<Leave>", lambda event: self.canvas.configure(cursor=""))

    # ---------- Seleção de tarefa ----------

    # Descobre qual tarefa foi clicada olhando as etiquetas (task1, task2, ...) do item
    def on_task_click(self, event):
        items = self.canvas.find_withtag("current")
        if len(items) == 0:
            return
        for tag in self.canvas.gettags(items[0]):
            if tag.startswith("task") and tag[4:].isdigit():
                self.select_task(int(tag[4:]))
                return

    # Seleciona uma tarefa (0 = nenhuma): destaca a linha e preenche o menu lateral
    def select_task(self, task_id):
        self.selected_task_id = task_id

        # volta todos os fundos para branco e pinta o da tarefa escolhida
        self.canvas.itemconfigure("rowbg", fill="#ffffff", outline="#ffffff")
        if task_id > 0:
            self.canvas.itemconfigure(f"rowbg{task_id}", fill="#fff3c4", outline="#e0a800")

        for entry in self.entries.values():
            entry.delete(0, "end")

        if task_id == 0:
            self.panel_title.configure(text="Nenhuma tarefa selecionada")
            self.panel_hint.configure(text="Clique em uma tarefa no gráfico.")
            self.set_status_text("")
            return

        info = None
        for candidate in self.result.tasks:
            if candidate.id == task_id:
                info = candidate

        self.panel_title.configure(text=f"Tarefa {task_id}")
        self.panel_hint.configure(text="Situação ao final da simulação.")

        lines = ""
        for name, value in make_task_status(self.result, task_id):
            lines += f"{name}: {value}\n"
        self.set_status_text(lines.strip())

        self.entries["color"].insert(0, info.color)
        self.entries["arrival"].insert(0, str(info.arrival))
        self.entries["duration"].insert(0, str(info.duration))
        self.entries["period"].insert(0, str(info.period))
        self.entries["deadline"].insert(0, str(info.deadline))
        self.entries["events"].insert(0, str(info.events))

    def set_status_text(self, message):
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", message)
        self.status_text.configure(state="disabled")

    def show_message(self, message):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", message)
        self.text.configure(state="disabled")

    def run(self):
        self.root.mainloop()


# Etiquetas do Canvas para uma forma: "task" + "task<id>" fazem o clique funcionar;
# "rowbg" + "rowbg<id>" marcam o fundo da linha (usado para destacar a seleção).
def tags_for(shape):
    if shape.task_id == 0:
        return ()
    tags = ("task", f"task{shape.task_id}")
    if shape.is_background:
        tags = tags + ("rowbg", f"rowbg{shape.task_id}")
    return tags


# Devolve só as últimas linhas (não vazias) de um texto
def last_lines(text, count):
    lines = []
    for line in text.split("\n"):
        if line.strip():
            lines.append(line)
    return "\n".join(lines[-count:])


def run_gui(simulate, config_path, output_dir):
    window = SimulatorWindow(simulate, config_path, output_dir)
    window.run()
