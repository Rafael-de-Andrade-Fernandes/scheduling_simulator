import os
import sys
import main_copy

# --- 1. Importamos as bibliotecas nativas dependendo do Sistema Operacional ---
if os.name == 'nt':
    import msvcrt  # Biblioteca embutida do Windows
else:
    import tty, termios, select  # Bibliotecas embutidas do Linux e Mac

def ler_setinha():
    """Lê o teclado e identifica se foi pressionada uma seta ou o botão ESC."""
    
    # --- Lógica para WINDOWS ---
    if os.name == 'nt':
        tecla = msvcrt.getch()
        if tecla == b'\x1b':  # Código byte para a tecla ESC
            return 'ESC'
        
        # No Windows, teclas especiais (como setas) geram dois sinais seguidos. 
        # O primeiro costuma ser \xe0 ou \x00.
        elif tecla in (b'\xe0', b'\x00'):
            tecla = msvcrt.getch()  # Lê o segundo sinal
            if tecla == b'K': return 'ESQUERDA'
            if tecla == b'M': return 'DIREITA'
            
    # --- Lógica para LINUX / MAC ---
    else:
        fd = sys.stdin.fileno()
        config_antiga = termios.tcgetattr(fd)
        try:
            tty.setraw(fd) # Muda o terminal para ler tecla a tecla (sem Enter)
            ch = sys.stdin.read(1)
            
            if ch == '\x1b':  # '\x1b' é o sinal de ESC. Mas setinhas começam com ESC!
                # Verificamos super rápido se tem mais dados vindo atrás do ESC
                # (Setinhas no Linux enviam 3 caracteres juntos: ESC + [ + C)
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    ch2 = sys.stdin.read(2) # Lê os próximos dois caracteres
                    if ch2 == '[D': return 'ESQUERDA'
                    if ch2 == '[C': return 'DIREITA'
                else:
                    return 'ESC' # Se não veio mais nada, o usuário apertou só o ESC mesmo
        finally:
            # Garante que o terminal volta ao normal mesmo se der erro
            termios.tcsetattr(fd, termios.TCSADRAIN, config_antiga)
            
    return None

def limpar_tela():
    os.system('cls' if os.name == 'nt' else 'clear')

def programa_nativo():
    etapas = [
        "--- ETAPA 1 ---\nNenhuma biblioteca baixada! Seta DIREITA para avançar.",
        "--- ETAPA 2 ---\nSeta ESQUERDA volta, DIREITA avança.",
        "--- ETAPA 3 ---\nEstamos lendo o teclado direto do sistema operacional.",
        "--- ETAPA 4 ---\nFim do programa! Aperte ESC para sair."
    ]
    
    indice = 0
    
    # Função para desenhar a tela
    def desenhar():
        limpar_tela()
        print("=" * 60)
        print(etapas[indice])
        print("=" * 60)
        print("\nControles: [->] Avançar | [<-] Retroceder | [ESC] Sair")

    desenhar()

    # Loop principal
    while True:
        acao = ler_setinha()
        
        if acao == 'DIREITA':
            if indice < len(etapas) - 1:
                indice += 1
                desenhar()
        elif acao == 'ESQUERDA':
            if indice > 0:
                indice -= 1
                desenhar()
        elif acao == 'ESC':
            limpar_tela()
            print("Você saiu do programa. Até logo!\n")
            break

# Executa o código
if __name__ == "__main__":
    programa_nativo()