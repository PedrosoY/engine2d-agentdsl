"""Matrizes 3x3 em coordenadas homogêneas (2D).

Convenção: matrizes "linha-maior" do numpy; ao enviar para o OpenGL usamos
transpose=GL_TRUE. Um vértice v = (x, y, 1) é transformado por v' = M @ v.
"""
from __future__ import annotations

import math

import numpy as np


def translacao(tx: float, ty: float) -> np.ndarray:
    """Matriz T (eq. 3 do artigo)."""
    return np.array([[1.0, 0.0, tx],
                     [0.0, 1.0, ty],
                     [0.0, 0.0, 1.0]], dtype=np.float32)


def rotacao(theta_graus: float) -> np.ndarray:
    """Matriz R (eq. 4). Ângulo em graus, sentido anti-horário."""
    t = math.radians(theta_graus)
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, -s, 0.0],
                     [s, c, 0.0],
                     [0.0, 0.0, 1.0]], dtype=np.float32)


def escala(sx: float, sy: float) -> np.ndarray:
    """Matriz S (eq. 5)."""
    return np.array([[sx, 0.0, 0.0],
                     [0.0, sy, 0.0],
                     [0.0, 0.0, 1.0]], dtype=np.float32)


def modelo(tx: float, ty: float, theta_graus: float, sx: float, sy: float) -> np.ndarray:
    """M = T · R · S (eq. 6), calculada de forma fechada (sem 2 produtos matriciais).

    Equivale a translacao(tx,ty) @ rotacao(theta) @ escala(sx,sy).
    """
    t = math.radians(theta_graus)
    c, s = math.cos(t), math.sin(t)
    return np.array([[c * sx, -s * sy, tx],
                     [s * sx, c * sy, ty],
                     [0.0, 0.0, 1.0]], dtype=np.float32)


def modelo_vetorizado(tx, ty, theta_graus, sx, sy) -> np.ndarray:
    """Calcula N matrizes de modelo de uma vez. Entradas: arrays (N,).

    Retorna array (N, 3, 3) float32. Usado pelo renderizador em lote.
    """
    t = np.radians(theta_graus)
    c, s = np.cos(t), np.sin(t)
    n = len(tx)
    m = np.zeros((n, 3, 3), dtype=np.float32)
    m[:, 0, 0] = c * sx
    m[:, 0, 1] = -s * sy
    m[:, 0, 2] = tx
    m[:, 1, 0] = s * sx
    m[:, 1, 1] = c * sy
    m[:, 1, 2] = ty
    m[:, 2, 2] = 1.0
    return m


def ortografica(esquerda: float, direita: float, baixo: float, cima: float) -> np.ndarray:
    """Projeção ortográfica 2D: leva o retângulo do mundo para o NDC [-1, 1]²."""
    sx = 2.0 / (direita - esquerda)
    sy = 2.0 / (cima - baixo)
    tx = -(direita + esquerda) / (direita - esquerda)
    ty = -(cima + baixo) / (cima - baixo)
    return np.array([[sx, 0.0, tx],
                     [0.0, sy, ty],
                     [0.0, 0.0, 1.0]], dtype=np.float32)


def aplicar(m: np.ndarray, x: float, y: float) -> tuple[float, float]:
    """v' = M v (eq. 7) para um ponto."""
    v = m @ np.array([x, y, 1.0], dtype=np.float32)
    return float(v[0]), float(v[1])
