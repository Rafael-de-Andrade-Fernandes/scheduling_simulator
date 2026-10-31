import os
import tkinter
from tkinter import filedialog, messagebox, ttk

from gui.gantt import build_gantt, tick_x
from gui.report import make_report, make_task_status
from gui.svg_export import save_svg


# Janela principal do simulador.
#
# Esta parte NÃO conhece o core da simulação. Ela recebe do main.py um objeto "engine"
# com estes métodos (o core fornece a classe que os implementa):
#     load(caminho)                 -> (ok, texto)
#     step_forward() / step_back()  -> "" se deu certo, senão o motivo
#     run_to_end()                  -> "" se deu certo, senão o motivo
#     edit_task(id, valores)        -> (ok, mensagem)
#     set_algorithm(nome)           -> (ok, mensagem)
#     set_num_cpus(quantidade)      -> (ok, mensagem)
#     view()                        -> dados do estado atual (somente leitura)
# Assim o core e a janela ficam separados.
class SimulatorWindow:
    def __init__(self, engine, config_path, output_dir):
        self.engine = engine
        self.config_path = config_path
        self.output_dir = output_dir
        # Último gráfico desenhado (guardado para o botão "Salvar imagem")
        self.shapes = []
        self.chart_width = 0
        self.chart_height = 0
        # Estado atual da simulação (vindo do engine.view()) e tarefa selecionada (0 = nenhuma)
        self.result = None
        self.selected_task_id = 0
        # Campos editáveis do menu lateral: nome do campo -> caixa de texto
        self.entries = {}

        self.root = tkinter.Tk()
        self.root.title("Simulador de Escalonamento")
        self.root.geometry("1150x880")

        self.build_toolbar()
        self.build_message_bar()
        self.build_canvas()
        self.build_text_area()

        # Setas do teclado = voltar / avançar um passo
        self.root.bind("<Left>", self.on_key_left)
        self.root.bind("<Right>", self.on_key_right)

        self.show_text("Escolha um arquivo de configuração e clique em \"Executar simulação completa\" "
                       "ou em \"Iniciar passo a passo\".")

    # ---------- Montagem da janela ----------

    def build_toolbar(self):
        # Linha 1: arquivo de configuração
        row1 = tkinter.Frame(self.root)
        row1.pack(side="top", fill="x", padx=6, pady=(6, 0))
        tkinter.Button(row1, text="Abrir configuração...", command=self.on_open).pack(side="left")
        self.path_label = tkinter.Label(row1, text=self.config_path, anchor="w")
        self.path_label.pack(side="left", padx=10)

        # Linha 2: controle da simulação
        row2 = tkinter.Frame(self.root)
        row2.pack(side="top", fill="x", padx=6, pady=6)
        tkinter.Button(row2, text="Executar simulação completa", command=self.on_run).pack(side="left")
        tkinter.Button(row2, text="Iniciar passo a passo", command=self.on_start_steps).pack(side="left", padx=6)
        tkinter.Button(row2, text="<< Voltar", command=self.on_step_back).pack(side="left")
        tkinter.Button(row2, text="Passo >>", command=self.on_step_forward).pack(side="left", padx=6)
        tkinter.Button(row2, text="Salvar imagem (SVG)...", command=self.on_save).pack(side="left")

        # Linha 3: parâmetros do sistema (podem mudar durante a simulação)
        row3 = tkinter.Frame(self.root)
        row3.pack(side="top", fill="x", padx=6)
        tkinter.Label(row3, text="Algoritmo:").pack(side="left")
        self.algorithm_var = tkinter.StringVar()
        self.algorithm_box = ttk.Combobox(row3, textvariable=self.algorithm_var, width=8, state="readonly")
        self.algorithm_box.pack(side="left", padx=(4, 12))
        tkinter.Label(row3, text="Processadores:").pack(side="left")
        self.cpu_var = tkinter.StringVar(value="1")
        tkinter.Spinbox(row3, from_=1, to=64, width=4, textvariable=self.cpu_var).pack(side="left", padx=(4, 12))
        tkinter.Button(row3, text="Aplicar sistema", command=self.on_apply_system).pack(side="left")

    # Linha de mensagens: mostra o resultado da última ação (vermelho = recusada)
    def build_message_bar(self):
        self.message_label = tkinter.Label(self.root, text="", anchor="w", justify="left", wraplength=1100)
        self.message_label.pack(side="top", fill="x", padx=6, pady=(4, 0))

    def build_canvas(self):
        middle = tkinter.Frame(self.root)
        middle.pack(side="top", fill="both", expand=True, padx=6, pady=(4, 0))

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

        tkinter.Label(panel, text="Situação no tick atual", anchor="w", font=("Helvetica", 10, "bold")).pack(
            side="top", fill="x", padx=8, pady=(8, 0))
        self.status_text = tkinter.Text(panel, height=9, width=34, state="disabled", borderwidth=0,
                                        background=panel.cget("background"))
        self.status_text.pack(side="top", fill="x", padx=8)

        tkinter.Label(panel, text="Características e estado (editáveis)", anchor="w",
                      font=("Helvetica", 10, "bold")).pack(side="top", fill="x", padx=8, pady=(8, 2))

        form = tkinter.Frame(panel)
        form.pack(side="top", fill="x", padx=8)
        field_names = [("color", "Cor (RGB hex)"), ("arrival", "Ingresso"), ("duration", "Duração"),
                       ("period", "Período"), ("deadline", "Prazo"), ("executed", "Já executado"),
                       ("events", "Eventos (projeto B)")]
        for row in range(len(field_names)):
            key = field_names[row][0]
            tkinter.Label(form, text=field_names[row][1], anchor="w").grid(row=row, column=0, sticky="w", pady=1)
            entry = tkinter.Entry(form, width=16)
            entry.grid(row=row, column=1, sticky="e", pady=1, padx=(6, 0))
            self.entries[key] = entry

        tkinter.Button(panel, text="Aplicar alterações", command=self.on_apply_task).pack(side="top", pady=8)
        tkinter.Label(panel, text="A mudança vale a partir do tick atual. Se for inválida, "
                                  "é recusada e o motivo aparece acima do gráfico.",
                      wraplength=260, justify="left", foreground="#555555").pack(side="top", padx=8)

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

    # Lê o arquivo de configuração e começa uma simulação no tick 0.
    # Devolve False (e mostra o erro) se o arquivo for inválido.
    def load_simulation(self):
        ok, text = self.engine.load(self.config_path)
        if not ok:
            self.show_text(text)
            self.set_message("Não foi possível carregar a configuração. Veja o motivo no quadro abaixo.", True)
            messagebox.showerror("Erro na configuração", last_lines(text, 3))
        return ok

    # Execução completa (modo b): simula tudo até o fim
    def on_run(self):
        if self.load_simulation():
            message = self.engine.run_to_end()
            self.selected_task_id = 0
            self.refresh(message, message != "")

    # Passo a passo (modo a): carrega e para no tick 0
    def on_start_steps(self):
        if self.load_simulation():
            self.selected_task_id = 0
            self.refresh("Simulação iniciada no tick 0. Use \"Passo >>\" e \"<< Voltar\" "
                         "(ou as setas do teclado).", False)

    def on_step_forward(self):
        message = self.engine.step_forward()
        self.refresh(message, message != "")

    def on_step_back(self):
        message = self.engine.step_back()
        self.refresh(message, message != "")

    # As setas só funcionam como atalho quando o cursor não está digitando em um campo
    def on_key_left(self, event):
        if not self.typing_in_field():
            self.on_step_back()

    def on_key_right(self, event):
        if not self.typing_in_field():
            self.on_step_forward()

    def typing_in_field(self):
        try:
            focus = self.root.focus_get()
        except KeyError:
            return False
        return isinstance(focus, (tkinter.Entry, tkinter.Spinbox, ttk.Combobox))

    # Botão do menu lateral: modifica a tarefa selecionada no tick atual
    def on_apply_task(self):
        if self.selected_task_id == 0:
            self.set_message("Selecione uma tarefa no gráfico antes de aplicar alterações.", True)
            return

        values = {}
        for key in ["color", "arrival", "duration", "period", "deadline", "executed"]:
            values[key] = self.entries[key].get()

        ok, message = self.engine.edit_task(self.selected_task_id, values)
        if ok:
            self.refresh(message, False)
        else:
            # Mantém o que o usuário digitou para ele poder corrigir
            self.set_message(message, True)

    # Botão "Aplicar sistema": troca o algoritmo e/ou a quantidade de processadores
    def on_apply_system(self):
        if self.result is None:
            self.set_message("Carregue uma simulação antes de mudar o sistema.", True)
            return

        messages = []
        all_ok = True

        if self.algorithm_var.get() != self.result.algorithm:
            ok, message = self.engine.set_algorithm(self.algorithm_var.get())
            messages.append(message)
            all_ok = all_ok and ok

        try:
            num_cpus = int(self.cpu_var.get())
        except ValueError:
            num_cpus = 0
        if num_cpus != self.result.num_cpus:
            ok, message = self.engine.set_num_cpus(num_cpus)
            messages.append(message)
            all_ok = all_ok and ok

        if len(messages) == 0:
            messages.append("Nada foi alterado.")
        self.refresh(" ".join(messages), not all_ok)

    def on_save(self):
        if len(self.shapes) == 0:
            messagebox.showinfo("Salvar imagem", "Execute uma simulação antes de salvar a imagem.")
            return
        path = filedialog.asksaveasfilename(title="Salvar gráfico de Gantt", defaultextension=".svg",
                                            filetypes=[("SVG", "*.svg")])
        if path:
            save_svg(self.shapes, self.chart_width, self.chart_height, path)

    # ---------- Atualização da tela ----------

    # Redesenha tudo a partir do estado atual da simulação
    def refresh(self, message="", is_error=False):
        result = self.engine.view()
        if result is None:
            self.set_message(message, is_error)
            return
        self.result = result

        self.shapes, self.chart_width, self.chart_height = build_gantt(result)
        self.draw_shapes()
        self.scroll_to_cursor()

        # Controles do sistema mostram os valores atuais
        self.algorithm_box.configure(values=result.algorithms)
        self.algorithm_var.set(result.algorithm)
        self.cpu_var.set(str(result.num_cpus))

        # Menu lateral continua na mesma tarefa (se ela ainda existir)
        known_ids = [task.id for task in result.tasks]
        if self.selected_task_id not in known_ids:
            self.selected_task_id = 0
        self.select_task(self.selected_task_id)

        self.show_text(make_report(result) + "\n\n--- Log da simulação ---\n" + "\n".join(result.log))

        # O PDF pede que a imagem seja gerada ao final da simulação
        if result.finished:
            os.makedirs(self.output_dir, exist_ok=True)
            image_path = os.path.join(self.output_dir, "gantt.svg")
            save_svg(self.shapes, self.chart_width, self.chart_height, image_path)
            message = (message + " " if message else "") + f"Simulação terminada. Imagem salva em: {image_path}"

        self.set_message(message, is_error)

    def set_message(self, message, is_error):
        color = "#b00020" if is_error else "#1b5e20"
        self.message_label.configure(text=message, foreground=color)

    # Rola o gráfico para o tick atual ficar visível
    def scroll_to_cursor(self):
        self.root.update_idletasks()
        visible_width = self.canvas.winfo_width()
        if self.chart_width <= visible_width:
            return
        x = tick_x(self.result.tick)
        self.canvas.xview_moveto(max(0, (x - visible_width * 0.7) / self.chart_width))

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

        for key in self.entries:
            self.entries[key].configure(state="normal")
            self.entries[key].delete(0, "end")

        if task_id == 0:
            self.panel_title.configure(text="Nenhuma tarefa selecionada")
            self.panel_hint.configure(text="Clique em uma tarefa no gráfico.")
            self.set_status_text("")
            return

        task = None
        for candidate in self.result.tasks:
            if candidate.id == task_id:
                task = candidate

        self.panel_title.configure(text=f"Tarefa {task_id}")
        self.panel_hint.configure(text=f"Estado no tick {self.result.tick}.")

        lines = ""
        for name, value in make_task_status(task):
            lines += f"{name}: {value}\n"
        self.set_status_text(lines.strip())

        self.entries["color"].insert(0, task.color)
        self.entries["arrival"].insert(0, str(task.arrival))
        self.entries["duration"].insert(0, str(task.duration))
        self.entries["period"].insert(0, str(task.period))
        self.entries["deadline"].insert(0, str(task.deadline))
        self.entries["executed"].insert(0, str(task.executed))
        # Eventos só serão tratados no projeto B: o campo é apenas para consulta
        self.entries["events"].insert(0, str(task.events))
        self.entries["events"].configure(state="readonly")

    def set_status_text(self, message):
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", message)
        self.status_text.configure(state="disabled")

    def show_text(self, message):
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


def run_gui(engine, config_path, output_dir):
    window = SimulatorWindow(engine, config_path, output_dir)
    window.run()
