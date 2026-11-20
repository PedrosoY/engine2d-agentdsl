"""Câmera 2D: pan (x, y), zoom e rotação."""
from __future__ import annotations

import numpy as np

from . import matematica


class Camera2D:
    """A câmera define qual retângulo do mundo aparece na janela.

    (x, y) é o ponto do mundo que fica no centro da tela.
    """

    def __init__(self, largura: int, altura: int):
        self.largura = largura
        self.altura = altura
        self.x = largura / 2
        self.y = altura / 2
        self.zoom = 1.0
        self.rotacao = 0.0

    def view(self) -> np.ndarray:
        """Matriz de visão: inversa da transformação da câmera."""
        return (matematica.escala(self.zoom, self.zoom)
                @ matematica.rotacao(-self.rotacao)
                @ matematica.translacao(-self.x, -self.y))

    def projecao(self) -> np.ndarray:
        w, h = self.largura / 2, self.altura / 2
        return matematica.ortografica(-w, w, -h, h)

    def view_proj(self) -> np.ndarray:
        return self.projecao() @ self.view()

    def tela_para_mundo(self, px: float, py_topo: float) -> tuple[float, float]:
        """Converte coordenada do mouse (origem no topo-esquerdo) para o mundo."""
        nx = px - self.largura / 2
        ny = (self.altura - py_topo) - self.altura / 2
        inv = np.linalg.inv(self.view())
        return matematica.aplicar(inv, nx, ny)

    def redimensionar(self, largura: int, altura: int) -> None:
        self.largura, self.altura = largura, altura
