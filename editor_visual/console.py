"""Painel Console: mensagens do editor, erros de scripts e a saída (print) do jogo em Play."""
from __future__ import annotations

import time

import pygame

from .widgets import COR, botao, recortar

CORES = {"info": COR["texto"], "aviso": COR["amarelo"], "erro": COR["vermelho"], "play": COR["play"],
         "ajuda": (150, 210, 150)}


class ConsoleMixin:
    def log(self, texto: str, tipo: str = "info"):
        for linha in str(texto).splitlines() or [""]:
            self.console.append((time.strftime("%H:%M:%S"), linha, tipo))
        del self.console[:-800]
        self._rolagem_console_fim = True

    def _n_erros(self):
        return sum(1 for _, _, t in self.console if t == "erro")

    def _desenhar_console(self, ui, area):
        ent = self.motor.entrada
        livre = self.livre("baixo")
        if botao(ui, (area.x + 6, area.y + 4, 70, 20), "Limpar", livre):
            self.console.clear()
        ui.texto(area.x + 90, area.y + 14, f"{len(self.console)} mensagens · {self._n_erros()} erro(s)", 12,
                 ancora="midleft", sombra=False, cor=COR["texto2"])
        corpo = pygame.Rect(area.x, area.y + 28, area.w, area.h - 28)
        pygame.draw.rect(ui.surface, COR["campo"], corpo)
        cabem = max(1, corpo.h // 17)
        if getattr(self, "_rolagem_console_fim", False):
            self.rolagem_console = max(0, len(self.console) - cabem)
            self._rolagem_console_fim = False
        self.rolagem_console = getattr(self, "rolagem_console", 0)
        if livre and ent.roda and corpo.collidepoint(ent.mouse_tela):
            self.rolagem_console -= ent.roda * 3
        self.rolagem_console = max(0, min(self.rolagem_console, max(0, len(self.console) - cabem)))
        with recortar(ui, corpo):
            y = corpo.y + 2
            for hora, linha, tipo in self.console[self.rolagem_console:self.rolagem_console + cabem]:
                ui.texto(corpo.x + 6, y, hora, 12, sombra=False, cor=COR["texto2"])
                ui.texto(corpo.x + 66, y, linha, 12, sombra=False, cor=CORES.get(tipo, COR["texto"]))
                y += 17
