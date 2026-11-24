"""Grade do mapa e o caminho dos inimigos.

ATENÇÃO: os tiles do chão estão salvos na cena (Assets/Cenas/Principal.cena). Se você mudar o
CAMINHO aqui, mude também os tiles de terra na cena para combinarem (ou gere de novo).
"""
import math

TILE = 64
COLS, LINHAS = 16, 11
Y0 = 8                       # o mapa começa 8 px acima da borda de baixo da tela
LARGURA_MAPA = COLS * TILE   # 1024; o painel da loja ocupa o resto da tela

# Caminho em células (coluna, linha), linha 0 embaixo. Começa e termina fora do mapa.
CAMINHO_CELULAS = [(-1, 8), (3, 8), (3, 3), (7, 3), (7, 9), (11, 9), (11, 2), (14, 2), (14, 6), (16, 6)]


def centro_celula(c, r):
    return c * TILE + TILE / 2, Y0 + r * TILE + TILE / 2


def celulas_do_caminho():
    cel = set()
    for (c0, r0), (c1, r1) in zip(CAMINHO_CELULAS, CAMINHO_CELULAS[1:]):
        for c in range(min(c0, c1), max(c0, c1) + 1):
            for r in range(min(r0, r1), max(r0, r1) + 1):
                cel.add((c, r))
    return cel


PONTOS = [centro_celula(c, r) for c, r in CAMINHO_CELULAS]
COMPRIMENTO = sum(math.dist(a, b) for a, b in zip(PONTOS, PONTOS[1:]))


def ponto_no_caminho(s):
    """Posição (x, y) e direção (graus) a uma distância s do início do caminho."""
    for a, b in zip(PONTOS, PONTOS[1:]):
        seg = math.dist(a, b)
        if s <= seg:
            f = s / seg
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f,
                    math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))
        s -= seg
    a, b = PONTOS[-2], PONTOS[-1]
    return b[0], b[1], math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
