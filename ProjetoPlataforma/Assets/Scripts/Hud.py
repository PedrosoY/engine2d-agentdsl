"""Placar e telas da fase: moedas, vidas, pontos e tempo; pausa, fim de jogo e vitória.

Também passa para o agente "fase" da DSL as percepções tempo(N) e moedas(N).
Teclas: P pausa · R recomeça (no fim) · Esc volta ao menu.
"""
from engine2d import Componente

import Plataforma as P

T = "Assets/Sprites/Tiles/"
BRANCO, AMARELO, CINZA = (255, 255, 255), (255, 220, 90), (60, 70, 90)


class Hud(Componente):
    CAMPOS = {"tempo_fase": "int", "cena_menu": "str"}
    tempo_fase = 300
    cena_menu = "Assets/Cenas/Menu.cena"

    def iniciar(self):
        self.pontos = 0
        self.moedas = 0
        self.tempo = float(self.tempo_fase)
        self.estado = "jogando"           # jogando | pausado | fim | vitoria
        self.t_estado = 0.0
        self.recorde = P.ler_recorde()
        self.bateu_recorde = False
        self._msg = None
        self._banner = None
        self._flutuantes = []
        self._percebido = None
        self.motor.sair_com_esc = False

    # --- chamado pelos outros scripts e pela DSL -----------------------------------------------
    def somar(self, pontos, x=None, y=None):
        if self.estado == "jogando":
            self.pontos += int(pontos)
            if x is not None:
                self._flutuantes.append([str(int(pontos)), x, y, 0.8])

    def pegar_moeda(self, x=None, y=None):
        self.moedas += 1
        self.somar(100, x, y)

    def mensagem(self, texto):
        self._msg = [texto, 1.6]

    def banner(self, texto):
        self._banner = [texto, 2.0]

    def fim_de_jogo(self):
        if self.estado == "jogando":
            self.estado, self.t_estado = "fim", 0.0
            self.bateu_recorde = P.salvar_recorde(self.pontos)

    def vitoria(self):
        if self.estado == "jogando":
            bonus = int(self.tempo) * 10
            self.pontos += bonus
            self.estado, self.t_estado = "vitoria", 0.0
            self.bonus_tempo = bonus
            self.bateu_recorde = P.salvar_recorde(self.pontos)

    # --- relógio, teclas e percepções do agente "fase" ----------------------------------------------
    def atualizar(self, dt):
        ent = self.motor.entrada
        self.t_estado += 1 / 60 if self.estado == "pausado" else dt
        if ent.tecla_baixou("escape"):
            self.motor.trocar_cena(self.cena_menu)
        elif ent.tecla_baixou("p") and self.estado in ("jogando", "pausado"):
            self.estado = "pausado" if self.estado == "jogando" else "jogando"
        elif ent.tecla_baixou("r") and self.estado in ("fim", "vitoria") and self.t_estado > 0.8:
            self.motor.reiniciar_cena()
        self.motor.escala_tempo = 0.0 if self.estado == "pausado" else 1.0
        if self.estado == "jogando":
            self.tempo = max(0.0, self.tempo - dt)
        for alvo in (self._msg, self._banner):
            if alvo:
                alvo[1] -= dt
        for f in self._flutuantes:
            f[2] += 50 * dt
            f[3] -= dt
        self._flutuantes = [f for f in self._flutuantes if f[3] > 0]
        self._perceber_fase()

    def _perceber_fase(self):
        atual = (int(self.tempo), self.moedas)
        if atual == self._percebido:
            return
        go = self.cena.encontrar("agente fase")
        corpo = go.obter("ComportamentoAgente") if go else None
        if corpo is not None and getattr(corpo, "ag", None) is not None:
            corpo.perceber({("tempo", (atual[0],)), ("moedas", (atual[1],))})
            self._percebido = atual

    # --- desenho ---------------------------------------------------------------------------------
    def desenhar_ui(self, ui):
        w, h = ui.largura, ui.altura
        j = P.jogador(self.cena)
        ui.retangulo((10, 8, w - 20, 50), (0, 0, 0, 90), raio=12)
        ui.desenhar_imagem(T + "hud_player_green.png", 40, 33, tamanho=40)
        ui.texto(66, 33, f"x {j.vidas if j else 0}", 24, BRANCO, "midleft", negrito=True)
        ui.desenhar_imagem(T + "hud_coin.png", 170, 33, tamanho=40)
        ui.texto(196, 33, f"x {self.moedas}", 24, BRANCO, "midleft", negrito=True)
        ui.texto(w / 2, 33, f"{self.pontos:07d}", 28, AMARELO, "center", negrito=True)
        cor_t = (255, 110, 110) if self.tempo < 60 else BRANCO
        ui.texto(w - 30, 33, f"TEMPO {int(self.tempo):03d}", 24, cor_t, "midright", negrito=True)
        for texto, x, y, t in self._flutuantes:
            px, py = ui.mundo_para_tela(x, y)
            ui.texto(px, py - 30, texto, 18, AMARELO, "center", negrito=True, alfa=int(255 * min(1, t * 2)))
        if self._banner and self._banner[1] > 0:
            ui.texto(w / 2, h * 0.3, self._banner[0], 40, BRANCO, "center", negrito=True,
                     alfa=int(255 * min(1, self._banner[1] * 2)))
        if self._msg and self._msg[1] > 0:
            ui.texto(w / 2, h * 0.42, self._msg[0], 26, AMARELO, "center", negrito=True,
                     alfa=int(255 * min(1, self._msg[1] * 2)))
        self._telas(ui, w, h)

    def _telas(self, ui, w, h):
        if self.estado == "pausado":
            ui.retangulo((0, 0, w, h), (0, 0, 0, 130), raio=0)
            ui.texto(w / 2, h / 2 - 10, "PAUSA", 52, BRANCO, "center", negrito=True)
            ui.texto(w / 2, h / 2 + 40, "P continua  ·  Esc menu", 20, BRANCO, "center")
        elif self.estado in ("fim", "vitoria") and self.t_estado > 1.0:
            ui.retangulo((0, 0, w, h), (0, 0, 0, 150), raio=0)
            venceu = self.estado == "vitoria"
            ui.texto(w / 2, h / 2 - 90, "FASE COMPLETA!" if venceu else "FIM DE JOGO", 54,
                     (140, 255, 140) if venceu else (255, 110, 110), "center", negrito=True)
            ui.texto(w / 2, h / 2 - 20, f"{self.pontos:07d} pontos", 32, AMARELO, "center", negrito=True)
            if venceu:
                ui.texto(w / 2, h / 2 + 18, f"{self.moedas} moedas  ·  bônus de tempo {self.bonus_tempo}", 20,
                         BRANCO, "center")
            if self.bateu_recorde:
                ui.texto(w / 2, h / 2 + 52, "NOVO RECORDE!", 22, (140, 230, 255), "center", negrito=True)
            ui.texto(w / 2, h / 2 + 100, "R joga de novo  ·  Esc menu", 20, BRANCO, "center")
