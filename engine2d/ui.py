"""Camada de interface em modo imediato.

A cada quadro os componentes desenham textos, barras e botões numa Surface do
pygame (CPU); no fim do quadro ela é enviada como UMA textura e desenhada por
cima da cena com projeção de tela. Coordenadas em pixels, origem no topo-esquerdo.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pygame

from .sprite import Sprite
from .textura import Textura

CORES = {
    "texto": (240, 240, 240), "fundo": (20, 22, 30, 215), "borda": (90, 100, 120),
    "botao": (52, 60, 80), "botao_hover": (72, 84, 112), "botao_off": (40, 42, 50),
    "destaque": (255, 200, 60), "verde": (90, 200, 110), "vermelho": (220, 70, 70), "azul": (80, 150, 240),
}


class CamadaUI:
    def __init__(self, motor):
        self.motor = motor
        self.largura, self.altura = motor.largura, motor.altura
        self.surface = pygame.Surface((self.largura, self.altura), pygame.SRCALPHA)
        self._fontes: dict[tuple, pygame.font.Font] = {}
        self._imagens: dict[tuple, pygame.Surface] = {}
        self._cache_texto: dict[tuple, pygame.Surface] = {}
        self.textura = Textura(np.zeros((self.altura, self.largura, 4), np.uint8), nome="ui")
        # sy = -1: a GPU vira a imagem (a Surface tem a linha 0 em cima), sem copiar na CPU
        self.sprite = Sprite(self.textura, x=self.largura / 2, y=self.altura / 2, sy=-1.0,
                             camada=1_000_000, espaco_tela=True, nome="ui")
        self.areas_bloqueadas: list[pygame.Rect] = []   # regiões da UI (o jogo ignora cliques nelas)
        self.sujo = False
        self._formato_gl = None
        self._sobreposicoes: list = []
        self._tardias: list = []       # desenhadas depois da UI normal (janelas flutuantes), sem ser modal
        self._areas_anteriores: list = []
        self._modal_ativo = False      # havia janela modal no quadro anterior
        self._modal_proximo = False
        self._em_sobreposicao = False

    def redimensionar(self, largura: int, altura: int) -> None:
        self.largura, self.altura = largura, altura
        self.surface = pygame.Surface((largura, altura), pygame.SRCALPHA)
        self.textura.atualizar(np.zeros((altura, largura, 4), np.uint8))
        self.sprite.largura, self.sprite.altura = largura, altura
        self.sprite.x, self.sprite.y = largura / 2, altura / 2

    # --- ciclo -----------------------------------------------------------------
    def limpar(self) -> None:
        self.surface.fill((0, 0, 0, 0))
        # A lógica do jogo roda ANTES da UI ser desenhada: ela consulta as áreas do quadro anterior.
        self._areas_anteriores = self.areas_bloqueadas
        self.areas_bloqueadas = []
        self._modal_ativo = self._modal_proximo
        self._modal_proximo = False
        self.sujo = False
        if len(self._cache_texto) > 2000:
            self._cache_texto.clear()

    def enviar(self) -> None:
        """Sobe a Surface para a GPU sem cópia na CPU.

        Os pixels são lidos direto da memória da Surface (BGRA, em geral) e enviados com
        o formato correspondente; a inversão vertical é feita pelo sprite com sy = -1.
        """
        from OpenGL import GL
        if self._formato_gl is None:
            r_mask = self.surface.get_masks()[0]
            self._formato_gl = GL.GL_BGRA if r_mask == 0xFF0000 else GL.GL_RGBA
        dados = np.frombuffer(self.surface.get_buffer(), dtype=np.uint8)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.textura.id)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)
        GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, self.surface.get_pitch() // 4)
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, self.largura, self.altura,
                           self._formato_gl, GL.GL_UNSIGNED_BYTE, dados)
        GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, 0)

    def depois(self, funcao) -> None:
        """Agenda ``funcao(ui)`` para desenhar depois da UI normal e antes das janelas modais."""
        self._tardias.append(funcao)

    def desenhar_tardias(self) -> None:
        pend, self._tardias = self._tardias, []
        for f in pend:
            f(self)

    def sobrepor(self, funcao) -> None:
        """Agenda ``funcao(ui)`` para desenhar DEPOIS de todo o resto (janelas modais)."""
        self._sobreposicoes.append(funcao)

    def desenhar_sobreposicoes(self) -> None:
        pend, self._sobreposicoes = self._sobreposicoes, []
        self._modal_proximo = bool(pend)
        self._em_sobreposicao = True
        for f in pend:
            f(self)
        self._em_sobreposicao = False

    def mouse_sobre_ui(self) -> bool:
        mx, my = self.motor.entrada.mouse_tela
        if self._modal_ativo:
            return True
        return any(r.collidepoint(mx, my) for r in self.areas_bloqueadas + self._areas_anteriores)

    # --- recursos ---------------------------------------------------------------
    def fonte(self, tamanho: int = 18, negrito: bool = False, arquivo: str | None = None) -> pygame.font.Font:
        """Fonte do sistema (Segoe UI) ou um arquivo .ttf do projeto (``arquivo``)."""
        k = (tamanho, negrito, arquivo or "")
        if k not in self._fontes:
            f = None
            if arquivo:
                p = Path(arquivo)
                if not p.is_absolute() and self.motor.texturas.pasta_base:
                    p = self.motor.texturas.pasta_base / p
                try:
                    f = pygame.font.Font(str(p), tamanho)
                    f.set_bold(negrito)
                except (OSError, pygame.error) as e:
                    print(f"[ui] fonte '{arquivo}': {e}")
            self._fontes[k] = f or pygame.font.SysFont("segoeui,arial", tamanho, bold=negrito)
        return self._fontes[k]

    def imagem(self, caminho: str, tamanho: int | None = None) -> pygame.Surface:
        k = (caminho, tamanho)
        if k not in self._imagens:
            from .textura import PREFIXO_EMBUTIDO, desenhar_forma
            if str(caminho).startswith(PREFIXO_EMBUTIDO):      # sprite padrão da engine
                px = desenhar_forma(str(caminho)[len(PREFIXO_EMBUTIDO):])
                px = np.ascontiguousarray(px[::-1])
                img = pygame.image.frombuffer(px.tobytes(), (px.shape[1], px.shape[0]), "RGBA").convert_alpha()
            else:
                p = Path(caminho)
                if not p.is_absolute() and self.motor.texturas.pasta_base:
                    p = self.motor.texturas.pasta_base / p
                img = pygame.image.load(str(p)).convert_alpha()
            if tamanho:
                w, h = img.get_size()
                f = tamanho / max(w, h)
                novo = (max(1, int(w * f)), max(1, int(h * f)))
                # pixel art (imagens pequenas) é ampliada sem borrar
                img = pygame.transform.scale(img, novo) if max(w, h) <= 32 else pygame.transform.smoothscale(img, novo)
            self._imagens[k] = img
        return self._imagens[k]

    # --- primitivas ---------------------------------------------------------------
    def bloquear(self, rect) -> pygame.Rect:
        r = pygame.Rect(rect)
        self.areas_bloqueadas.append(r)
        return r

    def retangulo(self, rect, cor=CORES["fundo"], borda=None, raio: int = 6, bloquear: bool = False):
        r = pygame.Rect(rect)
        if len(cor) == 4 and cor[3] < 255:
            tmp = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.rect(tmp, cor, tmp.get_rect(), border_radius=raio)
            self.surface.blit(tmp, r.topleft)
        else:
            pygame.draw.rect(self.surface, cor, r, border_radius=raio)
        if borda:
            pygame.draw.rect(self.surface, borda, r, 1, border_radius=raio)
        if bloquear:
            self.bloquear(r)
        return r

    def texto(self, x, y, texto, tamanho=18, cor=CORES["texto"], ancora="topleft", negrito=False,
              sombra=True, fonte: str | None = None, alfa: int = 255) -> pygame.Rect:
        k = (texto, tamanho, cor, negrito, fonte)
        surf = self._cache_texto.get(k)
        if surf is None:
            surf = self.fonte(tamanho, negrito, fonte).render(str(texto), True, cor[:3])
            self._cache_texto[k] = surf
        r = surf.get_rect(**{ancora: (int(x), int(y))})
        if sombra:
            sk = (texto, tamanho, (0, 0, 0), negrito, fonte)
            s2 = self._cache_texto.get(sk)
            if s2 is None:
                s2 = self.fonte(tamanho, negrito, fonte).render(str(texto), True, (0, 0, 0))
                self._cache_texto[sk] = s2
            if alfa < 255:
                s2 = s2.copy()
                s2.set_alpha(alfa)
            self.surface.blit(s2, r.move(1, 1))
        if alfa < 255:
            surf = surf.copy()
            surf.set_alpha(alfa)
        self.surface.blit(surf, r)
        return r

    def barra(self, rect, fracao, cor=CORES["verde"], fundo=(40, 40, 50, 220), texto=None, tamanho=14):
        r = pygame.Rect(rect)
        self.retangulo(r, fundo, raio=4)
        f = max(0.0, min(1.0, fracao))
        if f > 0:
            pygame.draw.rect(self.surface, cor, (r.x, r.y, max(2, int(r.w * f)), r.h), border_radius=4)
        pygame.draw.rect(self.surface, (0, 0, 0), r, 1, border_radius=4)
        if texto:
            self.texto(r.centerx, r.centery, texto, tamanho, ancora="center")

    def desenhar_imagem(self, caminho, x, y, tamanho=None, ancora="center", alfa=255):
        img = self.imagem(caminho, tamanho)
        if alfa < 255:
            img = img.copy()
            img.set_alpha(alfa)
        r = img.get_rect(**{ancora: (int(x), int(y))})
        self.surface.blit(img, r)
        return r

    def botao(self, rect, rotulo="", ativo=True, imagem=None, tamanho_texto=16, selecionado=False,
              dica=None) -> bool:
        """Desenha um botão e devolve True no quadro em que ele é clicado."""
        r = self.bloquear(rect)
        ent = self.motor.entrada
        # com uma janela modal aberta, só os botões dela respondem
        hover = r.collidepoint(ent.mouse_tela) and (self._em_sobreposicao or not self._modal_ativo)
        cor = CORES["botao_off"] if not ativo else (CORES["botao_hover"] if hover else CORES["botao"])
        self.retangulo(r, cor, borda=CORES["destaque"] if selecionado else CORES["borda"])
        if imagem:
            self.desenhar_imagem(imagem, r.centerx, r.centery - (8 if rotulo else 0),
                                 tamanho=min(r.w, r.h) - (22 if rotulo else 10), alfa=255 if ativo else 110)
            if rotulo:
                self.texto(r.centerx, r.bottom - 4, rotulo, 13, ancora="midbottom",
                           cor=CORES["texto"] if ativo else (140, 140, 140))
        else:
            self.texto(r.centerx, r.centery, rotulo, tamanho_texto, ancora="center",
                       cor=CORES["texto"] if ativo else (140, 140, 140))
        if hover and dica:
            self._dica = (dica, ent.mouse_tela)
        if hover and ent.clicou(1):
            ent.consumir_clique()
            return ativo
        return False

    def circulo(self, centro, raio, cor, largura=0):
        if len(cor) == 4 and cor[3] < 255:
            r = int(raio) + 2
            tmp = pygame.Surface((2 * r, 2 * r), pygame.SRCALPHA)
            pygame.draw.circle(tmp, cor, (r, r), int(raio), largura)
            self.surface.blit(tmp, (int(centro[0]) - r, int(centro[1]) - r))
        else:
            pygame.draw.circle(self.surface, cor, (int(centro[0]), int(centro[1])), int(raio), largura)

    def linha(self, a, b, cor, largura=1):
        pygame.draw.line(self.surface, cor, a, b, largura)

    def mundo_para_tela(self, x, y) -> tuple[float, float]:
        cam = self.motor.camera
        from . import matematica as M
        v = cam.view()
        px, py = M.aplicar(v, x, y)
        return px + cam.largura / 2, cam.altura / 2 - py

    def desenhar_dicas(self):
        d = getattr(self, "_dica", None)
        if d:
            texto, (mx, my) = d
            linhas = texto.split("\n")
            w = max(self.fonte(14).size(l)[0] for l in linhas) + 14
            h = 18 * len(linhas) + 8
            x = min(mx + 14, self.largura - w - 4)
            y = min(my + 14, self.altura - h - 4)
            self.retangulo((x, y, w, h), (10, 10, 14, 235), borda=CORES["borda"])
            for i, l in enumerate(linhas):
                self.texto(x + 7, y + 4 + 18 * i, l, 14, sombra=False)
            self._dica = None
