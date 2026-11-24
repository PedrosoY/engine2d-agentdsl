"""Custo da iluminação 2D: tempo por quadro com 2 000 sprites e quantidades crescentes de luzes,
sem e com sombras (volumes de sombra no stencil).

    python benchmark_luzes.py        → resultados/luzes.csv e resultados/luzes.png
"""
import csv
import random
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from OpenGL import GL  # noqa: E402

from engine2d import Cena, Colisor, Luz2D, Motor, ProjetorSombra2D, SpriteRenderer  # noqa: E402

LUZES = [0, 1, 10, 50, 100, 200]
SPRITES = 2000
QUADROS = 120


def medir(n_luzes, sombras, projetores=40):
    random.seed(1)
    m = Motor(1280, 720, visivel=False, editor=False, vsync=False, pasta_assets=RAIZ)
    cena = Cena()
    m.carregar_cena(cena)
    for _ in range(SPRITES):
        cena.criar("s", random.uniform(0, 1280), random.uniform(0, 720),
                   componentes=[SpriteRenderer(imagem="assets/estrela.png")])
    if n_luzes:
        cena.criar("amb", componentes=[Luz2D(tipo="global", intensidade=0.25)])
        for _ in range(n_luzes - 1):
            cena.criar("l", random.uniform(0, 1280), random.uniform(0, 720),
                       componentes=[Luz2D(raio=random.uniform(80, 220), sombras=sombras,
                                          cor=(random.random(), random.random(), 1, 1))])
        if sombras:
            for _ in range(projetores):
                cena.criar("p", random.uniform(0, 1280), random.uniform(0, 720),
                           componentes=[Colisor(forma="caixa", largura=40, altura=40), ProjetorSombra2D()])
    for _ in range(10):
        m.passo(1 / 60)
    GL.glFinish()
    t = time.perf_counter()
    for _ in range(QUADROS):
        m.passo(1 / 60)
    GL.glFinish()
    ms = (time.perf_counter() - t) / QUADROS * 1000
    tri = m.renderizador.stats.sombras
    m.encerrar()
    return ms, tri


def main():
    linhas = []
    for n in LUZES:
        sem, _ = medir(n, False)
        com, tri = medir(n, True) if n else (sem, 0)
        linhas.append({"luzes": n, "ms_sem_sombra": round(sem, 2), "ms_com_sombra": round(com, 2),
                       "triangulos_sombra": tri})
        print(linhas[-1], flush=True)
    saida = RAIZ / "resultados"
    with open(saida / "luzes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 3.4), dpi=150)
    ax.plot([l["luzes"] for l in linhas], [l["ms_sem_sombra"] for l in linhas], "o-", label="luzes sem sombra")
    ax.plot([l["luzes"] for l in linhas], [l["ms_com_sombra"] for l in linhas], "s-", label="luzes com sombra (40 objetos)")
    ax.axhline(16.7, color="gray", ls="--", lw=1)
    ax.text(LUZES[-1], 17.5, "60 FPS", ha="right", color="gray", fontsize=8)
    ax.set_xlabel("quantidade de luzes")
    ax.set_ylabel("tempo por quadro (ms)")
    ax.set_title(f"Custo da iluminação 2D ({SPRITES} sprites, 1280x720)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(saida / "luzes.png")
    print("ok:", saida / "luzes.csv")


if __name__ == "__main__":
    main()
