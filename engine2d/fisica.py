"""Física 2D simples: integração de velocidade, detecção e resposta a colisões.

Fase ampla (broad phase): grade espacial uniforme (spatial hash). Cada colisor
é inserido nas células que sua AABB toca; só pares que dividem célula são
testados, o que reduz o custo de O(n²) para ~O(n) quando os objetos estão
espalhados.
Fase estreita: círculo×círculo, caixa×caixa e círculo×caixa, devolvendo o
vetor mínimo de separação (MTV).
Resposta: colisores sólidos com CorpoRigido são afastados pelo MTV, divididos
na proporção inversa das massas. Gatilhos só geram eventos.
Eventos: ao_entrar_colisao / ao_sair_colisao em todos os componentes dos dois objetos.
"""
from __future__ import annotations

import math
from collections import defaultdict


class Fisica:
    def __init__(self, tamanho_celula: float = 96.0):
        self.celula = tamanho_celula
        self.colisores: list = []
        self.corpos: list = []
        self._contatos: set[tuple] = set()
        self._ignorar: set[frozenset] = set()
        self.pares_testados = 0
        self.contatos_quadro = 0

    # --- registro ---------------------------------------------------------
    def registrar_colisor(self, c):
        self.colisores.append(c)

    def remover_colisor(self, c):
        if c in self.colisores:
            self.colisores.remove(c)
        # avisa "saiu" para quem estava encostando
        for par in [p for p in self._contatos if c in p]:
            self._contatos.discard(par)
            a, b = par
            if a.gameobject and b.gameobject and not a.gameobject.destruido and not b.gameobject.destruido:
                _avisar(a, b, "ao_sair_colisao")
                _avisar(b, a, "ao_sair_colisao")

    def registrar_corpo(self, c):
        self.corpos.append(c)

    def remover_corpo(self, c):
        if c in self.corpos:
            self.corpos.remove(c)

    def ignorar(self, camada_a: str, camada_b: str) -> None:
        """Camadas que nunca colidem entre si (matriz de colisão)."""
        self._ignorar.add(frozenset((camada_a, camada_b)))

    def colidem(self, a: str, b: str) -> bool:
        return frozenset((a, b)) not in self._ignorar

    # --- consultas ------------------------------------------------------------
    def consultar_circulo(self, x, y, raio, camada: str | None = None) -> list:
        saida = []
        for c in self.colisores:
            if (camada and c.camada_fisica != camada) or not c.habilitado or \
                    not c.gameobject.ativo_na_hierarquia:
                continue
            cx, cy = c.centro()
            r = c.raio * c.escala() if c.forma == "circulo" else max(c.largura, c.altura) * c.escala() / 2
            if (cx - x) ** 2 + (cy - y) ** 2 <= (raio + r) ** 2:
                saida.append(c)
        return saida

    def mais_proximo(self, x, y, camada: str, raio_max: float = math.inf):
        melhor, dmin = None, raio_max * raio_max
        for c in self.colisores:
            if c.camada_fisica != camada or not c.habilitado or not c.gameobject.ativo_na_hierarquia:
                continue
            cx, cy = c.centro()
            d = (cx - x) ** 2 + (cy - y) ** 2
            if d < dmin:
                melhor, dmin = c, d
        return melhor

    # --- passo da simulação ----------------------------------------------------
    def passo(self, dt: float) -> None:
        for rb in self.corpos:
            if not rb.habilitado or not rb.gameobject.ativo_na_hierarquia:
                continue
            if rb.vx or rb.vy:
                t = rb.gameobject.transform
                t.x += rb.vx * dt
                t.y += rb.vy * dt
            if rb.arrasto:
                f = max(0.0, 1.0 - rb.arrasto * dt)
                rb.vx *= f
                rb.vy *= f

        ativos = [c for c in self.colisores if c.habilitado and c.gameobject.ativo_na_hierarquia]
        # Fase ampla: grade espacial
        grade: dict[tuple, list] = defaultdict(list)
        caixas = {}
        inv = 1.0 / self.celula
        for c in ativos:
            x0, y0, x1, y1 = c.aabb()
            caixas[c] = (x0, y0, x1, y1)
            for i in range(int(math.floor(x0 * inv)), int(math.floor(x1 * inv)) + 1):
                for j in range(int(math.floor(y0 * inv)), int(math.floor(y1 * inv)) + 1):
                    grade[(i, j)].append(c)

        vistos = set()
        contatos = set()
        testados = 0
        for lista in grade.values():
            n = len(lista)
            if n < 2:
                continue
            for i in range(n):
                a = lista[i]
                for k in range(i + 1, n):
                    b = lista[k]
                    par = (a, b) if id(a) < id(b) else (b, a)
                    if par in vistos:
                        continue
                    vistos.add(par)
                    if a.gameobject is b.gameobject or not self.colidem(a.camada_fisica, b.camada_fisica):
                        continue
                    # AABBs precisam se sobrepor antes do teste exato
                    ax0, ay0, ax1, ay1 = caixas[a]
                    bx0, by0, bx1, by1 = caixas[b]
                    if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
                        continue
                    testados += 1
                    mtv = _intersecao(a, b)
                    if mtv is None:
                        continue
                    contatos.add(par)
                    if not a.gameobject.destruido and not b.gameobject.destruido and not (a.gatilho or b.gatilho):
                        _separar(a, b, mtv)
        self.pares_testados = testados
        self.contatos_quadro = len(contatos)

        novos = contatos - self._contatos
        saidas = self._contatos - contatos
        self._contatos = contatos
        for a, b in novos:
            _avisar(a, b, "ao_entrar_colisao")
            _avisar(b, a, "ao_entrar_colisao")
        for a, b in saidas:
            if not a.gameobject.destruido and not b.gameobject.destruido:
                _avisar(a, b, "ao_sair_colisao")
                _avisar(b, a, "ao_sair_colisao")


def _avisar(c, outro, metodo):
    go = c.gameobject
    if go is None or go.destruido:
        return
    for comp in list(go.componentes):
        if comp.habilitado:
            getattr(comp, metodo)(outro)


def _intersecao(a, b):
    """Vetor (dx, dy) que, aplicado a ``b``, o separa de ``a``; None se não há contato."""
    ax, ay = a.centro()
    bx, by = b.centro()
    ea, eb = a.escala(), b.escala()
    if a.forma == "circulo" and b.forma == "circulo":
        ra, rb = a.raio * ea, b.raio * eb
        dx, dy = bx - ax, by - ay
        d2 = dx * dx + dy * dy
        if d2 >= (ra + rb) ** 2:
            return None
        d = math.sqrt(d2) or 1e-6
        p = ra + rb - d
        return (dx / d * p, dy / d * p) if d > 1e-6 else (p, 0.0)
    if a.forma == "caixa" and b.forma == "caixa":
        hwa, hha = a.largura * ea / 2, a.altura * ea / 2
        hwb, hhb = b.largura * eb / 2, b.altura * eb / 2
        dx, dy = bx - ax, by - ay
        px = hwa + hwb - abs(dx)
        py = hha + hhb - abs(dy)
        if px <= 0 or py <= 0:
            return None
        return (math.copysign(px, dx), 0.0) if px < py else (0.0, math.copysign(py, dy))
    # círculo x caixa
    inverter = a.forma == "circulo"
    caixa, circ = (b, a) if inverter else (a, b)
    cx, cy = caixa.centro()
    ox, oy = circ.centro()
    ec, eo = caixa.escala(), circ.escala()
    hw, hh = caixa.largura * ec / 2, caixa.altura * ec / 2
    r = circ.raio * eo
    qx = min(max(ox, cx - hw), cx + hw)
    qy = min(max(oy, cy - hh), cy + hh)
    dx, dy = ox - qx, oy - qy
    d2 = dx * dx + dy * dy
    if d2 >= r * r:
        return None
    if d2 > 1e-12:
        d = math.sqrt(d2)
        mtv = (dx / d * (r - d), dy / d * (r - d))
    else:  # centro do círculo dentro da caixa: sai pelo lado mais próximo
        ex = hw - abs(ox - cx) + r
        ey = hh - abs(oy - cy) + r
        mtv = (math.copysign(ex, ox - cx), 0.0) if ex < ey else (0.0, math.copysign(ey, oy - cy))
    # mtv empurra o círculo para fora da caixa; convertemos para "empurrar b"
    return (-mtv[0], -mtv[1]) if inverter else mtv


def _separar(a, b, mtv):
    ra, rb = a.obter("CorpoRigido"), b.obter("CorpoRigido")
    ma = 0.0 if ra is None or ra.cinematico else 1.0 / max(ra.massa, 1e-6)
    mb = 0.0 if rb is None or rb.cinematico else 1.0 / max(rb.massa, 1e-6)
    soma = ma + mb
    if soma == 0:
        return
    dx, dy = mtv
    ta, tb = a.gameobject.transform, b.gameobject.transform
    ka, kb = ma / soma, mb / soma
    ta.x -= dx * ka
    ta.y -= dy * ka
    tb.x += dx * kb
    tb.y += dy * kb
