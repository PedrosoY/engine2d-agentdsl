"""Tela de título: Espaço (ou Enter) começa a fase; Esc fecha o jogo."""
import math

from engine2d import Componente

import Navinha as N


class Menu(Componente):
    CAMPOS = {"cena_jogo": "str", "titulo": "str"}
    cena_jogo = "Assets/Cenas/Fase1.cena"
    titulo = "NAVINHA"

    def iniciar(self):
        self.t = 0.0
        self.recorde = N.ler_recorde()
        self.motor.sair_com_esc = True

    def atualizar(self, dt):
        self.t += dt
        ent = self.motor.entrada
        if ent.tecla_baixou("space") or ent.tecla_baixou("return"):
            N.tocar(self.cena, "item")
            self.motor.trocar_cena(self.cena_jogo)

    def desenhar_ui(self, ui):
        w, h = ui.largura, ui.altura
        y = h * 0.2 + math.sin(self.t * 2) * 6
        ui.texto(w / 2, y, self.titulo, 80, (255, 210, 70), "center", negrito=True)
        ui.texto(w / 2, y + 62, "um shoot 'em up feito na Engine2D", 18, (180, 185, 210), "center")
        ui.texto(w / 2, h * 0.43, "RECORDE", 14, (140, 230, 255), "center", negrito=True)
        ui.texto(w / 2, h * 0.43 + 24, f"{self.recorde:07d}", 20, (140, 230, 255), "center", fonte=N.FONTE)
        if int(self.t * 2) % 2 == 0:
            ui.texto(w / 2, h * 0.6, "aperte ESPAÇO para jogar", 24, (240, 240, 250), "center", negrito=True)
        ui.texto(w / 2, h - 22, "inimigos controlados pela AgentDSL  ·  arte e sons: Kenney (CC0)", 13,
                 (120, 125, 150), "center")
