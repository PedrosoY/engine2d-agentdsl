"""Carregamento de imagens (PNG) e gerenciamento de texturas OpenGL."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from OpenGL import GL
from PIL import Image


class Textura:
    """Textura RGBA na GPU. Uma mesma textura pode ser usada por vários sprites."""

    def __init__(self, pixels: np.ndarray, nome: str = "", filtro_suave: bool = True):
        self.nome = nome
        self.id = GL.glGenTextures(1)
        self.filtro_suave = filtro_suave
        self.largura = 0
        self.altura = 0
        self.atualizar(pixels)

    @classmethod
    def de_arquivo(cls, caminho: str | Path, filtro_suave: bool = True) -> "Textura":
        img = Image.open(caminho).convert("RGBA")
        # A imagem tem a linha 0 no topo; no OpenGL a coordenada v=0 é embaixo.
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
        return cls(np.asarray(img, dtype=np.uint8), nome=Path(caminho).stem, filtro_suave=filtro_suave)

    @classmethod
    def cor_solida(cls, rgba=(255, 255, 255, 255), tamanho: int = 4) -> "Textura":
        pixels = np.zeros((tamanho, tamanho, 4), dtype=np.uint8)
        pixels[:, :] = rgba
        return cls(pixels, nome="solida")

    def atualizar(self, pixels: np.ndarray) -> None:
        """(Re)envia os pixels (altura, largura, 4) para a GPU."""
        pixels = np.ascontiguousarray(pixels, dtype=np.uint8)
        self.altura, self.largura = pixels.shape[:2]
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.id)
        filtro = GL.GL_LINEAR if self.filtro_suave else GL.GL_NEAREST
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, filtro)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, filtro)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, self.largura, self.altura, 0,
                        GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, pixels)

    @property
    def bytes_vram(self) -> int:
        return self.largura * self.altura * 4

    def liberar(self) -> None:
        GL.glDeleteTextures([self.id])


class AtlasTexturas:
    """Junta várias imagens numa única textura (empacotamento em prateleiras).

    Com todos os sprites usando a mesma textura, o renderizador em lote desenha
    a cena inteira em UMA chamada, mantendo exatamente a ordem das camadas.
    Cada imagem vira uma região (u0, v0, u1, v1) do atlas. As bordas são
    estendidas em ``margem`` pixels para evitar "sangramento" na filtragem linear.
    """

    def __init__(self, caminhos, largura_max: int = 2048, margem: int = 2):
        imagens = []
        for c in caminhos:
            img = Image.open(c).convert("RGBA").transpose(Image.FLIP_TOP_BOTTOM)
            px = np.asarray(img, dtype=np.uint8)
            px = np.pad(px, ((margem, margem), (margem, margem), (0, 0)), mode="edge")
            imagens.append((Path(c).name, px))
        # Prateleiras: ordena por altura decrescente e preenche linha a linha.
        imagens.sort(key=lambda t: -t[1].shape[0])
        x = y = altura_prateleira = 0
        posicoes = {}
        for nome, px in imagens:
            h, w = px.shape[:2]
            if x + w > largura_max:
                x, y, altura_prateleira = 0, y + altura_prateleira, 0
            posicoes[nome] = (x, y, w, h)
            x += w
            altura_prateleira = max(altura_prateleira, h)
        largura = 1
        while largura < max(p[0] + p[2] for p in posicoes.values()):
            largura *= 2
        altura = 1
        while altura < y + altura_prateleira:
            altura *= 2
        atlas = np.zeros((altura, largura, 4), dtype=np.uint8)
        self.regioes: dict[str, tuple[float, float, float, float]] = {}
        self.tamanhos: dict[str, tuple[int, int]] = {}
        for nome, px in imagens:
            x, y, w, h = posicoes[nome]
            atlas[y:y + h, x:x + w] = px
            # Região sem a margem
            x0, y0, x1, y1 = x + margem, y + margem, x + w - margem, y + h - margem
            self.regioes[nome] = (x0 / largura, y0 / altura, x1 / largura, y1 / altura)
            self.tamanhos[nome] = (w - 2 * margem, h - 2 * margem)
        self.textura = Textura(atlas, nome="atlas")

    def configurar(self, sprite, nome: str):
        """Faz o sprite usar a imagem ``nome`` do atlas."""
        sprite.textura = self.textura
        sprite.regiao_uv = self.regioes[nome]
        sprite.largura, sprite.altura = self.tamanhos[nome]
        return sprite


class GerenciadorTexturas:
    """Cache por caminho: carregar o mesmo PNG duas vezes devolve a mesma textura."""

    def __init__(self, pasta_base: str | Path | None = None):
        self.pasta_base = Path(pasta_base) if pasta_base else None
        self._cache: dict[str, Textura] = {}

    def carregar(self, caminho: str | Path, filtro_suave: bool = True) -> Textura:
        p = Path(caminho)
        if not p.is_absolute() and self.pasta_base is not None:
            p = self.pasta_base / p
        chave = str(p.resolve())
        if chave not in self._cache:
            self._cache[chave] = Textura.de_arquivo(p, filtro_suave)
        return self._cache[chave]

    def registrar(self, nome: str, textura: Textura) -> Textura:
        self._cache[nome] = textura
        return textura

    @property
    def bytes_vram(self) -> int:
        return sum(t.bytes_vram for t in self._cache.values())

    def __len__(self) -> int:
        return len(self._cache)
