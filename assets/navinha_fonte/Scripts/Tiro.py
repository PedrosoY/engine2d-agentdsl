"""Um tiro: anda reto (CorpoRigido), some fora da área e causa dano no que acerta.

``do_jogador``: tiro do jogador acerta inimigos; tiro de inimigo acerta o jogador.
"""
from engine2d import Componente

import Navinha as N


class Tiro(Componente):
    CAMPOS = {"dano": "int", "do_jogador": "bool"}
    dano = 1
    do_jogador = True

    def atualizar(self, dt):
        x, y = self.transform.posicao_mundo
        if not N.dentro(x, y, 40):
            self.gameobject.destruir()

    def ao_entrar_colisao(self, outro):
        if self.gameobject.destruido:
            return
        alvo = outro.gameobject
        x, y = self.transform.posicao_mundo
        if self.do_jogador and alvo.tag == "inimigo":
            corpo = alvo.obter("ComportamentoAgente")
            if corpo is not None and getattr(corpo, "ag", None) is not None:
                corpo.pulsar("atingido", (self.dano,))     # o agente da DSL decide o que acontece
            N.faisca(self.cena, x, y + 8)
            N.tocar(self.cena, "acerto", 0.25)
            self.gameobject.destruir()
        elif not self.do_jogador and alvo.tag == "jogador":
            j = alvo.obter("Jogador")
            if j is not None:
                j.levar_dano()
            self.gameobject.destruir()
