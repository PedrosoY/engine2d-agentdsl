"""Liga a fase ao diretor da DSL: diz onde os inimigos nascem e conta quantos estão na tela
(percepção inimigos(N) do agente diretor)."""
from engine2d import Componente

import Navinha as N


class Fase(Componente):
    CAMPOS = {"musica": "str", "volume_musica": "float"}
    musica = ""
    volume_musica = 0.4

    def iniciar(self):
        self._contagem = None
        if self.musica:
            self.motor.audio.musica(self.musica, self.volume_musica)

    def atualizar(self, dt):
        srv = self.cena.servicos.get("agentes")
        if srv is None:
            return
        if srv.ponto_de_invocacao is None:
            srv.ponto_de_invocacao = lambda modelo: (N.x_aleatorio(50), N.CIMA + 50)
        n = len(self.cena.com_tag("inimigo"))
        if n != self._contagem:
            self._contagem = n
            go = self.cena.encontrar("agente diretor")
            corpo = go.obter("ComportamentoAgente") if go else None
            if corpo is not None and getattr(corpo, "ag", None) is not None:
                corpo.perceber({("inimigos", (n,))})
