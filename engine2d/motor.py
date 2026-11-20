"""Janela, contexto OpenGL e loop principal da engine."""
from __future__ import annotations

import time
from collections import deque
from pathlib import Path

import numpy as np
import pygame
from OpenGL import GL

from .camera import Camera2D
from .cena import Cena
from .renderizador import Renderizador
from .sprite import Sprite
from .textura import GerenciadorTexturas, Textura


class Motor:
    """Ponto de entrada da engine.

    Loop (seção III-H do artigo):
        processar eventos → atualizar objetos → ordenar por camada →
        limpar framebuffer → desenhar sprites → apresentar framebuffer
    """

    def __init__(self, largura: int = 1280, altura: int = 720, titulo: str = "Engine2D",
                 vsync: bool = True, visivel: bool = True, modo_render: str = "lote",
                 pasta_assets: str | Path | None = None):
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        if not visivel:
            flags |= pygame.HIDDEN
        pygame.display.set_mode((largura, altura), flags, vsync=1 if vsync else 0)
        pygame.display.set_caption(titulo)
        self.titulo = titulo
        self.largura, self.altura = largura, altura

        self.texturas = GerenciadorTexturas(pasta_assets)
        self.renderizador = Renderizador(largura, altura, modo_render)
        self.cena = Cena()
        self.camera = Camera2D(largura, altura)
        self.rodando = False
        self.tempo_total = 0.0
        self.quadro = 0
        self._tempos_quadro = deque(maxlen=120)
        self.info_gl = {
            "renderer": GL.glGetString(GL.GL_RENDERER).decode(errors="ignore"),
            "versao": GL.glGetString(GL.GL_VERSION).decode(errors="ignore"),
        }

    # --- atalhos ----------------------------------------------------------
    def carregar_textura(self, caminho) -> Textura:
        return self.texturas.carregar(caminho)

    def criar_sprite(self, textura, **kw) -> Sprite:
        if isinstance(textura, (str, Path)):
            textura = self.carregar_textura(textura)
        return self.cena.adicionar(Sprite(textura, **kw))

    @property
    def fps_medio(self) -> float:
        if not self._tempos_quadro:
            return 0.0
        return 1.0 / max(np.mean(self._tempos_quadro), 1e-9)

    @property
    def ms_quadro_medio(self) -> float:
        return float(np.mean(self._tempos_quadro) * 1000) if self._tempos_quadro else 0.0

    # --- um quadro --------------------------------------------------------
    def renderizar_quadro(self) -> None:
        self.renderizador.limpar()
        self.renderizador.desenhar(self.cena, self.camera)
        pygame.display.flip()

    def executar(self, atualizar=None, ao_evento=None, max_quadros: int | None = None) -> None:
        """Roda o loop até a janela fechar (ou ``max_quadros``).

        ``atualizar(motor, dt)`` é chamado a cada quadro;
        ``ao_evento(motor, evento)`` recebe cada evento do pygame.
        """
        self.rodando = True
        anterior = time.perf_counter()
        while self.rodando:
            agora = time.perf_counter()
            dt = min(agora - anterior, 0.1)
            anterior = agora
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                    self.rodando = False
                elif ao_evento:
                    ao_evento(self, ev)
            if atualizar:
                atualizar(self, dt)
            self.renderizar_quadro()
            self._tempos_quadro.append(dt)
            self.tempo_total += dt
            self.quadro += 1
            if max_quadros is not None and self.quadro >= max_quadros:
                self.rodando = False

    def capturar_tela(self, caminho) -> None:
        """Salva o framebuffer atual (o último quadro desenhado) como PNG."""
        from PIL import Image
        self.renderizador.limpar()
        self.renderizador.desenhar(self.cena, self.camera)
        GL.glPixelStorei(GL.GL_PACK_ALIGNMENT, 1)
        dados = GL.glReadPixels(0, 0, self.largura, self.altura, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
        img = Image.frombytes("RGBA", (self.largura, self.altura), dados)
        img.transpose(Image.FLIP_TOP_BOTTOM).save(caminho)

    def encerrar(self) -> None:
        pygame.quit()


class TextoHUD:
    """Texto em espaço de tela: o pygame desenha a fonte numa Surface e ela vira textura."""

    def __init__(self, motor: Motor, x: float = 10, y_topo: float = 10, tamanho: int = 18,
                 cor=(235, 235, 235)):
        self.motor = motor
        self.fonte = pygame.font.SysFont("consolas", tamanho)
        self.cor = cor
        self.x, self.y_topo = x, y_topo
        self._texto = None
        self.textura = Textura(np.zeros((1, 1, 4), np.uint8), nome="hud")
        self.sprite = motor.cena.adicionar(Sprite(self.textura, camada=10_000, espaco_tela=True, nome="hud"))

    def definir(self, texto: str) -> None:
        if texto == self._texto:
            return
        self._texto = texto
        linhas = texto.split("\n")
        sups = [self.fonte.render(l, True, self.cor) for l in linhas]
        w = max(s.get_width() for s in sups) + 12
        h = sum(s.get_height() for s in sups) + 10
        alvo = pygame.Surface((w, h), pygame.SRCALPHA)
        alvo.fill((0, 0, 0, 150))
        y = 5
        for s in sups:
            alvo.blit(s, (6, y))
            y += s.get_height()
        pixels = pygame.surfarray.pixels3d(alvo).swapaxes(0, 1)
        alfa = pygame.surfarray.pixels_alpha(alvo).swapaxes(0, 1)
        rgba = np.dstack([pixels, alfa])[::-1]  # inverte: linha 0 embaixo
        self.textura.atualizar(rgba)
        sp = self.sprite
        sp.largura, sp.altura = w, h
        sp.x = self.x + w / 2
        sp.y = self.motor.altura - self.y_topo - h / 2
