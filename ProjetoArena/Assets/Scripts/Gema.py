import math
import random

from engine2d import Componente, SpriteRenderer
from engine2d.projeto import acao_dsl


class Gema(Componente):
    """Cristal de experiência: voa até o jogador quando ele chega perto (ímã)."""

    CAMPOS = {"valor": "int"}
    valor = 1

    def iniciar(self):
        self.jogador = self.cena.encontrar("jogador")
        self.comp = self.jogador.obter("Jogador")
        self.atraida = False
        self.vel = 0.0

    def atualizar(self, dt):
        jx, jy = self.jogador.transform.posicao_mundo
        t = self.transform
        dx, dy = jx - t.x, jy - t.y
        d = math.hypot(dx, dy)
        if not self.atraida and d < self.comp.ima:
            self.atraida = True
        if self.atraida:
            self.vel = min(900.0, self.vel + 1400 * dt)
            passo = min(d, self.vel * dt)
            t.x += dx / (d or 1) * passo
            t.y += dy / (d or 1) * passo
            if d < 18:
                self.comp.ganhar_xp(self.valor)
                self.gameobject.destruir()


@acao_dsl("soltar_xp", "num", descricao="solta cristais de experiência onde o inimigo está")
def soltar_xp(corpo, agente, n):
    x, y = corpo.transform.posicao_mundo
    n = int(n)
    valor = 5 if n >= 5 else 1
    for _ in range(max(1, n // valor)):
        corpo.cena.criar("cristal", x + random.uniform(-14, 14), y + random.uniform(-14, 14), escala=0.45,
                         componentes=[SpriteRenderer(
                             imagem="Assets/Sprites/Efeitos/" + ("cristal.png" if valor == 1 else "cristal_grande.png"),
                             camada=1, cor=(0.45, 0.85, 1.0, 1) if valor == 1 else (1, 0.5, 1, 1)), Gema(valor=valor)])
