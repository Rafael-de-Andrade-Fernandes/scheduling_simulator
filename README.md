**Simulador de Escalonamento — Projeto A**

Implementa RM e EDF preemptivos, várias CPUs, Gantt, histórico por tick e edição
durante a simulação. Cada definição periódica libera dez instâncias. O prazo de
cada instância é independente do período: D<P, D=P e D>P são aceitos.

**Executar a distribuição Windows**

Extraia `SimuladorEscalonamento-Windows-x64.zip` e abra `Simulador.exe` dentro da
pasta extraída. Mantenha a pasta `_internal` junto dos executáveis. Python,
Tcl/Tk e as bibliotecas necessárias estão incluídos; não é necessário instalar
Python ou pacotes para usar essa distribuição.

Para executar sem interface:

```powershell
.\SimuladorConsole.exe .\configs\config.txt --console --output-dir .\output
```

O gráfico final será salvo como `gantt.svg`. A pasta de saída pode ser escolhida
com `--output-dir`; a interface também permite salvar em outro local.

**Executar a partir do código-fonte**

É necessário Python com Tkinter. O código e a distribuição foram testados com
Python 3.12; a suíte também é executada no Python 3.15 durante o desenvolvimento.
A aplicação não usa pacotes Python externos.

```powershell
python src/main.py
python src/main.py configs/config.txt --console --output-dir output
```

**Formato do arquivo de configuração**

```text
algoritmo;quantum;quantidade_cpus
id;cor;ingresso;duracao;periodo;prazo;lista_eventos
```

Exemplo com prazo diferente do período:

```text
edf;1;2
1;FF0000;0;5;3;6;[]
2;00FF00;1;1;4;2;[]
```

- Algoritmos e cores não distinguem maiúsculas/minúsculas. UTF-8 com ou sem BOM,
  espaços, linhas vazias e ponto e vírgula final opcional são aceitos.
- IDs são inteiros positivos e não se repetem; cada tarefa tem uma cor RGB
  hexadecimal diferente. Cores já desenhadas ficam reservadas à tarefa original.
- Ingresso é inteiro não negativo; duração, período e prazo são inteiros positivos.
- O número de CPUs deve ser ao menos um. Não há um corte artificial da quantidade
  de tarefas ou do horizonte do gráfico; os recursos físicos continuam finitos.
- Tarefas com período zero são aperiódicas: são ignoradas com aviso no Projeto A.
- Quantum é carregado e validado, mas não altera RM/EDF. A lista de eventos é
  armazenada; execução de mutex, E/S e comunicação pertence ao Projeto B.

**Operação e edição**

`Passo >>` simula o intervalo [t,t+1), preserva um retrato independente e atualiza
o Gantt. `<< Voltar` descarta o último retrato e restaura o anterior. Avançar após
voltar gera novamente o futuro a partir daquele estado, inclusive os sorteios.

`Completar simulação` usa as mesmas transições e guarda o histórico, mas desenha
somente o resultado final. `Pausar`, ou entrar em um campo de edição, exibe o
instante alcançado. Isso permite inspecionar e editar sem sobrescrever a digitação.

Os campos do sistema alteram algoritmo e CPUs. Ao reduzir CPUs ocupadas, as tarefas
deslocadas voltam à fila global de prontos. `Nova tarefa...` inclui uma definição
no instante atual ou no futuro. `Remover tarefa` cancela todas as suas instâncias
restantes; o passado continua visível e o ID não é reutilizado no histórico.
Voltar a um retrato anterior restaura a tarefa removida.

Clique em uma tarefa no gráfico para consultar/editar sua instância atual: a mais
antiga ainda não concluída. Se todas terminaram, mostra-se a última concluída.
Estados: Nova, Pronta, Executando, Suspensa e Finalizada. Uma tarefa removida aparece
como Removida e fica somente para consulta. As edições do menu são globais para
todas as instâncias ativas e para as cópias futuras da tarefa. A instância mais
antiga serve apenas para consulta dos valores e do progresso.

Escolher Suspensa libera as CPUs de todas as instâncias da tarefa e mantém o
progresso individual. As futuras continuam chegando pelo calendário, já suspensas,
até uma retomada global para Pronta ou Executando. Escolher Finalizada encerra
todas as instâncias ativas e cancela as liberações futuras da tarefa. O histórico
das instâncias já concluídas e dos intervalos passados não é reescrito.

O campo `Identificador` também pode ser editado. Ao aplicar um novo ID positivo e
exclusivo, toda a tarefa muda de nome, inclusive suas instâncias futuras. O eixo Y
é reordenado pelo ID atual e mantém as barras/eventos já registrados. Os rótulos
das CPUs conservam o ID usado em cada intervalo, e um marcador S# registra a troca.
IDs antigos ficam reservados à mesma tarefa, que pode voltar a utilizá-los; outra
tarefa não pode assumi-los. Retroceder restaura o ID e a ordem do retrato anterior.

Aplicar uma edição substitui somente o retrato atual, sem avançar o relógio. A
validação é atômica: erros não deixam alterações parciais. O ingresso já registrado
não pode ser reescrito; a duração não pode apagar trabalho executado por nenhuma
instância. Executando exige CPUs livres para todas as instâncias já admitidas;
Novas aguardam o ingresso antes de disputar CPU. Alterar apenas um atributo, como
a cor, preserva os estados atuais. Para desfazer acontecimentos passados, retroceda.
Finalizar manualmente é uma intervenção explícita do debugger; sem intervenção,
cada instância só termina após consumir sua duração.

**Relógio, calendário e escalonamento**

O ingresso da instância k é `ingresso_inicial + (k-1)*periodo`; o prazo absoluto é
`ingresso_da_instancia + prazo`. A sucessora é agendada na admissão, mesmo que a
instância anterior ainda execute. Nem o término nem uma perda de prazo liberam uma
instância fora desse calendário. Uma instância atrasada continua até terminar.

Chegadas, liberações de CPU e edições relevantes disparam o escalonador. Eventos
no mesmo instante são reunidos antes de executar o próximo intervalo. Ticks sem
evento não refazem a seleção. Filas e afinidades de CPU só mudam quando necessário.
Um término em t é consumido pelo despacho antes de executar [t,t+1), sem tick ocioso.

RM escolhe menor período; EDF escolhe menor prazo absoluto. Em empate: quem já
executa, menor prazo relativo, menor ingresso, menor duração e sorteio. O estado
do gerador de sorteios também faz parte do histórico.

**Gráfico e legenda**

Execução usa a cor da tarefa; espera não tem preenchimento; suspensão usa preto
pontilhado. Se instâncias da mesma tarefa se sobrepõem, faixas distintas e rótulos
`P#/I#` identificam processador e instância. Há também linhas separadas por CPU.
`OFF` significa CPU existente sem trabalho; `-` indica CPU que não existia naquele
intervalo. Os IDs decrescem de cima para baixo.

Chegadas, conclusões, perdas de prazo, sorteios e remoções têm símbolos distintos.
Reconfigurações são marcadas por `S#`; as descrições e o instante aparecem abaixo
das CPUs. Cores e quantidade de CPUs de intervalos passados são preservadas.
O SVG é gerado pelas primitivas do gráfico, sem fotografar ou limitar-se à janela.

**Adicionar políticas de escalonamento**

O registro fica em `src/core/choose_task.py`. Uma política de prioridade pode ser
registrada com `register_algorithm('NOME', chave_de_prioridade)`. O carregador, o
estado e a interface reconhecem automaticamente as abreviações registradas.

Políticas mais complexas podem fornecer `selector(candidatas, estado, rng)`,
`tick_event(estado)` e `edit_signature(tarefa)`. O primeiro retorna uma candidata
sem modificar as filas; o segundo sinaliza um evento específico, como quantum;
o terceiro informa quais mudanças de dados afetam a decisão. RM/EDF não registram
evento de quantum. A aplicação das trocas e a afinidade de CPU continuam no núcleo.

**Estrutura e testes**

- `src/core/`: TCBs, CPUs, registro de algoritmos, leitura/validação, calendário e estados.
- `src/gui/`: interface Tkinter, primitivas do Gantt, relatório e exportação SVG.
- `src/main.py`: liga as partes e oferece a entrada CLI/GUI.
- `tests/`: regressões essenciais de execução, escalonamento, edição e requisitos do PDF.
- `tools/`: compilação e verificação da distribuição.

```powershell
python -B -m unittest discover -s tests -v
```

**Gerar a distribuição**

No Windows, usando Python 3.12 com Tkinter:

```powershell
python -m venv .build-env
.\.build-env\Scripts\python.exe -m pip install -r requirements-build.txt
.\.build-env\Scripts\python.exe tools/build_portable.py
python tools/verify_portable.py
```

PyInstaller é uma dependência de compilação, não uma instalação exigida do usuário.
A pasta e o ZIP são gerados em `output/distribuicao`. A verificação executa o pacote
com PATH sem Python e com caminhos externos de Python/Tcl/Tk inválidos, e confere
as DLLs realmente carregadas. Ela não equivale a um teste em outra máquina física.
