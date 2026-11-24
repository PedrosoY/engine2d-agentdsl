"""O "corpo" de um inimigo. Quem decide o que ele faz é o agente da DSL (Assets/Agentes/navinha.agt);
este script só executa os movimentos pedidos, manda as percepções para o agente e cuida da física.

Percepções que o agente recebe:
  jogador_lado(esquerda | direita | frente)   onde o jogador está em relação a ele
  chegou                                      terminou o ir_para / descer_ate
  atingido(D)                                 levou um tiro (vem do Tiro.py)
"""
import math

from agentdsl.interpretador import Simbolo
from engine2d import Componente

import Navinha as N

LADOS = {n: Simbolo(n) for n in ("esquerda", "direita", "frente")}


class NaveInimiga(Componente):
    CAMPOS = {"dano_contato": "int", "tamanho_explosao": "float"}
    dano_contato = 1
    tamanho_explosao = 1.0

    def iniciar(self):
        self.destino = None            # (x, y, velocidade) do ir_para
        self.quicar = False            # bate nas bordas da área e volta
        self.entrou = False            # já apareceu dentro da área (só some depois de entrar)
        self.morto = False
        self.angulo_anel = 0.0         # o anel de tiros gira um pouco a cada vez (espiral)
        self.agente = self.obter("ComportamentoAgente")

    def _corpo(self):
        return self.obter("CorpoRigido")

    def atualizar(self, dt):
        t = self.transform
        x, y = t.posicao_mundo
        if N.dentro(x, y, -10):
            self.entrou = True
        elif self.entrou and not N.dentro(x, y, 90):
            self.gameobject.destruir()          # saiu da área: some sem dar pontos
            return
        elif not self.entrou and y < N.BAIXO - 90:
            self.gameobject.destruir()
            return
        rb = self._corpo()
        if self.destino is not None and rb is not None:
            dx, dy, vel = self.destino[0] - x, self.destino[1] - y, self.destino[2]
            d = math.hypot(dx, dy)
            if d <= vel * dt or d < 2:
                t.posicao_mundo = self.destino[:2]
                rb.vx = rb.vy = 0.0
                self.destino = None
                self._pulsar("chegou")
            else:
                rb.vx, rb.vy = dx / d * vel, dy / d * vel
        if self.quicar and rb is not None:
            if (x < N.ESQUERDA + 50 and rb.vx < 0) or (x > N.DIREITA - 50 and rb.vx > 0):
                rb.vx = -rb.vx
        self._perceber(x)

    def _perceber(self, x):
        if self.agente is None or getattr(self.agente, "ag", None) is None:
            return
        j = N.jogador(self.cena)
        atuais = set()
        if j is not None:
            jx = j.transform.posicao_mundo[0]
            lado = "frente" if abs(jx - x) < 40 else ("esquerda" if jx < x else "direita")
            atuais.add(("jogador_lado", (LADOS[lado],)))
        self.agente.perceber(atuais)

    def _pulsar(self, nome, args=()):
        if self.agente is not None and getattr(self.agente, "ag", None) is not None:
            self.agente.pulsar(nome, args)

    # --- usado pelas ações da DSL ---------------------------------------------------------
    def ir_para(self, x, y, vel):
        self.destino = (float(x), float(y), max(1.0, float(vel)))

    def explodir(self, pontos=0):
        if self.morto:
            return
        self.morto = True
        x, y = self.transform.posicao_mundo
        N.explosao(self.cena, x, y, self.tamanho_explosao)
        h = N.hud(self.cena)
        if h is not None and pontos:
            h.somar(int(pontos), x, y)
        self.gameobject.destruir()

    def bateu_no_jogador(self, jogador):
        if jogador.levar_dano():
            self._pulsar("atingido", (self.dano_contato * 3,))
