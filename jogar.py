"""Menu para jogar os projetos prontos (sem abrir o editor).

    python jogar.py            # abre o menu
    python jogar.py arena      # direto na Arena dos Sobreviventes
    python jogar.py torres     # direto no Tower Defense
    python jogar.py exemplo    # direto no projeto de exemplo
    python jogar.py navinha    # direto na navinha

Cada jogo é um projeto do editor (pasta Projeto*): para ver/alterar, use  python editor.py
"""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

PROJETOS = {
    "arena": ("ProjetoArena", "Arena dos Sobreviventes", "estilo Vampire Survivors",
              "Assets/Sprites/Personagens/jogador.png"),
    "torres": ("ProjetoTorres", "Defesa da Base", "tower defense estilo Bloons",
               "Assets/Sprites/Torres/torreta_missil.png"),
    "sorveteria": ("ProjetoSorveteria", "Fábrica de Sorvete", "programe os robôs em AgentDSL",
                   "Assets/Sprites/Itens/sorvete_misto.png"),
    "navinha": ("ProjetoNavinha", "Navinha", "shoot 'em up com IA na DSL",
                "Assets/Sprites/Naves/playerShip1_blue.png"),
    "plataforma": ("ProjetoPlataforma", "Pulo Verde", "plataforma estilo Mario",
                   "Assets/Sprites/Personagem/character_green_idle.png"),
    "exemplo": ("ProjetoExemplo", "Coletor de Moedas", "projeto de exemplo (scripts + DSL)",
                "Assets/Sprites/Personagens/jogador.png"),
}


def rodar_projeto(chave, esperar=False):
    pasta = RAIZ / PROJETOS[chave][0]
    cmd = [sys.executable, str(RAIZ / "rodar.py"), str(pasta)]
    if esperar:
        return subprocess.call(cmd)
    subprocess.Popen(cmd)


def menu():
    from engine2d import Cena, Componente, Motor
    from engine2d.ui import CORES

    class Menu(Componente):
        def desenhar_ui(self, ui):
            cx = ui.largura // 2
            ui.texto(cx, 100, "Engine2D + AgentDSL", 44, ancora="center", negrito=True)
            ui.texto(cx, 148, "escolha um jogo (cada um é um projeto que também abre no editor)", 17,
                     ancora="center", cor=(200, 200, 210))
            n = len(PROJETOS)
            por_linha = 3
            for i, (chave, (pasta, titulo, sub, img)) in enumerate(PROJETOS.items()):
                k = min(por_linha, n - (i // por_linha) * por_linha)        # cartões nesta linha
                r = (cx - (k * 308 - 8) // 2 + (i % por_linha) * 308, 185 + (i // por_linha) * 250, 300, 235)
                if ui.botao(r, ""):
                    rodar_projeto(chave)
                try:
                    ui.desenhar_imagem(str(RAIZ / pasta / img), r[0] + 150, r[1] + 90, tamanho=110)
                except Exception:
                    pass
                ui.texto(r[0] + 150, r[1] + 175, titulo, 22, ancora="center", negrito=True)
                ui.texto(r[0] + 150, r[1] + 205, sub, 13, ancora="center", cor=(200, 200, 210))
            ui.texto(cx, 680, "Para ver e mudar os jogos: python editor.py  ·  ESC sai", 15, ancora="center",
                     cor=CORES["destaque"])
            ui.texto(cx, 704, "Assets: Kenney (CC0) — kenney.nl", 13, ancora="center", cor=(130, 130, 140))

    motor = Motor(1280, 720, "Engine2D + AgentDSL", pasta_assets=RAIZ, editor=False, tela_cheia=True)
    cena = Cena("Menu")
    cena.criar("Menu", componentes=[Menu()])
    motor.executar(cena)
    motor.encerrar()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(rodar_projeto(sys.argv[1], esperar=True))
    menu()
