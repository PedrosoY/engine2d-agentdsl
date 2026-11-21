"""Entrada (teclado e mouse) consultável de qualquer componente, como o Input da Unity."""
from __future__ import annotations

import pygame


class Entrada:
    def __init__(self, motor):
        self.motor = motor
        self._baixou: set[str] = set()
        self._soltou: set[str] = set()
        self.mouse_tela = (0, 0)          # pixels, origem no topo-esquerdo
        self._cliques: set[int] = set()
        self._soltos: set[int] = set()
        self.roda = 0
        self.texto_digitado = ""
        self.clique_consumido = False      # a UI "come" o clique para o jogo não recebê-lo

    def novo_quadro(self) -> None:
        self._baixou.clear()
        self._soltou.clear()
        self._cliques.clear()
        self._soltos.clear()
        self.roda = 0
        self.texto_digitado = ""
        self.clique_consumido = False

    def processar(self, ev) -> None:
        if ev.type == pygame.KEYDOWN:
            self._baixou.add(pygame.key.name(ev.key))
            if ev.unicode and ev.unicode.isprintable():
                self.texto_digitado += ev.unicode
        elif ev.type == pygame.KEYUP:
            self._soltou.add(pygame.key.name(ev.key))
        elif ev.type == pygame.MOUSEMOTION:
            self.mouse_tela = ev.pos
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 2, 3):
            self.mouse_tela = ev.pos
            self._cliques.add(ev.button)
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button in (1, 2, 3):
            self._soltos.add(ev.button)
        elif ev.type == pygame.MOUSEWHEEL:
            self.roda += ev.y

    # --- teclado ----------------------------------------------------------------
    def tecla(self, nome: str) -> bool:
        """Tecla mantida pressionada (nomes do pygame: 'a', 'space', 'left', 'left shift'...)."""
        return pygame.key.get_pressed()[pygame.key.key_code(nome)]

    def tecla_baixou(self, nome: str) -> bool:
        return nome in self._baixou

    def tecla_soltou(self, nome: str) -> bool:
        return nome in self._soltou

    def eixo(self, negativo: tuple, positivo: tuple) -> float:
        p = pygame.key.get_pressed()
        n = any(p[pygame.key.key_code(k)] for k in negativo)
        q = any(p[pygame.key.key_code(k)] for k in positivo)
        return float(q) - float(n)

    def direcao_wasd(self) -> tuple[float, float]:
        x = self.eixo(("a", "left"), ("d", "right"))
        y = self.eixo(("s", "down"), ("w", "up"))
        n = (x * x + y * y) ** 0.5
        return (x / n, y / n) if n else (0.0, 0.0)

    # --- mouse ------------------------------------------------------------------------
    def clicou(self, botao: int = 1) -> bool:
        return botao in self._cliques and not (botao == 1 and self.clique_consumido)

    def soltou_mouse(self, botao: int = 1) -> bool:
        return botao in self._soltos

    def mouse_pressionado(self, botao: int = 1) -> bool:
        return pygame.mouse.get_pressed()[botao - 1]

    def consumir_clique(self) -> None:
        self.clique_consumido = True

    @property
    def mouse_mundo(self) -> tuple[float, float]:
        return self.motor.camera.tela_para_mundo(*self.mouse_tela)
