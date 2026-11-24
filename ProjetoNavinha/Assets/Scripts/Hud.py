"""Placar e telas da fase: painéis laterais, avisos, barra do chefe, pausa, fim de jogo e vitória.

Teclas: P pausa · R recomeça (no fim) · Esc volta ao menu.
"""
from engine2d import Componente

import Navinha as N

AMARELO, BRANCO, CINZA = (255, 210, 70), (235, 235, 245), (150, 155, 175)


class Hud(Componente):
    CAMPOS = {"cena_menu": "str"}
    cena_menu = "Assets/Cenas/Menu.cena"

    def iniciar(self):
        self.pontos = 0
        self.recorde = N.ler_recorde()
        self.bateu_recorde = False
        self.estado = "jogando"          # jogando | pausado | fim | vitoria
        self.t_estado = 0.0
        self._banner = None              # (texto, tempo restante)
        self._curta = None
        self._flutuantes = []            # [texto, x, y, tempo]
        self.vida_chefe = None           # (vida, total) enquanto o chefe estiver vivo
        self.motor.sair_com_esc = False  # Esc volta ao menu em vez de fechar o jogo

    # --- chamado pelos outros scripts e pela DSL --------------------------------------------------
    def somar(self, pontos, x=None, y=None):
        if self.estado not in ("jogando", "pausado"):
            return
        self.pontos += int(pontos)
        if x is not None:
            self._flutuantes.append([f"+{int(pontos)}", x, y, 0.9])

    def banner(self, texto, tempo=2.2):
        self._banner = [texto, tempo]

    def mensagem_curta(self, texto):
        self._curta = [texto, 1.4]

    def fim_de_jogo(self):
        if self.estado == "jogando":
            self.estado, self.t_estado = "fim", 0.0
            self.bateu_recorde = N.salvar_recorde(self.pontos)

    def vitoria(self):
        if self.estado == "jogando":
            j = N.jogador(self.cena)
            if j is not None:
                self.pontos += 1000 * j.vidas          # bônus pelas vidas que sobraram
            self.estado, self.t_estado = "vitoria", 0.0
            self.vida_chefe = None
            self.bateu_recorde = N.salvar_recorde(self.pontos)

    # --- teclas ---------------------------------------------------------------------------------
    def atualizar(self, dt):
        ent = self.motor.entrada
        self.t_estado += dt
        if ent.tecla_baixou("escape"):
            self.motor.pausado = False
            self.motor.trocar_cena(self.cena_menu)
        elif ent.tecla_baixou("p") and self.estado in ("jogando", "pausado"):
            self.estado = "pausado" if self.estado == "jogando" else "jogando"
        elif ent.tecla_baixou("r") and self.estado in ("fim", "vitoria") and self.t_estado > 0.8:
            self.motor.reiniciar_cena()
        self.motor.escala_tempo = 0.0 if self.estado == "pausado" else 1.0
        real = dt if self.estado != "pausado" else 1 / 60
        for alvo in (self._banner, self._curta):
            if alvo:
                alvo[1] -= real
        for f in self._flutuantes:
            f[2] += 40 * dt
            f[3] -= dt
        self._flutuantes = [f for f in self._flutuantes if f[3] > 0]

    # --- desenho ----------------------------------------------------------------------------------
    def desenhar_ui(self, ui):
        w, h = ui.largura, ui.altura
        esq, dir_ = int(N.ESQUERDA), int(N.DIREITA)
        ui.retangulo((0, 0, esq, h), (10, 8, 24, 235), raio=0)
        ui.retangulo((dir_, 0, w - dir_, h), (10, 8, 24, 235), raio=0)
        ui.linha((esq, 0), (esq, h), (90, 80, 170), 2)
        ui.linha((dir_, 0), (dir_, h), (90, 80, 170), 2)
        f = N.FONTE
        # painel da esquerda: pontos
        ui.texto(esq / 2, 40, "PONTOS", 16, CINZA, "center", negrito=True)
        ui.texto(esq / 2, 72, f"{self.pontos:07d}", 22, AMARELO, "center", fonte=f)
        ui.texto(esq / 2, 130, "RECORDE", 14, CINZA, "center", negrito=True)
        ui.texto(esq / 2, 156, f"{max(self.recorde, self.pontos):07d}", 16, BRANCO, "center", fonte=f)
        ui.texto(esq / 2, h - 70, "WASD / setas", 12, CINZA, "center", negrito=True)
        ui.texto(esq / 2, h - 50, "Espaço atira", 12, CINZA, "center", negrito=True)
        ui.texto(esq / 2, h - 30, "Shift  P  Esc", 12, CINZA, "center", negrito=True)
        # painel da direita: vidas, arma, escudo
        j = N.jogador(self.cena)
        cx = dir_ + (w - dir_) / 2
        ui.texto(cx, 40, "VIDAS", 16, CINZA, "center", negrito=True)
        vidas = j.vidas if j else 0
        for i in range(max(0, vidas)):
            ui.desenhar_imagem("Assets/Sprites/UI/playerLife1_blue.png", cx - 40 + (i % 3) * 40,
                               76 + (i // 3) * 30)
        ui.texto(cx, 150, "ARMA", 16, CINZA, "center", negrito=True)
        nivel = j.nivel_arma if j else 0
        for i in range(4):
            cor = AMARELO if i < nivel else (50, 50, 70)
            ui.retangulo((cx - 50 + i * 26, 170, 22, 14), cor, raio=3)
        ui.texto(cx, 210, "ESCUDO", 16, CINZA, "center", negrito=True)
        ui.barra((cx - 55, 230, 110, 12), (j.escudo / 10.0) if j else 0, cor=(90, 170, 255))
        # barra do chefe
        if self.vida_chefe:
            v, t = self.vida_chefe
            ui.texto((esq + dir_) / 2, 10, "CHEFE", 13, (255, 120, 120), "midtop", negrito=True)
            ui.barra((esq + 30, 28, dir_ - esq - 60, 12), v / max(1.0, t), cor=(230, 70, 70))
        # pontos flutuando onde o inimigo explodiu
        for texto, x, y, tempo in self._flutuantes:
            px, py = ui.mundo_para_tela(x, y)
            ui.texto(px, py, texto, 14, AMARELO, "center", fonte=f, alfa=int(255 * min(1.0, tempo * 2)))
        if self._banner and self._banner[1] > 0:
            a = int(255 * min(1.0, self._banner[1] * 2))
            ui.texto((esq + dir_) / 2, h * 0.38, self._banner[0], 30, BRANCO, "center", negrito=True, alfa=a)
        if self._curta and self._curta[1] > 0:
            ui.texto((esq + dir_) / 2, h - 60, self._curta[0], 20, (140, 230, 255), "center", negrito=True)
        self._tela_estado(ui, esq, dir_, h)

    def _tela_estado(self, ui, esq, dir_, h):
        f = N.FONTE
        meio = (esq + dir_) / 2
        if self.estado == "pausado":
            ui.retangulo((esq, 0, dir_ - esq, h), (0, 0, 0, 140), raio=0)
            ui.texto(meio, h / 2, "PAUSA", 40, BRANCO, "center", negrito=True)
            ui.texto(meio, h / 2 + 40, "P continua  ·  Esc menu", 14, CINZA, "center", negrito=True)
        elif self.estado in ("fim", "vitoria") and self.t_estado > 0.6:
            ui.retangulo((esq, 0, dir_ - esq, h), (0, 0, 0, 160), raio=0)
            titulo = "FIM DE JOGO" if self.estado == "fim" else "VITÓRIA!"
            cor = (255, 90, 90) if self.estado == "fim" else (120, 255, 150)
            ui.texto(meio, h / 2 - 60, titulo, 44, cor, "center", negrito=True)
            ui.texto(meio, h / 2, f"{self.pontos:07d}", 26, AMARELO, "center", fonte=f)
            if self.bateu_recorde:
                ui.texto(meio, h / 2 + 34, "NOVO RECORDE!", 18, (140, 230, 255), "center", negrito=True)
            ui.texto(meio, h / 2 + 80, "R joga de novo  ·  Esc menu", 14, CINZA, "center", negrito=True)
