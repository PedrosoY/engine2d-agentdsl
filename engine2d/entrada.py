"""Entrada (teclado e mouse) consultável de qualquer componente."""
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
        self._usa_textinput = False        # vira True no primeiro evento TEXTINPUT do SDL
        # Teclas e botões segurados, vindos dos eventos. Junto com o estado do SDL, isso faz a
        # entrada funcionar também com eventos simulados (testes e o robô do editor).
        self._seguradas: set[str] = set()
        self._botoes: set[int] = set()
        # Em tela cheia o jogo é ampliado: converte o pixel do monitor para o pixel do jogo.
        self.converter_mouse = None

    def _pos(self, p):
        return self.converter_mouse(p) if self.converter_mouse else p

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
            self._seguradas.add(pygame.key.name(ev.key))
            ctrl = ev.mod & pygame.KMOD_CTRL and not ev.mod & pygame.KMOD_ALT   # AltGr = Ctrl+Alt no Windows
            if ev.unicode and ev.unicode.isprintable() and not ctrl and not self._usa_textinput:
                self.texto_digitado += ev.unicode
        elif ev.type == pygame.TEXTINPUT:
            # TEXTINPUT entrega o texto já composto (acentos, ç, AltGr); quando ele existe,
            # o unicode do KEYDOWN é ignorado para não duplicar letras.
            if not self._usa_textinput:
                self._usa_textinput = True
                self.texto_digitado = ""
            self.texto_digitado += ev.text
        elif ev.type == pygame.KEYUP:
            self._soltou.add(pygame.key.name(ev.key))
            self._seguradas.discard(pygame.key.name(ev.key))
        elif ev.type == pygame.MOUSEMOTION:
            self.mouse_tela = self._pos(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 2, 3):
            self.mouse_tela = self._pos(ev.pos)
            self._cliques.add(ev.button)
            self._botoes.add(ev.button)
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button in (1, 2, 3):
            self.mouse_tela = self._pos(ev.pos)
            self._soltos.add(ev.button)
            self._botoes.discard(ev.button)
        elif ev.type == pygame.MOUSEWHEEL:
            self.roda += ev.y
        elif ev.type in (getattr(pygame, "WINDOWFOCUSLOST", -1), getattr(pygame, "WINDOWLEAVE", -1)):
            self._seguradas.clear()           # soltou a tecla com a janela sem foco: não fica "presa"
            if ev.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
                self._botoes.clear()

    # --- teclado ----------------------------------------------------------------
    def tecla(self, nome: str) -> bool:
        """Tecla mantida pressionada (nomes do pygame: 'a', 'space', 'left', 'left shift'...)."""
        return nome in self._seguradas or bool(pygame.key.get_pressed()[pygame.key.key_code(nome)])

    def tecla_baixou(self, nome: str) -> bool:
        return nome in self._baixou

    def tecla_soltou(self, nome: str) -> bool:
        return nome in self._soltou

    def eixo(self, negativo: tuple, positivo: tuple) -> float:
        n = any(self.tecla(k) for k in negativo)
        q = any(self.tecla(k) for k in positivo)
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
        return botao in self._botoes or bool(pygame.mouse.get_pressed()[botao - 1])

    def consumir_clique(self) -> None:
        self.clique_consumido = True

    @property
    def mouse_mundo(self) -> tuple[float, float]:
        return self.motor.camera.tela_para_mundo(*self.mouse_tela)
