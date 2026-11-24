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


PREFIXO_EMBUTIDO = "embutido:"
# nome → (largura, altura) em pixels; 64 px = 1 "unidade" dos sprites padrão
FORMAS = {"quadrado": (64, 64), "circulo": (64, 64), "triangulo": (64, 64), "capsula": (64, 128),
          "losango": (64, 32), "hexagono": (64, 64), "hexagono_ponta": (64, 64),
          "quadrado_arredondado": (64, 64)}


def desenhar_forma(forma: str):
    """Pixels RGBA (já de cabeça para baixo, como o OpenGL espera) de uma forma branca com borda
    suave (desenhada 4x maior e reduzida)."""
    import math
    from PIL import ImageDraw
    if forma not in FORMAS:
        return None
    w, h = FORMAS[forma]
    k = 4
    W, H = w * k, h * k
    img = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    branco = (255, 255, 255, 255)
    if forma == "quadrado":
        d.rectangle((0, 0, W - 1, H - 1), fill=branco)
    elif forma == "circulo":
        d.ellipse((0, 0, W - 1, H - 1), fill=branco)
    elif forma == "triangulo":
        d.polygon([(W / 2, 0), (W - 1, H - 1), (0, H - 1)], fill=branco)
    elif forma == "capsula":
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=W // 2, fill=branco)
    elif forma == "losango":
        d.polygon([(W / 2, 0), (W - 1, H / 2), (W / 2, H - 1), (0, H / 2)], fill=branco)
    elif forma in ("hexagono", "hexagono_ponta"):
        base = 0 if forma == "hexagono" else 30
        pts = [(W / 2 + W / 2 * math.cos(math.radians(base + 60 * i)),
                H / 2 + H / 2 * math.sin(math.radians(base + 60 * i))) for i in range(6)]
        d.polygon(pts, fill=branco)
    elif forma == "quadrado_arredondado":
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=W // 4, fill=branco)
    img = img.resize((w, h), Image.LANCZOS).transpose(Image.FLIP_TOP_BOTTOM)
    return np.asarray(img, dtype=np.uint8)


class GerenciadorTexturas:
    """Cache por caminho: carregar o mesmo PNG duas vezes devolve a mesma textura."""

    def __init__(self, pasta_base: str | Path | None = None):
        self.pasta_base = Path(pasta_base) if pasta_base else None
        self._cache: dict[str, Textura] = {}
        self.faltando: set[str] = set()      # imagens que não abriram (avisa uma vez só)

    def carregar(self, caminho: str | Path, filtro_suave: bool | None = None) -> Textura:
        """``filtro_suave=None`` decide sozinho: imagens pequenas (até 32 px, pixel art) são
        ampliadas sem borrar (filtro NEAREST); as maiores usam filtro linear.
        Caminho vazio, arquivo que não existe ou que não é imagem: devolve a textura "sem imagem"
        (xadrez rosa) em vez de travar o jogo/editor."""
        if not str(caminho).strip():
            return self.sem_imagem()
        if str(caminho).startswith(PREFIXO_EMBUTIDO):
            return self.embutido(str(caminho)[len(PREFIXO_EMBUTIDO):])
        p = Path(caminho)
        if not p.is_absolute() and self.pasta_base is not None:
            p = self.pasta_base / p
        chave = str(p.resolve())
        if chave not in self._cache:
            try:
                if filtro_suave is None:
                    with Image.open(p) as im:
                        filtro_suave = max(im.size) > 32
                self._cache[chave] = Textura.de_arquivo(p, filtro_suave)
            except (OSError, ValueError) as e:
                if chave not in self.faltando:
                    self.faltando.add(chave)
                    print(f"[texturas] não consegui abrir a imagem '{caminho}': {e}")
                return self.sem_imagem()
        return self._cache[chave]

    def embutido(self, forma: str) -> Textura:
        """Sprite padrão da engine (branco, para tingir com a cor do SpriteRenderer)."""
        chave = PREFIXO_EMBUTIDO + forma
        if chave not in self._cache:
            px = desenhar_forma(forma)
            if px is None:
                return self.sem_imagem()
            self._cache[chave] = Textura(px, nome=forma, filtro_suave=True)
        return self._cache[chave]

    def sem_imagem(self) -> Textura:
        """Xadrez rosa e preto 32x32: aparece onde falta a imagem (fácil de ver e de clicar)."""
        if "<sem imagem>" not in self._cache:
            px = np.zeros((32, 32, 4), dtype=np.uint8)
            px[:, :] = (255, 0, 200, 255)
            for i in range(0, 32, 8):
                for j in range(0, 32, 8):
                    if (i + j) // 8 % 2:
                        px[i:i + 8, j:j + 8] = (30, 30, 30, 255)
            self._cache["<sem imagem>"] = Textura(px, nome="sem imagem", filtro_suave=False)
        return self._cache["<sem imagem>"]

    def eh_sem_imagem(self, tex) -> bool:
        return tex is self._cache.get("<sem imagem>")

    def registrar(self, nome: str, textura: Textura) -> Textura:
        self._cache[nome] = textura
        return textura

    @property
    def bytes_vram(self) -> int:
        return sum(t.bytes_vram for t in self._cache.values())

    def __len__(self) -> int:
        return len(self._cache)
