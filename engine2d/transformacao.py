"""Componente de transformação de um sprite (posição, rotação, escala)."""
from __future__ import annotations

import numpy as np

from . import matematica


class Transformacao:
    """Guarda Tx, Ty, θ, Sx, Sy e mantém a matriz de modelo em cache.

    A matriz só é recalculada quando alguma propriedade muda ("dirty flag").
    """

    __slots__ = ("_x", "_y", "_rotacao", "_sx", "_sy", "_matriz", "_suja")

    def __init__(self, x: float = 0.0, y: float = 0.0, rotacao: float = 0.0,
                 sx: float = 1.0, sy: float = 1.0):
        self._x = float(x)
        self._y = float(y)
        self._rotacao = float(rotacao)
        self._sx = float(sx)
        self._sy = float(sy)
        self._matriz = None
        self._suja = True

    # --- propriedades com invalidação do cache -------------------------------
    def _set(self, nome: str, valor: float) -> None:
        valor = float(valor)
        if getattr(self, nome) != valor:
            setattr(self, nome, valor)
            self._suja = True

    x = property(lambda s: s._x, lambda s, v: s._set("_x", v))
    y = property(lambda s: s._y, lambda s, v: s._set("_y", v))
    rotacao = property(lambda s: s._rotacao, lambda s, v: s._set("_rotacao", v))
    sx = property(lambda s: s._sx, lambda s, v: s._set("_sx", v))
    sy = property(lambda s: s._sy, lambda s, v: s._set("_sy", v))

    @property
    def posicao(self) -> tuple[float, float]:
        return self._x, self._y

    @posicao.setter
    def posicao(self, p) -> None:
        self.x, self.y = p

    # --- operações ---------------------------------------------------------
    def transladar(self, dx: float, dy: float) -> None:
        self.x = self._x + dx
        self.y = self._y + dy

    def rotacionar(self, graus: float) -> None:
        self.rotacao = (self._rotacao + graus) % 360.0

    def escalar(self, fx: float, fy: float | None = None) -> None:
        self.sx = self._sx * fx
        self.sy = self._sy * (fx if fy is None else fy)

    def matriz(self) -> np.ndarray:
        """Matriz de modelo M = T·R·S (sem o tamanho em pixels do sprite)."""
        if self._suja or self._matriz is None:
            self._matriz = matematica.modelo(self._x, self._y, self._rotacao, self._sx, self._sy)
            self._suja = False
        return self._matriz

    def __repr__(self) -> str:
        return (f"Transformacao(x={self._x:.1f}, y={self._y:.1f}, rot={self._rotacao:.1f}, "
                f"sx={self._sx:.2f}, sy={self._sy:.2f})")
