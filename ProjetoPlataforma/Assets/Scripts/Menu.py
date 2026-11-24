"""Tela de título: Espaço (ou Enter) começa a fase; Esc fecha o jogo."""
import math

from engine2d import Componente

import Plataforma as P


class Menu(Componente):
    CAMPOS = {"cena_jogo": "str", "titulo": "str"}
    cena_jogo = "Assets/Cenas/Fase1.cena"
    titulo = "PULO VERDE"

    def iniciar(self):
        self.t = 0.0
        self.recorde = P.ler_recorde()
        self.motor.sair_com_esc = True

    def atualizar(self, dt):
        self.t += dt
        ent = self.motor.entrada
        if ent.tecla_baixou("space") or ent.tecla_baixou("return"):
            P.tocar(self.cena, "moeda")
            self.motor.trocar_cena(self.cena_jogo)

    def desenhar_ui(self, ui):
        w, h = ui.largura, ui.altura
        y = h * 0.22 + math.sin(self.t * 2.2) * 6
        ui.texto(w / 2 + 4, y + 4, self.titulo, 84, (40, 90, 40), "center", negrito=True, sombra=False)
        ui.texto(w / 2, y, self.titulo, 84, (255, 255, 255), "center", negrito=True, sombra=False)
        ui.texto(w / 2, y + 66, "uma fase de plataforma feita na Engine2D", 22, (30, 60, 30), "center",
                 sombra=False)
        if int(self.t * 2) % 2 == 0:
            ui.texto(w / 2, h * 0.56, "aperte ESPAÇO para jogar", 30, (255, 255, 255), "center", negrito=True)
        ui.texto(w / 2, h * 0.65, f"recorde: {self.recorde}", 20, (255, 240, 150), "center", negrito=True)
        ui.texto(w / 2, h - 50, "A/D ou setas andam  ·  Espaço pula (segure para pular mais alto)  ·  P pausa",
                 18, (255, 255, 255), "center")
        ui.texto(w / 2, h - 24, "inimigos e blocos controlados pela AgentDSL  ·  arte e sons: Kenney (CC0)", 15,
                 (220, 235, 220), "center")
