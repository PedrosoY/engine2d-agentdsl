import math

from Comum import criar_fumaca
from engine2d import Componente
from engine2d.projeto import percepcao_dsl

# Crenças que este script coloca nos agentes (o compilador da DSL passa a conhecê-las)
percepcao_dsl("atingido", "num")
percepcao_dsl("tocando_jogador")
percepcao_dsl("jogador_perto")


class Inimigo(Componente):
    """Vai em todo inimigo (prefabs). Gera as percepções do agente da DSL a cada quadro.

    O COMPORTAMENTO (perseguir, morder, atirar, morrer) está em Assets/Agentes/arena.agt.
    """

    CAMPOS = {"raio_toque": "float"}
    raio_toque = 30.0

    def iniciar(self):
        self.dano_acumulado = 0.0
        self.agente = self.obter("ComportamentoAgente")
        self.jogador = self.cena.encontrar("jogador")

    def receber_dano(self, d):
        self.dano_acumulado += d      # vários golpes no mesmo quadro viram um único evento

    def atualizar(self, dt):
        corpo = self.agente
        if corpo is None or not corpo._iniciado or self.jogador is None:
            return
        if self.dano_acumulado > 0:
            corpo.pulsar("atingido", (round(self.dano_acumulado, 1),))     # evento +atingido(D)
            self.dano_acumulado = 0.0
        jx, jy = self.jogador.transform.posicao_mundo
        x, y = self.transform.posicao_mundo
        d = math.hypot(jx - x, jy - y)
        percepcoes = set()
        if d < self.raio_toque * self.transform.escala_x + 22:
            percepcoes.add(("tocando_jogador", ()))
        alcance = corpo.crenca_num("alcance")      # crença alcance(R) escrita no .agt
        if alcance and d < alcance:
            percepcoes.add(("jogador_perto", ()))
        corpo.perceber(percepcoes)                 # só o que mudou vira evento (+b / -b)

    def ao_destruir(self):
        if self.cena is not None and "gerente" in self.cena.servicos:
            x, y = self.transform.posicao_mundo
            criar_fumaca(self.cena, x, y, 0.7 * self.transform.escala_x)
            self.cena.servicos["gerente"].abates += 1
