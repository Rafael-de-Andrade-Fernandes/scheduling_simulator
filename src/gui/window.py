import os
import tkinter
from tkinter import filedialog, messagebox, ttk

from gui.gantt import build_gantt
from gui.report import make_report, make_task_status
from gui.svg_export import save_svg


# Janela principal do simulador.
#
# A janela recebe callbacks do main.py e o histórico compartilhado.
# O core continua sem depender do Tkinter ou das rotinas de desenho.
class SimulatorWindow:
    def __init__(self, start_simulation, step_simulation, state_list, config_path, output_dir):
        self.start_simulation = start_simulation
        self.step_simulation = step_simulation
        self.state_list = state_list
        self.is_running = False
        self.after_id = None
        self.config_path = config_path
        self.output_dir = output_dir
        # Último gráfico desenhado (guardado para o botão "Salvar imagem")
        self.shapes = []
        self.chart_width = 0
        self.chart_height = 0
        # Resultado da última simulação e tarefa selecionada (0 = nenhuma)
        self.result = None
        self.selected_task_id = 0
        # O foco em um campo pausa a execução para não sobrescrever a digitação.
        self.entries = {}

        self.root = tkinter.Tk()
        self.root.title("Simulador de Escalonamento")
        width = min(1180, self.root.winfo_screenwidth() - 80)
        height = min(860, self.root.winfo_screenheight() - 80)
        self.root.geometry(f"{width}x{height}")

        self.build_toolbar()
        self.build_canvas()
        self.build_text_area()
        self.show_message("Escolha uma configuração e clique em \"Passo >>\" ou "
                          "\"Completar simulação\".")
        self.update_controls()
        self.ensure_started()

    # ---------- Montagem da janela ----------

    def build_toolbar(self):
        toolbar = tkinter.Frame(self.root)
        toolbar.pack(side="top", fill="x", padx=6, pady=6)

        self.open_button = tkinter.Button(toolbar, text="Abrir configuração...", command=self.on_open)
        self.open_button.pack(side="left")
        self.run_button = tkinter.Button(toolbar, text="Completar simulação", command=self.on_run)
        self.run_button.pack(side="left", padx=6)
        self.pause_button = tkinter.Button(toolbar, text="Pausar", command=self.on_pause)
        self.pause_button.pack(side="left", padx=(0, 6))
        self.back_button = tkinter.Button(toolbar, text="<< Voltar", command=self.on_step_back)
        self.back_button.pack(side="left")
        self.forward_button = tkinter.Button(toolbar, text="Passo >>", command=self.on_step_forward)
        self.forward_button.pack(side="left", padx=6)
        tkinter.Button(toolbar, text="Salvar imagem (SVG)...", command=self.on_save).pack(side="left")

        self.path_label = tkinter.Label(toolbar, text=self.config_path, anchor="w")
        self.path_label.pack(side="left", padx=10)

        settings = tkinter.Frame(self.root)
        settings.pack(side="top", fill="x", padx=6, pady=(0, 6))
        self.system_entries = {}
        for key, label, width in (("algorithm", "Algoritmo (rm / edf)", 8),
                                  ("num_cpus", "Processadores", 6)):
            tkinter.Label(settings, text=label).pack(side="left", padx=(0, 5))
            entry = tkinter.Entry(settings, width=width)
            entry.pack(side="left", padx=(0, 12))
            entry.bind("<FocusIn>", self.on_edit_focus)
            entry.bind("<KeyPress>", self.on_edit_focus)
            self.system_entries[key] = entry
        self.apply_system_button = tkinter.Button(settings, text="Aplicar sistema", command=self.on_apply_system)
        self.apply_system_button.pack(side="left")
        tkinter.Label(settings, text="Editar pausa a execução; aplicar mantém o instante atual.").pack(side="left", padx=12)

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

    # Menu lateral: mostra a situação e as características da tarefa clicada
    def build_side_panel(self, parent):
        outer = tkinter.Frame(parent, width=320, borderwidth=1, relief="groove")
        outer.pack(side="right", fill="y", padx=(6, 0))
        outer.pack_propagate(False)

        # O botão permanece acessível mesmo em telas pequenas ou com DPI alto.
        footer = tkinter.Frame(outer)
        footer.pack(side="bottom", fill="x")
        self.apply_task_button = tkinter.Button(footer, text="Aplicar alterações", command=self.on_apply_task,
                                                state="disabled")
        self.apply_task_button.pack(side="top", pady=(8, 4))
        self.edit_hint = tkinter.Label(footer, text="Instância mais antiga não concluída. "
                                       "Características valem para instâncias não concluídas e futuras.",
                                       wraplength=290, justify="left", font=("Helvetica", 9))
        self.edit_hint.pack(side="top", padx=8, pady=(0, 6))

        self.side_canvas = tkinter.Canvas(outer, highlightthickness=0,
                                          background=outer.cget("background"))
        scroll = tkinter.Scrollbar(outer, orient="vertical", command=self.side_canvas.yview)
        self.side_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.side_canvas.pack(side="left", fill="both", expand=True)
        panel = tkinter.Frame(self.side_canvas)
        panel_id = self.side_canvas.create_window((0, 0), window=panel, anchor="nw")
        panel.bind("<Configure>", lambda event: self.side_canvas.configure(
            scrollregion=self.side_canvas.bbox("all")))
        self.side_canvas.bind("<Configure>", lambda event: self.side_canvas.itemconfigure(
            panel_id, width=event.width))

        self.panel_title = tkinter.Label(panel, text="Nenhuma tarefa selecionada",
                                         font=("Helvetica", 12, "bold"))
        self.panel_title.pack(side="top", pady=(8, 2))
        self.panel_hint = tkinter.Label(panel, text="Clique em uma tarefa no gráfico.",
                                        wraplength=260, justify="left")
        self.panel_hint.pack(side="top")

        tkinter.Label(panel, text="Situação", anchor="w", font=("Helvetica", 10, "bold")).pack(
            side="top", fill="x", padx=8, pady=(10, 0))
        self.status_text = tkinter.Text(panel, height=7, width=36, state="disabled", borderwidth=0,
                                        background=panel.cget("background"), font=("Helvetica", 10),
                                        wrap="none")
        self.status_text.pack(side="top", fill="x", padx=8)

        tkinter.Label(panel, text="Características", anchor="w",
                      font=("Helvetica", 10, "bold")).pack(side="top", fill="x", padx=8, pady=(10, 2))

        form = tkinter.Frame(panel)
        form.pack(side="top", fill="x", padx=8)
        field_names = [("color", "Cor (RGB hex)"), ("arrival", "Ingresso"), ("duration", "Duração"),
                       ("period", "Período"), ("deadline", "Prazo"), ("events", "Eventos")]
        for row, (key, label) in enumerate(field_names, start=1):
            tkinter.Label(form, text=label, anchor="w").grid(row=row, column=0, sticky="w", pady=2)
            entry = tkinter.Entry(form, width=18, state="disabled")
            entry.grid(row=row, column=1, sticky="e", pady=2, padx=(6, 0))
            self.entries[key] = entry
            entry.bind("<FocusIn>", self.on_edit_focus)
            entry.bind("<KeyPress>", self.on_edit_focus)

        tkinter.Label(form, text="Estado", anchor="w").grid(row=0, column=0, sticky="w", pady=2)
        self.task_state = ttk.Combobox(form, width=16, state="disabled",
                                      values=("Nova", "Pronta", "Executando", "Suspensa", "Finalizada"))
        self.task_state.grid(row=0, column=1, sticky="e", pady=2, padx=(6, 0))
        self.task_state.bind("<FocusIn>", self.on_edit_focus)
        self.task_state.bind("<<ComboboxSelected>>", self.on_edit_focus)

    def build_text_area(self):
        frame = tkinter.Frame(self.root)
        frame.pack(side="bottom", fill="x", padx=6, pady=6)

        self.text = tkinter.Text(frame, height=7, state="disabled", font=("Consolas", 10), wrap="word")
        scroll = tkinter.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="x", expand=True)

    # ---------- Ações dos botões ----------

    def on_open(self):
        if self.is_running:
            return
        path = filedialog.askopenfilename(title="Escolha o arquivo de configuração",
                                          filetypes=[("Texto", "*.txt"), ("Todos os arquivos", "*")])
        if path:
            self.config_path = path
            self.path_label.configure(text=path)
            self.state_list.clear()
            self.result = None
            self.shapes = []
            self.chart_width = 0
            self.chart_height = 0
            self.canvas.delete("all")
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            self.select_task(0)
            self.show_message("Configuração carregada. Clique em \"Passo >>\" ou "
                              "\"Completar simulação\".")
            self.update_controls()
            self.ensure_started()

    def ensure_started(self):
        if self.state_list:
            return True
        state, log = self.start_simulation(self.config_path)
        if state is None:
            self.show_message(log)
            messagebox.showerror("Erro na simulação", last_lines(log, 3))
            return False
        self.draw_state(state)
        self.update_controls()
        return True

    def on_run(self):
        if self.is_running or not self.ensure_started() or self.state_list[-1].is_finished:
            return
        if self.state_list[-1].is_blocked:
            self.show_message(self.state_message(self.state_list[-1]))
            return
        self.is_running = True
        self.update_controls()
        # Cada callback executa um tick. O Tkinter pode redesenhar entre os passos.
        self.after_id = self.root.after(0, self.run_next_step)

    def on_pause(self):
        self.is_running = False
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.update_controls()

    def on_edit_focus(self, event=None):
        if self.is_running:
            self.on_pause()

    def run_next_step(self):
        self.after_id = None
        if not self.is_running:
            return
        self.advance()
        if self.is_running:
            self.after_id = self.root.after(1, self.run_next_step)

    def advance(self):
        current_state = self.state_list[-1]
        next_state = self.step_simulation(current_state)
        self.state_list.append(next_state)
        self.draw_state(next_state)
        if next_state.is_finished:
            self.is_running = False
            self.finish_simulation()
        elif next_state.is_blocked:
            self.is_running = False
        self.update_controls()

    def on_step_forward(self):
        if self.is_running or not self.ensure_started():
            return
        if not self.state_list[-1].is_finished:
            self.advance()

    def on_step_back(self):
        if self.is_running or len(self.state_list) <= 1:
            return
        self.state_list.pop()
        self.draw_state(self.state_list[-1])
        self.update_controls()

    def update_controls(self):
        finished = bool(self.state_list and self.state_list[-1].is_finished)
        can_advance = not self.is_running and not finished
        blocked = bool(self.state_list and self.state_list[-1].is_blocked)
        self.open_button.configure(state="disabled" if self.is_running else "normal")
        self.run_button.configure(state="normal" if can_advance and not blocked else "disabled")
        self.pause_button.configure(state="normal" if self.is_running else "disabled")
        self.forward_button.configure(state="normal" if can_advance else "disabled")
        self.back_button.configure(state="normal" if not self.is_running and len(self.state_list) > 1
                                   else "disabled")

    def state_message(self, state):
        status = ("concluída" if state.is_finished else "aguardando retomada de tarefa suspensa"
                  if state.is_blocked else "em andamento")
        return (f"Instante atual: {state.tick} | Simulação {status}\n\n"
                + make_report(state.result) + "\n\n--- Log da simulação ---\n" + state.log)

    def draw_state(self, state):
        self.result = state.result
        self.shapes, self.chart_width, self.chart_height = build_gantt(self.result)
        self.draw_shapes()
        self.select_task(self.selected_task_id)
        for key, entry in self.system_entries.items():
            entry.delete(0, "end")
            value = state.algorithm if key == "algorithm" else len(state.processors_list)
            entry.insert(0, str(value))
        self.root.title(f"Simulador de Escalonamento - instante {state.tick}")
        self.show_message(self.state_message(state))

    def finish_simulation(self):
        # A imagem final também é gerada quando o último tick é alcançado manualmente.
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            image_path = os.path.join(self.output_dir, "gantt.svg")
            save_svg(self.shapes, self.chart_width, self.chart_height, image_path)
        except OSError as error:
            messagebox.showerror("Erro ao salvar imagem", str(error))
            return
        self.show_message(self.state_message(self.state_list[-1]) + "\n\nImagem salva em: " + image_path)

    def apply_edit(self, **changes):
        self.on_pause()
        if not self.ensure_started():
            return
        try:
            edited = self.state_list[-1].edit(**changes)
        except ValueError as error:
            messagebox.showerror("Alteração inválida", str(error))
            return
        # Editar não cria um novo tick: substitui somente o retrato atual.
        self.state_list[-1] = edited
        self.draw_state(edited)
        self.update_controls()
        if edited.is_finished:
            self.finish_simulation()

    def on_apply_system(self):
        self.apply_edit(algorithm=self.system_entries["algorithm"].get(),
                        num_cpus=self.system_entries["num_cpus"].get())

    def on_apply_task(self):
        if not self.selected_task_id:
            messagebox.showinfo("Edição de tarefas", "Selecione uma tarefa no gráfico antes de editar.")
            return
        self.apply_edit(task_id=self.selected_task_id,
                        changes={key: entry.get() for key, entry in self.entries.items()},
                        task_state=self.task_state.get())

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
                                             stipple="gray25" if s.pattern == "dots" else "",
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

        info = None
        state_name = ""
        if self.result is not None and task_id:
            info, state_name = self.state_list[-1].current_task(task_id)
        for key, entry in self.entries.items():
            entry.configure(state="normal")
            entry.delete(0, "end")
            if info is not None:
                entry.insert(0, str(getattr(info, key)))
            entry.configure(state="normal" if info is not None else "disabled")
        self.task_state.set(state_name)
        self.task_state.configure(state="readonly" if info is not None else "disabled")
        self.apply_task_button.configure(state="normal" if info is not None else "disabled")

        if info is None:
            self.selected_task_id = 0
            self.panel_title.configure(text="Nenhuma tarefa selecionada")
            self.panel_hint.configure(text="Clique em uma tarefa no gráfico.")
            self.set_status_text("")
            return

        self.panel_title.configure(text=f"Tarefa {task_id}")
        self.panel_hint.configure(text=f"Instância {info.instance_number} | instante {self.result.total_ticks}")
        lines = f"Estado: {state_name}\nExecutado nesta instância: {info.computational_time}/{info.duration}\n"
        for name, value in make_task_status(self.result, task_id):
            lines += f"{name}: {value}\n"
        self.set_status_text(lines.strip())

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


def run_gui(start_simulation, step_simulation, state_list, config_path, output_dir):
    window = SimulatorWindow(start_simulation, step_simulation, state_list, config_path, output_dir)
    window.run()
