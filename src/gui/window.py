"""Interface Tkinter para execução, inspeção e edição atômica da simulação."""
import os
import tkinter
import traceback
from tkinter import filedialog, messagebox, ttk

from gui.gantt import build_gantt
from gui.report import make_report, make_task_status
from gui.svg_export import save_svg


# Janela principal do simulador.
#
# A janela recebe callbacks do main.py e o histórico compartilhado.
# O core continua sem depender do Tkinter ou das rotinas de desenho.
class SimulatorWindow:
    def __init__(self, engine, config_path, output_dir):
        # engine é o Simulator: guarda o histórico e faz avançar, voltar e editar
        self.engine = engine
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
        self.task_state_dirty = False
        # O foco em um campo pausa a execução para não sobrescrever a digitação.
        self.entries = {}

        self.root = tkinter.Tk()
        self.root.report_callback_exception = self.on_callback_error
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

    # Monta controles de execução e configuração com valores preenchidos pelo estado.
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
            field_label = tkinter.Label(settings, text=label)
            field_label.pack(side="left", padx=(0, 5))
            if key == 'algorithm':
                self.algorithm_label = field_label
            entry = tkinter.Entry(settings, width=width)
            entry.pack(side="left", padx=(0, 12))
            entry.bind("<FocusIn>", self.on_edit_focus)
            entry.bind("<KeyPress>", self.on_edit_focus)
            self.system_entries[key] = entry
        self.apply_system_button = tkinter.Button(settings, text="Aplicar sistema", command=self.on_apply_system)
        self.apply_system_button.pack(side="left")
        tkinter.Button(settings, text="Nova tarefa...", command=self.on_add_task).pack(side="left", padx=(8, 0))
        self.remove_task_button = tkinter.Button(settings, text="Remover tarefa", command=self.on_remove_task,
                                                 state="disabled")
        self.remove_task_button.pack(side="left", padx=(6, 0))

    # Monta o Gantt rolável e o painel lateral sem limitar o tamanho da exportação.
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

    # Erros inesperados de callbacks também são visíveis no aplicativo empacotado.
    def on_callback_error(self, error_type, error, trace):
        self.is_running = False
        self.update_controls()
        traceback.print_exception(error_type, error, trace)
        messagebox.showerror('Erro no simulador', str(error))

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
        self.edit_hint = tkinter.Label(footer, text="Consulta: instância mais antiga não concluída. "
                                       "Edições valem para todas as instâncias ativas e futuras.",
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
        self.status_text = tkinter.Text(panel, height=10, width=36, state="disabled", borderwidth=0,
                                        background=panel.cget("background"), font=("Helvetica", 10),
                                        wrap="none")
        self.status_text.pack(side="top", fill="x", padx=8)
        status_scroll = tkinter.Scrollbar(panel, orient='horizontal', command=self.status_text.xview)
        self.status_text.configure(xscrollcommand=status_scroll.set)
        status_scroll.pack(side='top', fill='x', padx=8)

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
        self.task_state.bind("<<ComboboxSelected>>", self.on_task_state_selected)

    # Mostra relatório e log associados ao instante atualmente exibido.
    def build_text_area(self):
        frame = tkinter.Frame(self.root)
        frame.pack(side="bottom", fill="x", padx=6, pady=6)

        self.text = tkinter.Text(frame, height=7, state="disabled", font=("Consolas", 10), wrap="word")
        scroll = tkinter.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="x", expand=True)

    # ---------- Ações dos botões ----------

    # Carrega outro sistema e reinicia seu histórico a partir do instante zero.
    def on_open(self):
        if self.is_running:
            return
        path = filedialog.askopenfilename(title="Escolha o arquivo de configuração",
                                          filetypes=[("Texto", "*.txt"), ("Todos os arquivos", "*")])
        if path:
            self.config_path = path
            self.path_label.configure(text=path)
            self.engine.reset()
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

    # Carrega a configuração uma única vez e exibe erros de entrada ao usuário.
    def ensure_started(self):
        if self.engine.is_loaded():
            return True
        try:
            self.engine.load(self.config_path)
        except ValueError as error:
            self.show_message(str(error))
            messagebox.showerror("Erro na simulação", last_lines(str(error), 3))
            return False
        self.draw_state(self.engine.current())
        self.update_controls()
        return True

    # Agenda execução automática, preservando histórico e apresentação final única.
    def on_run(self):
        if self.is_running or not self.ensure_started() or self.engine.current().is_finished:
            return
        if self.engine.current().is_blocked:
            self.show_message(self.state_message(self.engine.current()))
            return
        self.is_running = True
        self.update_controls()
        # Cada callback executa um tick. O Tkinter pode redesenhar entre os passos.
        self.after_id = self.root.after(0, self.run_next_step)

    # Cancela o próximo callback e exibe o instante alcançado para inspeção.
    def on_pause(self):
        was_running = self.is_running
        self.is_running = False
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        if was_running and self.engine.is_loaded():
            self.draw_state(self.engine.current())
        self.update_controls()

    # Pausa antes da digitação para que o desenho não sobrescreva os campos.
    def on_edit_focus(self, event=None):
        if self.is_running:
            self.on_pause()

    # Executa um tick automático e agenda outro sem redesenhar o Gantt intermediário.
    def run_next_step(self):
        self.after_id = None
        if not self.is_running:
            return
        self.advance()
        if self.is_running:
            self.after_id = self.root.after(1, self.run_next_step)

    # Compartilha a transição entre os modos manual e completo, tratando término/bloqueio.
    def advance(self, render=True):
        next_state = self.engine.step_forward()
        if render:
            self.draw_state(next_state)
        if next_state.is_finished:
            self.is_running = False
            if not render:
                self.draw_state(next_state)
            self.finish_simulation()
        elif next_state.is_blocked:
            self.is_running = False
            if not render:
                self.draw_state(next_state)
        self.update_controls()

    # Executa um único intervalo e mostra seu resultado no modo manual.
    def on_step_forward(self):
        if self.is_running or not self.ensure_started():
            return
        if not self.engine.current().is_finished:
            self.advance()

    # Descarta o futuro mais recente e volta ao retrato anterior sem recalculá-lo.
    def on_step_back(self):
        if self.is_running or not self.engine.is_loaded() or not self.engine.can_step_back():
            return
        self.draw_state(self.engine.step_back())
        self.update_controls()

    # Habilita apenas operações coerentes com execução, bloqueio e limites do histórico.
    def update_controls(self):
        loaded = self.engine.is_loaded()
        finished = loaded and self.engine.current().is_finished
        can_advance = not self.is_running and not finished
        blocked = loaded and self.engine.current().is_blocked
        self.open_button.configure(state="disabled" if self.is_running else "normal")
        self.run_button.configure(state="normal" if can_advance and not blocked else "disabled")
        self.pause_button.configure(state="normal" if self.is_running else "disabled")
        self.forward_button.configure(state="normal" if can_advance else "disabled")
        self.back_button.configure(state="normal" if not self.is_running and loaded and self.engine.can_step_back()
                                   else "disabled")

    # Compõe o relatório e o log exclusivos do estado atual.
    def state_message(self, state):
        status = ("concluída" if state.is_finished else "aguardando retomada de tarefa suspensa"
                  if state.is_blocked else "em andamento")
        return (f"Instante atual: {state.tick} | Simulação {status}\n\n"
                + make_report(state.result) + "\n\n--- Log da simulação ---\n" + "\n".join(state.log))

    # Atualiza gráfico, seleção e campos a partir do mesmo retrato consistente.
    def draw_state(self, state):
        # Ao voltar para um instante em que a tarefa selecionada ainda não existia, tira a seleção.
        if self.selected_task_id not in [info.id for info in state.result.tasks]:
            self.selected_task_id = 0
        self.result = state.result
        self.shapes, self.chart_width, self.chart_height = build_gantt(self.result)
        self.draw_shapes()
        self.select_task(self.selected_task_id)
        self.algorithm_label.configure(text='Algoritmo (' + ' / '.join(state.algorithm_options).lower() + ')')
        for key, entry in self.system_entries.items():
            entry.delete(0, "end")
            value = state.algorithm if key == "algorithm" else len(state.processors_list)
            entry.insert(0, str(value))
        self.root.title(f"Simulador de Escalonamento - instante {state.tick}")
        self.show_message(self.state_message(state))

    # Salva a imagem final e informa falhas de gravação sem perder o estado.
    def finish_simulation(self):
        # A imagem final também é gerada quando o último tick é alcançado manualmente.
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            image_path = os.path.join(self.output_dir, "gantt.svg")
            save_svg(self.shapes, self.chart_width, self.chart_height, image_path)
        except OSError as error:
            messagebox.showerror("Erro ao salvar imagem", str(error))
            return
        self.show_message(self.state_message(self.engine.current()) + "\n\nImagem salva em: " + image_path)

    # Substitui o retrato atual somente após validar toda a edição.
    def apply_edit(self, **changes):
        self.on_pause()
        if not self.ensure_started():
            return
        try:
            edited = self.engine.edit(**changes)
        except ValueError as error:
            messagebox.showerror("Alteração inválida", str(error))
            return False
        # Editar não cria um novo tick: o engine substitui somente o estado atual.
        self.draw_state(edited)
        self.update_controls()
        if edited.is_finished:
            self.finish_simulation()
        return True

    # Valores iniciais do formulário de nova tarefa: o próximo ID livre e a primeira cor não usada.
    def default_new_task(self, state):
        used_colors = {info.color for info in state.result.tasks}
        color = ""
        for value in range(1, 0x1000000):
            candidate = f"{value:06X}"
            if candidate not in used_colors:
                color = candidate
                break
        return dict(id=max((info.id for info in state.result.tasks), default=0) + 1, color=color,
                    arrival=state.tick, duration=1, period=4, deadline=4, events="[]")

    # Formulário de inclusão: a nova tarefa passa a pertencer ao retrato atual.
    def on_add_task(self):
        self.on_pause()
        if not self.ensure_started():
            return
        values = self.default_new_task(self.engine.current())

        dialog = tkinter.Toplevel(self.root)
        dialog.title("Nova tarefa periódica")
        dialog.transient(self.root)
        dialog.grab_set()

        labels = (('id', 'Identificador'), ('color', 'Cor RGB'), ('arrival', 'Ingresso'),
                  ('duration', 'Duração'), ('period', 'Período'), ('deadline', 'Prazo'), ('events', 'Eventos'))
        fields = {}
        for row, (key, label) in enumerate(labels):
            tkinter.Label(dialog, text=label).grid(row=row, column=0, sticky='w', padx=12, pady=5)
            entry = tkinter.Entry(dialog, width=28)
            entry.insert(0, str(values[key]))
            entry.grid(row=row, column=1, padx=12, pady=5)
            fields[key] = entry

        # Inclui os campos validados e só fecha o diálogo se a edição for aceita.
        def add():
            if self.apply_edit(add_task={key: entry.get() for key, entry in fields.items()}):
                self.select_task(int(fields['id'].get()))
                dialog.destroy()

        tkinter.Button(dialog, text="Incluir tarefa", command=add).grid(row=len(labels), column=0, columnspan=2, pady=12)
        # Referências também permitem validar o formulário com Tkinter real.
        self.add_task_dialog = dialog
        self.add_task_fields = fields
        self.add_task_submit = add

    # Cancela a definição selecionada preservando dados e desenhos históricos.
    def on_remove_task(self):
        if not self.selected_task_id:
            messagebox.showinfo("Remover tarefa", "Selecione uma tarefa no gráfico.")
            return
        self.apply_edit(remove_task_id=self.selected_task_id)

    # Encaminha os campos de algoritmo e quantidade de CPUs para edição atômica.
    def on_apply_system(self):
        self.apply_edit(algorithm=self.system_entries["algorithm"].get(),
                        num_cpus=self.system_entries["num_cpus"].get())

    # Aplica atributos à família; só uma escolha explícita muda o estado global.
    def on_apply_task(self):
        if not self.selected_task_id:
            messagebox.showinfo("Edição de tarefas", "Selecione uma tarefa no gráfico antes de editar.")
            return
        selected_state = self.task_state.get()
        current_state = self.engine.current().current_task(self.selected_task_id)[1]
        # Digitar uma cor não deve também mandar executar todas as instâncias
        # só porque a mais antiga, usada na consulta, está Executando.
        state_change = selected_state if self.task_state_dirty or selected_state != current_state else None
        self.apply_edit(task_id=self.selected_task_id,
                        changes={key: entry.get() for key, entry in self.entries.items()},
                        task_state=state_change)

    # Distingue a escolha de estado de uma simples edição de atributos.
    def on_task_state_selected(self, event=None):
        selected_state = self.task_state.get()
        self.on_edit_focus(event)
        self.task_state.set(selected_state)
        self.task_state_dirty = True

    # Exporta em destino escolhido e transforma falhas de I/O em aviso na interface.
    def on_save(self):
        if len(self.shapes) == 0:
            messagebox.showinfo("Salvar imagem", "Execute uma simulação antes de salvar a imagem.")
            return
        path = filedialog.asksaveasfilename(title="Salvar gráfico de Gantt", defaultextension=".svg",
                                            filetypes=[("SVG", "*.svg")])
        if path:
            try:
                save_svg(self.shapes, self.chart_width, self.chart_height, path)
            except OSError as error:
                messagebox.showerror("Erro ao salvar imagem", str(error))

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

    # Preenche (ou limpa) os campos de edição e liga/desliga os botões conforme a tarefa seja editável.
    def fill_task_form(self, info, state_name):
        editable = info is not None and state_name != 'Removida'
        for key, entry in self.entries.items():
            entry.configure(state="normal")
            entry.delete(0, "end")
            if info is not None:
                entry.insert(0, str(getattr(info, key)))
            entry.configure(state="normal" if editable else "disabled")
        self.task_state.set(state_name)
        self.task_state.configure(state="readonly" if editable else "disabled")
        self.apply_task_button.configure(state="normal" if editable else "disabled")
        self.remove_task_button.configure(state="normal" if editable else "disabled")

    # Mostra no menu lateral a situação da tarefa selecionada.
    def show_task_status(self, task_id, info, state_name):
        self.panel_title.configure(text=f"Tarefa {task_id}")
        hint = f"Instância {info.instance_number} | instante {self.result.total_ticks}"
        if state_name == 'Nova' and info.starts_suspended:
            hint += "\nEntrará suspensa no ingresso."
        self.panel_hint.configure(text=hint)

        cpu = str(info.processor.id) if info.processor else 'nenhuma'
        lines = (f"Estado: {state_name}\nExecutado nesta instância: {info.computational_time}/{info.duration}\n"
                 f"Prazo absoluto: {info.absolute_deadline}\nAtrasada: {'sim' if info.is_late else 'não'} | CPU atual: {cpu}\n")
        for name, value in make_task_status(self.result, task_id):
            lines += f"{name}: {value}\n"
        self.set_status_text(lines.strip())

    # Seleciona uma tarefa (0 = nenhuma): destaca a linha e preenche o menu lateral
    def select_task(self, task_id):
        self.selected_task_id = task_id
        self.task_state_dirty = False

        # volta todos os fundos para branco e pinta o da tarefa escolhida
        self.canvas.itemconfigure("rowbg", fill="#ffffff", outline="#ffffff")
        if task_id > 0:
            self.canvas.itemconfigure(f"rowbg{task_id}", fill="#fff3c4", outline="#e0a800")

        info = None
        state_name = ""
        if self.result is not None and task_id:
            info, state_name = self.engine.current().current_task(task_id)
        self.fill_task_form(info, state_name)

        if info is None:
            self.selected_task_id = 0
            self.panel_title.configure(text="Nenhuma tarefa selecionada")
            self.panel_hint.configure(text="Clique em uma tarefa no gráfico.")
            self.set_status_text("")
            return
        self.show_task_status(task_id, info, state_name)

    # Atualiza o texto de consulta sem permitir edição acidental do diagnóstico.
    def set_status_text(self, message):
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", message)
        self.status_text.configure(state="disabled")

    # Atualiza relatório/log mantendo a área somente para leitura.
    def show_message(self, message):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", message)
        self.text.configure(state="disabled")

    # Entrega o controle de eventos à janela principal do Tkinter.
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


# Liga os callbacks do programa à janela e inicia sua interação.
def run_gui(engine, config_path, output_dir):
    window = SimulatorWindow(engine, config_path, output_dir)
    window.run()
