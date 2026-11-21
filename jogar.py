"""Menu principal: escolha o jogo.

    python jogar.py            # abre o menu
    python jogar.py arena      # direto na Arena dos Sobreviventes
    python jogar.py torres     # direto no Tower Defense
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

from engine2d import Cena, Componente, SpriteRenderer  # noqa: E402
from engine2d.ui import CORES  # noqa: E402


class Menu(Componente):
    def iniciar(self):
        self.motor.sair_com_esc = True

    def desenhar_ui(self, ui):
        cx = ui.largura // 2
        ui.texto(cx, 120, "Engine2D + AgentDSL", 44, ancora="center", negrito=True)
        ui.texto(cx, 168, "dois jogos, uma engine, comportamentos escritos na DSL", 18, ancora="center",
                 cor=(200, 200, 210))
        jogos = [("Arena dos Sobreviventes", "estilo Vampire Survivors", "kenney_shooter/PNG/Survivor 1/survivor1_gun.png",
                  "arena"),
                 ("Defesa da Base", "tower defense estilo Bloons", "kenney_td/PNG/Default size/towerDefense_tile205.png",
                  "torres")]
        for i, (titulo, sub, img, chave) in enumerate(jogos):
            r = (cx - 420 + i * 440, 230, 400, 300)
            if ui.botao(r, ""):
                self.motor.trocar_cena(fabrica(chave))
            ui.desenhar_imagem(img, r[0] + 200, r[1] + 110, tamanho=120)
            ui.texto(r[0] + 200, r[1] + 210, titulo, 26, ancora="center", negrito=True)
            ui.texto(r[0] + 200, r[1] + 245, sub, 16, ancora="center", cor=(200, 200, 210))
        ui.texto(cx, 580, "ESC sai · F1 abre o editor em qualquer cena", 15, ancora="center", cor=(170, 170, 180))
        ui.texto(cx, 690, "Assets: Kenney (CC0) — kenney.nl", 13, ancora="center", cor=(130, 130, 140))


def fabrica(chave):
    if chave == "arena":
        from jogos.arena.arena import criar_cena
    else:
        from jogos.torres.torres import criar_cena
    return criar_cena


def criar_menu() -> Cena:
    cena = Cena("Menu")
    for i in range(21):
        for j in range(12):
            cena.criar("t", i * 64, j * 64, componentes=[SpriteRenderer(
                imagem="kenney_td/PNG/Default size/towerDefense_tile" + ("119" if (i + j) % 2 else "124") + ".png",
                camada=0, cor=(0.45, 0.5, 0.55, 1))])
    cena.criar("Menu", componentes=[Menu()])
    return cena


def main(argv=None, max_quadros=None, captura=None):
    from engine2d import Motor
    argv = sys.argv[1:] if argv is None else argv
    motor = Motor(1280, 720, "Engine2D + AgentDSL", pasta_assets=RAIZ / "assets")
    cena = fabrica(argv[0])() if argv else criar_menu()
    motor.executar(cena, max_quadros=max_quadros, captura=captura)
    motor.encerrar()


if __name__ == "__main__":
    main()
