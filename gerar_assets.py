"""Gera os PNGs (com canal alfa) usados pelas demos, para não depender de imagens externas."""
from pathlib import Path

from PIL import Image, ImageDraw

PASTA = Path(__file__).parent / "assets"


def _salvar(img: Image.Image, nome: str) -> None:
    PASTA.mkdir(exist_ok=True)
    img.save(PASTA / nome)


def circulo(nome, cor, tam=64):
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, tam - 3, tam - 3), fill=cor, outline=(255, 255, 255, 255), width=3)
    _salvar(img, nome)


def personagem(nome, cor, tam=64):
    """Corpo redondo com olhos voltados para a direita (mostra a rotação)."""
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, tam - 5, tam - 5), fill=cor, outline=(20, 20, 20, 255), width=3)
    for oy in (20, 36):
        d.ellipse((38, oy, 50, oy + 10), fill=(255, 255, 255, 255))
        d.ellipse((44, oy + 3, 49, oy + 8), fill=(0, 0, 0, 255))
    _salvar(img, nome)


def estrela(nome, cor, tam=64):
    import math
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = tam / 2
    pts = []
    for i in range(10):
        r = c - 3 if i % 2 == 0 else c * 0.42
        a = math.pi / 2 + i * math.pi / 5
        pts.append((c + r * math.cos(a), c - r * math.sin(a)))
    d.polygon(pts, fill=cor, outline=(255, 255, 255, 255))
    _salvar(img, nome)


def caixa(nome, cor, tam=64):
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((2, 2, tam - 3, tam - 3), fill=cor, outline=(30, 30, 30, 255), width=4)
    d.line((2, 2, tam - 3, tam - 3), fill=(30, 30, 30, 255), width=3)
    d.line((2, tam - 3, tam - 3, 2), fill=(30, 30, 30, 255), width=3)
    _salvar(img, nome)


def chao(nome, tam=256):
    img = Image.new("RGBA", (tam, tam), (46, 70, 52, 255))
    d = ImageDraw.Draw(img)
    passo = tam // 8
    for i in range(8):
        for j in range(8):
            if (i + j) % 2 == 0:
                d.rectangle((i * passo, j * passo, (i + 1) * passo - 1, (j + 1) * passo - 1),
                            fill=(52, 80, 58, 255))
    _salvar(img, nome)


def nuvem(nome, tam=128):
    """Semitransparente, para testar alpha blending entre camadas."""
    img = Image.new("RGBA", (tam, tam // 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for (x, y, r) in ((30, 38, 24), (60, 28, 30), (92, 38, 24)):
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 140))
    _salvar(img, nome)


def gerar():
    personagem("jogador.png", (70, 140, 255, 255))
    personagem("guarda.png", (230, 80, 70, 255))
    personagem("fujao.png", (250, 200, 60, 255))
    circulo("bola.png", (120, 220, 140, 255))
    estrela("estrela.png", (255, 215, 0, 255))
    caixa("caixa.png", (176, 120, 66, 255))
    chao("chao.png")
    nuvem("nuvem.png")
    return sorted(p.name for p in PASTA.glob("*.png"))


if __name__ == "__main__":
    print("Gerados:", ", ".join(gerar()))
