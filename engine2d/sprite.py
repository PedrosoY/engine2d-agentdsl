"""Representação de um sprite: S = {Tx, Ty, θ, Sx, Sy, L, I} (eq. 1)."""
from __future__ import annotations

import itertools

import numpy as np

from . import matematica
from .transformacao import Transformacao

_contador = itertools.count()


class Sprite:
    """Objeto gráfico independente da cena.

    - ``textura`` (I): referência a uma Textura (pode ser compartilhada).
    - ``transformacao``: posição, rotação e escala próprias.
    - ``camada`` (L): inteiro; camadas menores são desenhadas antes (eq. 8).
    - ``largura``/``altura``: tamanho em pixels (padrão = tamanho da textura).
    - ``cor``: tint RGBA multiplicado pela textura no fragment shader.
    - ``regiao_uv``: (u0, v0, u1, v1) para usar só parte da imagem (spritesheet).
    - ``espaco_tela``: se True, ignora a câmera (HUD/interface).
    """

    def __init__(self, textura, x: float = 0.0, y: float = 0.0, camada: int = 0,
                 rotacao: float = 0.0, sx: float = 1.0, sy: float = 1.0,
                 largura: float | None = None, altura: float | None = None,
                 cor=(1.0, 1.0, 1.0, 1.0), nome: str | None = None,
                 espaco_tela: bool = False):
        self.id = next(_contador)
        self.nome = nome or f"sprite_{self.id}"
        self.textura = textura
        self.transformacao = Transformacao(x, y, rotacao, sx, sy)
        self._camada = int(camada)
        self.largura = float(largura if largura is not None else textura.largura)
        self.altura = float(altura if altura is not None else textura.altura)
        self.cor = tuple(float(c) for c in cor)
        self.regiao_uv = (0.0, 0.0, 1.0, 1.0)
        self.visivel = True
        self.espaco_tela = espaco_tela
        self.lista = None  # preenchido por ListaRenderizacao.adicionar
        self.dados: dict = {}  # espaço livre para a aplicação (ex.: agente da DSL)

    # A camada avisa a lista de renderização para reordenar no próximo quadro.
    @property
    def camada(self) -> int:
        return self._camada

    @camada.setter
    def camada(self, valor: int) -> None:
        valor = int(valor)
        if valor != self._camada:
            self._camada = valor
            if self.lista is not None:
                self.lista.marcar_reordenar()

    # Atalhos para a transformação
    @property
    def x(self) -> float:
        return self.transformacao.x

    @x.setter
    def x(self, v: float) -> None:
        self.transformacao.x = v

    @property
    def y(self) -> float:
        return self.transformacao.y

    @y.setter
    def y(self, v: float) -> None:
        self.transformacao.y = v

    def matriz_final(self) -> np.ndarray:
        """M · Tamanho: leva o quad unitário [-0.5, 0.5]² para o mundo."""
        t = self.transformacao
        # Forma fechada de T·R·S·Tamanho (evita dois produtos matriciais por sprite).
        return matematica.modelo(t.x, t.y, t.rotacao, t.sx * self.largura, t.sy * self.altura)

    def contem_ponto(self, px: float, py: float) -> bool:
        """Teste de seleção (picking): leva o ponto para o espaço local do quad."""
        m = self.matriz_final()
        if abs(m[0, 0] * m[1, 1] - m[0, 1] * m[1, 0]) < 1e-9:
            return False   # escala ou tamanho zero: o sprite não tem área (e a matriz não tem inversa)
        inv = np.linalg.inv(m)
        lx, ly = matematica.aplicar(inv, px, py)
        return -0.5 <= lx <= 0.5 and -0.5 <= ly <= 0.5

    def __repr__(self) -> str:
        return f"Sprite({self.nome!r}, camada={self._camada}, {self.transformacao})"
