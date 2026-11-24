from Comum import criar_fumaca
from engine2d import Componente
from engine2d.projeto import percepcao_dsl
from engine2d.ui import CORES
from Mapa import COMPRIMENTO, ponto_no_caminho

percepcao_dsl("atingido", "num")      # levou dano neste quadro
percepcao_dsl("chegou_ao_fim")        # alcançou a base


class SeguirCaminho(Componente):
    """Anda pelo caminho do mapa. ``progresso`` = distância já percorrida."""

    CAMPOS = {"velocidade": "float", "progresso": "float"}
    velocidade = 70.0
    progresso = 0.0

    def iniciar(self):
        self.lento = 1.0
        self.tempo_lento = 0.0
        self.chegou = False
        self.agente = self.obter("ComportamentoAgente")
        self.render = self.obter("SpriteRenderer")

    def desacelerar(self, fator, segundos=1.2):
        self.lento = min(self.lento, fator)
        self.tempo_lento = segundos

    def atualizar(self, dt):
        if self.tempo_lento > 0:
            self.tempo_lento -= dt
            if self.tempo_lento <= 0:
                self.lento = 1.0
        self.progresso += self.velocidade * self.lento * dt
        x, y, ang = ponto_no_caminho(self.progresso)
        t = self.transform
        t.x, t.y, t.rotacao = x, y, ang
        if self.render:
            self.render.cor = (0.6, 0.85, 1.0, 1.0) if self.lento < 1 else (1, 1, 1, 1)
        if self.progresso >= COMPRIMENTO and not self.chegou and self.agente and self.agente._iniciado:
            self.chegou = True
            self.agente.pulsar("chegou_ao_fim")      # evento +chegou_ao_fim no .agt


class InimigoTD(Componente):
    """Junta o dano do quadro num único evento +atingido(D) e desenha a barra de vida."""

    def iniciar(self):
        self.dano = 0.0
        self.agente = self.obter("ComportamentoAgente")
        self.vida_max = None

    def receber_dano(self, d):
        self.dano += d

    def vida(self):
        return self.agente.crenca_num("vida") if self.agente and self.agente._iniciado else 0.0

    def atualizar(self, dt):
        if self.agente is None or not self.agente._iniciado:
            return
        if self.vida_max is None:
            self.vida_max = self.vida() or 1.0
        if self.dano > 0:
            self.agente.pulsar("atingido", (round(self.dano, 2),))
            self.dano = 0.0

    def desenhar_ui(self, ui):
        if self.vida_max and self.vida() < self.vida_max:
            x, y = ui.mundo_para_tela(*self.transform.posicao_mundo)
            ui.barra((x - 18, y - 30, 36, 5), self.vida() / self.vida_max, cor=CORES["vermelho"])

    def ao_destruir(self):
        if self.cena is not None and "gerente" in self.cena.servicos:
            x, y = self.transform.posicao_mundo
            criar_fumaca(self.cena, x, y, 0.6 * self.transform.escala_x)
