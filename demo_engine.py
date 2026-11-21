"""Demo da engine (Computação Gráfica): cena montada com GameObjects e componentes.

  WASD move o personagem · a câmera segue · F1 abre o editor
  No editor: clique para selecionar, arraste para mover, edite valores no inspector,
  F5 play/pause, Ctrl+S salva a cena em JSON. M alterna o modo de renderização.
"""
import math
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

from engine2d import (CameraSegue, Cena, Colisor, Componente, CorpoRigido,  # noqa: E402
                      SpriteRenderer)

SH = "kenney_shooter/PNG/"


class ControleJogador(Componente):
    CAMPOS = {"velocidade": "float"}
    velocidade = 260.0

    def iniciar(self):
        self.rb = self.obter(CorpoRigido)

    def atualizar(self, dt):
        ent = self.motor.entrada
        dx, dy = ent.direcao_wasd()
        self.rb.vx, self.rb.vy = dx * self.velocidade, dy * self.velocidade
        mx, my = ent.mouse_mundo
        self.transform.olhar_para(mx, my)
        if ent.tecla_baixou("m"):
            r = self.motor.renderizador
            r.modo = "individual" if r.modo == "lote" else "lote"


class Perseguidor(Componente):
    CAMPOS = {"velocidade": "float", "alvo": "str"}
    velocidade = 90.0
    alvo = "Jogador"

    def iniciar(self):
        self.rb = self.obter(CorpoRigido)

    def atualizar(self, dt):
        alvo = self.cena.encontrar(self.alvo)
        if alvo is None:
            return
        ax, ay = alvo.transform.posicao_mundo
        x, y = self.transform.posicao_mundo
        d = math.hypot(ax - x, ay - y) or 1
        self.rb.vx, self.rb.vy = (ax - x) / d * self.velocidade, (ay - y) / d * self.velocidade
        self.transform.olhar_para(ax, ay)


class Orbitar(Componente):
    """Gira o objeto em torno do pai (mostra a hierarquia de transformações)."""
    CAMPOS = {"graus_por_s": "float"}
    graus_por_s = 120.0

    def atualizar(self, dt):
        self.transform.rotacao += self.graus_por_s * dt


class Legenda(Componente):
    def desenhar_ui(self, ui):
        ui.retangulo((10, 10, 360, 70), bloquear=False)
        ui.texto(20, 16, "Demo da Engine2D", 18, negrito=True)
        ui.texto(20, 40, "WASD move · mouse mira · F1 editor · M modo render", 14)
        ui.texto(20, 58, f"FPS {self.motor.fps_medio:.0f} · modo {self.motor.renderizador.modo}", 14)


def montar_cena() -> Cena:
    cena = Cena("Demo")
    random.seed(3)
    chao = cena.criar("Chão")       # agrupa os tiles (aparece recolhido na hierarquia)
    for i in range(-10, 30):
        for j in range(-8, 20):
            cena.criar(f"tile {i},{j}", i * 64, j * 64, pai=chao, componentes=[
                SpriteRenderer(imagem=SH + "Tiles/tile_0" + ("1" if (i * 7 + j * 3) % 5 else "2") + ".png",
                               camada=0)])
    jog = cena.criar("Jogador", 600, 400, tag="jogador", componentes=[
        SpriteRenderer(imagem=SH + "Survivor 1/survivor1_gun.png", camada=3),
        CorpoRigido(massa=3), Colisor(raio=20, camada_fisica="jogador"), ControleJogador(), CameraSegue()])
    # Filho que orbita o jogador: a posição dele é relativa ao pai.
    pivo = cena.criar("Pivô da órbita", 0, 0, pai=jog, componentes=[Orbitar()])
    cena.criar("Satélite", 70, 0, pai=pivo, escala=0.6, componentes=[
        SpriteRenderer(imagem="kenney_td/PNG/Default size/towerDefense_tile134.png", camada=4)])
    for k in range(25):
        cena.criar(f"Caixa {k}", random.uniform(-400, 1700), random.uniform(-300, 1100), componentes=[
            SpriteRenderer(imagem=SH + "Tiles/tile_129.png", camada=2), Colisor(forma="caixa", largura=60, altura=60)])
    tipos = ["Zombie 1/zoimbie1_hold.png", "Robot 1/robot1_hold.png", "Man Brown/manBrown_hold.png"]
    for k in range(40):
        cena.criar(f"Inimigo {k}", random.uniform(-400, 1700), random.uniform(-300, 1100), tag="inimigo",
                   componentes=[SpriteRenderer(imagem=SH + random.choice(tipos), camada=2), CorpoRigido(),
                                Colisor(raio=18, camada_fisica="inimigo"),
                                Perseguidor(velocidade=random.uniform(50, 110))])
    cena.criar("Legenda", componentes=[Legenda()])
    return cena


def main(max_quadros=None, captura=None):
    from engine2d import Motor
    motor = Motor(1280, 720, "Engine2D — demo", pasta_assets=RAIZ / "assets")
    motor.executar(montar_cena(), max_quadros=max_quadros, captura=captura)
    motor.encerrar()


if __name__ == "__main__":
    main()
