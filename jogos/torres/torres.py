"""Defesa da Base — tower defense estilo Bloons TD.

Compre torres no painel da direita (ou teclas 1-4) e clique no mapa para
posicioná-las. Clique numa torre para melhorar ou vender. ESPAÇO inicia a
próxima onda. Sobreviva às 15 ondas. ESC pausa · F1 editor · F2 reinicia.

Inimigos, torres (incluindo as melhorias) e ondas estão em torres.agt.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from agentdsl.componente import ComportamentoAgente, ServicoAgentes
from agentdsl.semantica import ATOMO, NUM, TEXTO, Assinatura
from engine2d import Cena, Colisor, Componente, Piscar, SpriteRenderer
from engine2d.ui import CORES
from jogos.comum import LogDSL, Pausa, criar_fumaca, criar_texto_flutuante, painel_fim, td

PASTA = Path(__file__).parent
TILE = 64
COLS, LINHAS = 16, 11
Y0 = 8                       # o mapa começa 8 px acima da borda de baixo
LARGURA_MAPA = COLS * TILE   # 1024; o painel ocupa o resto da tela
ONDA_FINAL = 15

# Caminho em células (coluna, linha), linha 0 embaixo. Começa e termina fora do mapa.
CAMINHO_CELULAS = [(-1, 8), (3, 8), (3, 3), (7, 3), (7, 9), (11, 9), (11, 2), (14, 2), (14, 6), (16, 6)]

TORRES = {
    # nome: (título, preço, base, torreta, [custo nv2, custo nv3], descrição)
    "metralhadora": ("Metralhadora", 120, td(180), td(203), [100, 260], "rápida, dano baixo"),
    "canhao": ("Canhão", 280, td(181), td(249), [220, 450], "dano em área"),
    "missil": ("Lança-mísseis", 450, td(182), td(205), [350, 700], "alcance longo, mira no mais forte"),
    "gelo": ("Torre de gelo", 200, td(183), td(229), [150, 300], "deixa os inimigos lentos"),
}
INIMIGOS = {
    # modelo: (imagem, velocidade, escala, voa)
    "soldado": (td(245), 70, 1.0, False),
    "soldado_rapido": (td(246), 125, 1.0, False),
    "blindado": (td(247), 55, 1.1, False),
    "tanque": (td(268), 45, 0.9, False),
    "tanque_pesado": (td(269), 34, 1.0, False),
    "aviao": (td(270), 140, 0.8, True),
    "bombardeiro": (td(271), 28, 1.8, True),
}


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


def ponto_no_caminho(s: float):
    """Posição e direção a uma distância s do início do caminho."""
    for a, b in zip(PONTOS, PONTOS[1:]):
        seg = math.dist(a, b)
        if s <= seg:
            f = s / seg
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        s -= seg
    a, b = PONTOS[-2], PONTOS[-1]
    return b[0], b[1], math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


# =============================================================================
# Componentes
# =============================================================================
class SeguirCaminho(Componente):
    CAMPOS = {"velocidade": "float", "progresso": "float"}
    velocidade = 70.0
    progresso = 0.0

    def iniciar(self):
        self.lento = 1.0
        self.tempo_lento = 0.0
        self.chegou = False
        self.agente = self.obter(ComportamentoAgente)

    def desacelerar(self, fator, segundos=1.2):
        self.lento = min(self.lento, fator)
        self.tempo_lento = segundos

    def atualizar(self, dt):
        if self.tempo_lento > 0:
            self.tempo_lento -= dt
            if self.tempo_lento <= 0:
                self.lento = 1.0
        self.progresso += self.velocidade * self.lento * dt
        x, y, ang = ponto_no_caminho(self.progresso)
        t = self.transform
        t.x, t.y, t.rotacao = x, y, ang
        r = self.obter(SpriteRenderer)
        if r:
            r.cor = (0.6, 0.85, 1.0, 1.0) if self.lento < 1 else (1, 1, 1, 1)
        if self.progresso >= COMPRIMENTO and not self.chegou and self.agente and self.agente._iniciado:
            self.chegou = True
            self.agente.pulsar("chegou_ao_fim")


class InimigoTD(Componente):
    def iniciar(self):
        self.dano = 0.0
        self.agente = self.obter(ComportamentoAgente)
        self.vida_max = None

    def receber_dano(self, d):
        self.dano += d

    def vida(self) -> float:
        return self.agente.crenca_num("vida") if self.agente and self.agente._iniciado else 0.0

    def atualizar(self, dt):
        if self.agente is None or not self.agente._iniciado:
            return
        if self.vida_max is None:
            self.vida_max = self.vida() or 1.0
        if self.dano > 0:
            self.agente.pulsar("atingido", (round(self.dano, 2),))
            self.dano = 0.0

    def desenhar_ui(self, ui):
        if self.vida_max and self.vida() < self.vida_max:
            x, y = ui.mundo_para_tela(*self.transform.posicao_mundo)
            ui.barra((x - 18, y - 30, 36, 5), self.vida() / self.vida_max, cor=CORES["vermelho"])

    def ao_destruir(self):
        if self.cena is not None and "gerente" in self.cena.servicos:
            x, y = self.transform.posicao_mundo
            criar_fumaca(self.cena, x, y, 0.6 * self.transform.escala_x)


class Torre(Componente):
    """Gera a percepção inimigo_no_alcance e guarda o investimento (para vender)."""

    CAMPOS = {"tipo": "str", "investido": "int"}
    tipo = "metralhadora"
    investido = 0

    def iniciar(self):
        self.agente = self.obter(ComportamentoAgente)
        self.torreta = self.gameobject.filhos[0] if self.gameobject.filhos else None

    def alcance(self):
        return self.agente.crenca_num("alcance", 100) if self.agente and self.agente._iniciado else 100

    def nivel(self):
        return int(self.agente.crenca_num("nivel", 1)) if self.agente and self.agente._iniciado else 1

    def atualizar(self, dt):
        if self.agente is None or not self.agente._iniciado:
            return
        x, y = self.transform.posicao_mundo
        perto = self.cena.fisica.consultar_circulo(x, y, self.alcance(), camada="inimigo")
        self.agente.perceber({("inimigo_no_alcance", ())} if perto else set())


class ProjetilTD(Componente):
    CAMPOS = {"dano": "float", "velocidade": "float", "area": "float"}
    dano = 1.0
    velocidade = 600.0
    area = 0.0
    alvo = None        # definido por quem atira, antes do iniciar() rodar

    def iniciar(self):
        self.destino = None
        self.vida = 2.5

    def atualizar(self, dt):
        self.vida -= dt
        if self.alvo is not None and not self.alvo.destruido:
            self.destino = self.alvo.transform.posicao_mundo
        if self.destino is None or self.vida <= 0:
            self.gameobject.destruir()
            return
        t = self.transform
        dx, dy = self.destino[0] - t.x, self.destino[1] - t.y
        d = math.hypot(dx, dy)
        passo = self.velocidade * dt
        t.rotacao = math.degrees(math.atan2(dy, dx))
        if d <= passo + 6:
            self._acertar()
            return
        t.x += dx / d * passo
        t.y += dy / d * passo

    def _acertar(self):
        x, y = self.destino
        if self.area > 0:
            for c in self.cena.fisica.consultar_circulo(x, y, self.area, camada="inimigo"):
                ini = c.gameobject.obter(InimigoTD)
                if ini:
                    ini.receber_dano(self.dano)
            criar_fumaca(self.cena, x, y, self.area / 50)
        elif self.alvo is not None and not self.alvo.destruido:
            ini = self.alvo.obter(InimigoTD)
            if ini:
                ini.receber_dano(self.dano)
        self.gameobject.destruir()


class AnelGelo(Componente):
    CAMPOS = {"raio": "float"}
    raio = 120.0

    def iniciar(self):
        self.t = 0.0
        self.r = self.obter(SpriteRenderer)

    def atualizar(self, dt):
        self.t += dt
        f = min(1.0, self.t / 0.35)
        s = self.raio * 2 / 256 * (0.4 + 0.6 * f)
        self.transform.escala_x = self.transform.escala_y = s
        self.r.cor = (0.5, 0.8, 1.0, 0.8 * (1 - f))
        if f >= 1:
            self.gameobject.destruir()


# =============================================================================
# Gerente
# =============================================================================
class GerenteTD(Componente):
    def iniciar(self):
        self.cena.servicos["gerente"] = self
        self.srv: ServicoAgentes = self.cena.servicos["agentes"]
        self.srv.ponto_de_invocacao = lambda modelo: PONTOS[0]
        self.srv.ao_invocar = self.ao_invocar
        self.dinheiro = 700
        self.vidas = 100
        self.onda = 0
        self.onda_ativa = False
        self.fim = None
        self.modo_infinito = False
        self.colocando: str | None = None
        self.selecionada = None
        self.ocupadas: dict[tuple, object] = {}
        self.caminho = celulas_do_caminho()
        self.fantasma = self.cena.criar("fantasma", -500, -500, componentes=[
            SpriteRenderer(imagem=td(180), camada=8, cor=(1, 1, 1, 0.6))])
        self.fantasma_torreta = self.cena.criar("fantasma torreta", 0, 0, pai=self.fantasma, componentes=[
            SpriteRenderer(imagem=td(203), camada=9, cor=(1, 1, 1, 0.6))])

    # --- inimigos -------------------------------------------------------------------
    def ao_invocar(self, go, origem):
        """Inimigos que nascem de outro (invocar_aqui) continuam do mesmo ponto do caminho."""
        seg = go.obter(SeguirCaminho)
        if seg is None:
            return
        if origem is not None and origem.gameobject is not None:
            o = origem.obter(SeguirCaminho)
            if o is not None:
                seg.progresso = max(0.0, o.progresso - random.uniform(0, 30))
        x, y, ang = ponto_no_caminho(seg.progresso)
        go.transform.x, go.transform.y, go.transform.rotacao = x, y, ang

    def inimigos(self):
        return self.cena.com_tag("inimigo")

    # --- ondas -------------------------------------------------------------------------
    def iniciar_onda(self):
        if self.onda_ativa or self.fim:
            return
        self.onda += 1
        self.onda_ativa = True
        self.tempo_onda = 0.0     # a DSL só cria as séries no fim deste quadro (atualizar_tardio)
        ondas = self.srv.sis.agentes["ondas"]
        ondas.corpo.perceber({("onda", (self.onda,))})   # evento +onda(N) na DSL

    def atualizar(self, dt):
        if self.fim:
            return
        if self.onda_ativa:
            self.tempo_onda += dt
        if self.onda_ativa and self.tempo_onda > 0.5 and not self.srv.series and not self.inimigos():
            self.onda_ativa = False
            bonus = 60 + 12 * self.onda
            self.dinheiro += bonus
            criar_texto_flutuante(self.cena, LARGURA_MAPA / 2, 380, f"Onda {self.onda} concluída! +${bonus}")
            if self.onda >= ONDA_FINAL and not self.modo_infinito:
                self.fim = "vitoria"
        if self.vidas <= 0:
            self.vidas = 0
            self.fim = "derrota"
        self._entrada_mapa()

    def _celula_mouse(self):
        mx, my = self.motor.entrada.mouse_mundo
        c, r = int(mx // TILE), int((my - Y0) // TILE)
        if 0 <= c < COLS and 0 <= r < LINHAS and mx < LARGURA_MAPA:
            return c, r
        return None

    def _pode_colocar(self, cel):
        return cel is not None and cel not in self.caminho and cel not in self.ocupadas

    def _entrada_mapa(self):
        ent = self.motor.entrada
        ed = self.motor.editor
        if ed and ed.ativo:
            return
        for i, nome in enumerate(TORRES):
            if ent.tecla_baixou(str(i + 1)):
                self.selecionar_compra(nome)
        if ent.tecla_baixou("space"):
            self.iniciar_onda()
        cel = self._celula_mouse()
        if self.colocando:
            if cel is not None:
                x, y = centro_celula(*cel)
                self.fantasma.transform.x, self.fantasma.transform.y = x, y
                ok = self._pode_colocar(cel) and self.dinheiro >= TORRES[self.colocando][1]
                cor = (1, 1, 1, 0.65) if ok else (1, 0.4, 0.4, 0.65)
                for r in self.fantasma.obter_nos_filhos(SpriteRenderer):
                    r.cor = cor
                if ent.clicou(1) and ok and not self.motor.ui.mouse_sobre_ui():
                    self.construir(self.colocando, cel)
                    if not (ent.tecla("left shift") or ent.tecla("right shift")):
                        self.colocando = None
            if ent.clicou(3) or ent.tecla_baixou("escape"):
                self.colocando = None
                ent._baixou.discard("escape")    # não abre o menu de pausa
        elif ent.clicou(1) and cel is not None and not self.motor.ui.mouse_sobre_ui():
            self.selecionada = self.ocupadas.get(cel)
        if not self.colocando:
            self.fantasma.transform.x = -500

    def selecionar_compra(self, nome):
        self.colocando = nome
        self.selecionada = None
        _, _, base, torreta, _, _ = TORRES[nome]
        self.fantasma.obter(SpriteRenderer).trocar_imagem(base)
        self.fantasma_torreta.obter(SpriteRenderer).trocar_imagem(torreta)

    # --- torres ----------------------------------------------------------------------------
    def construir(self, nome, cel):
        preco = TORRES[nome][1]
        self.dinheiro -= preco
        x, y = centro_celula(*cel)
        go = self.srv.criar_corpo(nome, x, y)          # prefab + ComportamentoAgente(modelo=nome)
        go.obter(Torre).investido = preco
        go.nome = nome
        self.ocupadas[cel] = go
        self.selecionada = go

    def melhorar(self, go):
        torre = go.obter(Torre)
        n = torre.nivel()
        if n >= 3:
            return
        custo = TORRES[torre.tipo][4][n - 1]
        if self.dinheiro < custo:
            return
        self.dinheiro -= custo
        torre.investido += custo
        ag = go.obter(ComportamentoAgente).ag
        ag.remover("nivel", (n,))
        ag.adicionar("nivel", (n + 1,))          # evento +nivel(N+1): a DSL aplica a melhoria
        criar_texto_flutuante(self.cena, *go.transform.posicao_mundo, f"nível {n + 1}!")

    def vender(self, go):
        torre = go.obter(Torre)
        self.dinheiro += int(torre.investido * 0.7)
        for cel, g in list(self.ocupadas.items()):
            if g is go:
                del self.ocupadas[cel]
        go.destruir()
        self.selecionada = None

    # --- UI --------------------------------------------------------------------------------
    def desenhar_ui(self, ui):
        # alcance da torre selecionada / fantasma
        alvo = None
        if self.colocando and self.fantasma.transform.x > 0:
            alcance = {"metralhadora": 150, "canhao": 170, "missil": 260, "gelo": 120}[self.colocando]
            alvo = (self.fantasma.transform.posicao_mundo, alcance)
        elif self.selecionada is not None and not self.selecionada.destruido:
            alvo = (self.selecionada.transform.posicao_mundo, self.selecionada.obter(Torre).alcance())
        if alvo:
            (x, y), r = alvo
            sx, sy = ui.mundo_para_tela(x, y)
            ui.circulo((sx, sy), r, (255, 255, 255, 40))
            ui.circulo((sx, sy), r, (255, 255, 255, 140), 2)

        x0 = LARGURA_MAPA
        ui.retangulo((x0, 0, ui.largura - x0, ui.altura), (24, 28, 38, 245), raio=0, bloquear=True)
        ui.texto(x0 + 128, 26, "Defesa da Base", 24, ancora="center", negrito=True)
        ui.texto(x0 + 16, 56, f"Vidas: {self.vidas}", 19, cor=(255, 120, 120), negrito=True)
        ui.texto(x0 + 140, 56, f"$ {self.dinheiro}", 19, cor=(255, 220, 90), negrito=True)
        ui.texto(x0 + 16, 84, f"Onda {self.onda} / {ONDA_FINAL}" + ("  (em andamento)" if self.onda_ativa else ""),
                 16)
        if ui.botao((x0 + 12, 110, 232, 38), "Onda em andamento..." if self.onda_ativa else
                    f"Iniciar onda {self.onda + 1}  [espaço]", ativo=not self.onda_ativa and not self.fim):
            self.iniciar_onda()
        vel = self.motor.escala_tempo
        if ui.botao((x0 + 12, 154, 113, 30), f"Velocidade x{vel:g}", tamanho_texto=14):
            self.motor.escala_tempo = {1.0: 2.0, 2.0: 3.0}.get(vel, 1.0)
        ui.texto(x0 + 133, 160, f"inimigos: {len(self.inimigos())}", 14, cor=(190, 190, 200))

        ui.texto(x0 + 16, 196, "Torres", 17, negrito=True)
        for i, (nome, (titulo, preco, base, torreta, _, desc)) in enumerate(TORRES.items()):
            r = (x0 + 12 + (i % 2) * 118, 220 + (i // 2) * 112, 112, 106)
            if ui.botao(r, "", ativo=self.dinheiro >= preco, selecionado=self.colocando == nome,
                        dica=f"{titulo} [{i + 1}]\n{desc}"):
                self.selecionar_compra(nome)
            ui.desenhar_imagem(base, r[0] + 56, r[1] + 42, tamanho=50, alfa=255 if self.dinheiro >= preco else 120)
            ui.desenhar_imagem(torreta, r[0] + 56, r[1] + 42, tamanho=50, alfa=255 if self.dinheiro >= preco else 120)
            ui.texto(r[0] + 56, r[1] + 78, titulo, 13, ancora="center")
            ui.texto(r[0] + 56, r[1] + 95, f"$ {preco}", 13, ancora="center", cor=(255, 220, 90))

        sel = self.selecionada
        if sel is not None and not sel.destruido:
            torre = sel.obter(Torre)
            ag = sel.obter(ComportamentoAgente)
            titulo = TORRES[torre.tipo][0]
            y = 460
            ui.retangulo((x0 + 8, y, 240, 200), (34, 40, 54), borda=CORES["borda"])
            ui.texto(x0 + 18, y + 8, f"{titulo} — nível {torre.nivel()}", 16, negrito=True)
            atributos = [f"{n}: {ag.crenca_num(n):g}" for n in ("alcance", "dano", "cadencia", "area", "lentidao")
                         if ag._iniciado and ag.ag.crencas_com(n, 1)]
            for k, a in enumerate(atributos):
                ui.texto(x0 + 22, y + 34 + 18 * k, a, 14, cor=(200, 210, 220))
            n = torre.nivel()
            if n < 3:
                custo = TORRES[torre.tipo][4][n - 1]
                if ui.botao((x0 + 16, y + 130, 224, 30), f"Melhorar para nível {n + 1}  ($ {custo})",
                            ativo=self.dinheiro >= custo, tamanho_texto=14):
                    self.melhorar(sel)
            else:
                ui.texto(x0 + 128, y + 145, "nível máximo", 14, ancora="center", cor=CORES["destaque"])
            if ui.botao((x0 + 16, y + 164, 224, 28), f"Vender ($ {int(torre.investido * 0.7)})", tamanho_texto=14):
                self.vender(sel)
        else:
            ui.texto(x0 + 16, 470, "Clique numa torre do mapa", 14, cor=(160, 160, 170))
            ui.texto(x0 + 16, 488, "para melhorar ou vender.", 14, cor=(160, 160, 170))
            ui.texto(x0 + 16, 516, "Shift+clique: várias torres.", 14, cor=(160, 160, 170))

        if self.fim == "derrota":
            painel_fim(ui, self.motor, self.cena, "A base caiu!", [f"Você chegou à onda {self.onda}"],
                       cor=CORES["vermelho"])
        elif self.fim == "vitoria":
            painel_fim(ui, self.motor, self.cena, "Vitória!",
                       [f"{ONDA_FINAL} ondas defendidas", f"Vidas restantes: {self.vidas}"], cor=CORES["verde"],
                       extra=("Continuar (modo infinito)", self._continuar))

    def _continuar(self):
        self.fim = None
        self.modo_infinito = True


# =============================================================================
# Ações do jogo chamadas pela DSL
# =============================================================================
_cena = None


def _alvo(torre_go, estrategia, alcance):
    x, y = torre_go.transform.posicao_mundo
    cand = [c.gameobject for c in _cena.fisica.consultar_circulo(x, y, alcance, camada="inimigo")]
    cand = [g for g in cand if g.obter(SeguirCaminho)]
    if not cand:
        return None
    if estrategia == "forte":
        return max(cand, key=lambda g: g.obter(InimigoTD).vida())
    if estrategia == "ultimo":
        return min(cand, key=lambda g: g.obter(SeguirCaminho).progresso)
    if estrategia == "perto":
        return min(cand, key=lambda g: math.dist(g.transform.posicao_mundo, (x, y)))
    return max(cand, key=lambda g: g.obter(SeguirCaminho).progresso)   # "primeiro": o mais adiantado


PROJETEIS = {"bala": (td(272), 0.8), "bola": (td(274), 1.2), "missil": (td(251), 0.7)}


def acao_atirar(corpo, agente, estrategia, projetil, dano, velocidade, area):
    if corpo is None:
        return
    go = corpo.gameobject
    torre = go.obter(Torre)
    x, y = go.transform.posicao_mundo
    estrategia, projetil = str(estrategia), str(projetil)
    if projetil == "gelo":   # efeito em área em volta da torre, sem projétil
        lent = corpo.crenca_num("lentidao", 0.5)
        for c in _cena.fisica.consultar_circulo(x, y, float(area), camada="inimigo"):
            seg = c.gameobject.obter(SeguirCaminho)
            if seg:
                seg.desacelerar(lent)
        _cena.criar("anel de gelo", x, y, componentes=[SpriteRenderer(imagem="anel.png", camada=7), AnelGelo(raio=float(area))])
        return
    alvo = _alvo(go, estrategia, torre.alcance())
    if alvo is None:
        return
    ax, ay = alvo.transform.posicao_mundo
    if torre.torreta is not None:   # a torreta (filha) gira; a base fica parada. Sprites apontam para cima (+y)
        torre.torreta.transform.rotacao = math.degrees(math.atan2(ay - y, ax - x)) - 90
    img, esc = PROJETEIS.get(projetil, PROJETEIS["bala"])
    p = _cena.criar("projétil", x, y, escala=esc, componentes=[SpriteRenderer(imagem=img, camada=6),
                                                              ProjetilTD(dano=float(dano), velocidade=float(velocidade),
                                                                         area=float(area))])
    proj = p.obter(ProjetilTD)
    proj.alvo = alvo


def acao_pagar(corpo, agente, n):
    g = _cena.servicos["gerente"]
    g.dinheiro += int(n)
    if corpo is not None:
        criar_texto_flutuante(_cena, *corpo.transform.posicao_mundo, f"+{int(n)}", cor=(255, 220, 90))


def acao_ferir_base(corpo, agente, n):
    _cena.servicos["gerente"].vidas -= int(n)


def acao_trocar_torreta(corpo, agente, imagem):
    if corpo is not None and corpo.gameobject.filhos:
        corpo.gameobject.filhos[0].obter(SpriteRenderer).trocar_imagem(str(imagem))


ACOES_JOGO = {
    "atirar": (Assinatura((ATOMO, ATOMO, NUM, NUM, NUM), "estratégia, projétil, dano, velocidade, área"), acao_atirar),
    "pagar": (Assinatura((NUM,), "dá dinheiro ao jogador"), acao_pagar),
    "ferir_base": (Assinatura((NUM,), "tira vidas da base"), acao_ferir_base),
    "trocar_torreta": (Assinatura((TEXTO,), "troca a imagem da torreta"), acao_trocar_torreta),
}
PERCEPCOES = {
    ("atingido", 1): (NUM,),
    ("chegou_ao_fim", 0): (),
    ("inimigo_no_alcance", 0): (),
    ("onda", 1): (NUM,),
}
ALVOS = ("primeiro", "ultimo", "forte", "perto", "todos", "bala", "bola", "missil", "gelo")


# =============================================================================
# Cena
# =============================================================================
def prefab_inimigo(img, vel, escala, voa):
    filhos = []
    if voa:   # a sombra é um objeto filho, deslocado: anda junto com o avião
        filhos.append({"nome": "sombra", "transform": {"x": 10, "y": -14},
                       "componentes": [{"tipo": "SpriteRenderer",
                                        "campos": {"imagem": img, "camada": 1, "cor": [0, 0, 0, 0.3]}}]})
    return {"nome": "inimigo", "tag": "inimigo", "transform": {"escala": escala},
            "componentes": [
                {"tipo": "SpriteRenderer", "campos": {"imagem": img, "camada": 4 if voa else 2}},
                {"tipo": "Colisor", "campos": {"raio": 16, "gatilho": True, "camada_fisica": "inimigo"}},
                {"tipo": "SeguirCaminho", "campos": {"velocidade": vel}},
                {"tipo": "InimigoTD", "campos": {}},
                {"tipo": "Piscar", "campos": {}}],
            "filhos": filhos}


def prefab_torre(nome):
    _, _, base, torreta, _, _ = TORRES[nome]
    return {"nome": nome, "tag": "torre",
            "componentes": [{"tipo": "SpriteRenderer", "campos": {"imagem": base, "camada": 3}},
                            {"tipo": "Torre", "campos": {"tipo": nome}}],
            "filhos": [{"nome": "torreta", "componentes": [
                {"tipo": "SpriteRenderer", "campos": {"imagem": torreta, "camada": 5}}]}]}


def criar_cena(arquivo_agt: str | Path | None = None) -> Cena:
    global _cena
    cena = Cena("Defesa da Base")
    _cena = cena
    cena.servicos["fabrica"] = lambda: criar_cena(arquivo_agt)
    for modelo, args in INIMIGOS.items():
        cena.registrar_prefab(modelo, prefab_inimigo(*args))
    for nome in TORRES:
        cena.registrar_prefab(nome, prefab_torre(nome))

    caminho = celulas_do_caminho()
    mapa = cena.criar("Mapa")
    random.seed(11)
    for c in range(COLS):
        for r in range(LINHAS):
            x, y = centro_celula(c, r)
            img = td(50) if (c, r) in caminho else td(119 if (c + r) % 2 else 124)
            cena.criar("t", x, y, pai=mapa, componentes=[SpriteRenderer(imagem=img, camada=0, estatico=True)])
            if (c, r) not in caminho and random.random() < 0.07:
                cena.criar("decoração", x + random.uniform(-14, 14), y + random.uniform(-14, 14), pai=mapa,
                           escala=random.uniform(0.5, 0.8),
                           componentes=[SpriteRenderer(imagem=td(random.choice([130, 131, 135, 136, 137])),
                                                       camada=1, estatico=True)])
    # base do jogador no fim do caminho
    bx, by = PONTOS[-2]
    cena.criar("Base", bx, by, escala=1.0, componentes=[SpriteRenderer(imagem=td(182), camada=1, cor=(1, 0.85, 0.5, 1))])

    arq = Path(arquivo_agt) if arquivo_agt else PASTA / "torres.agt"
    cena.criar("Agentes (DSL)", componentes=[ServicoAgentes(
        fonte=arq.read_text(encoding="utf-8-sig"), acoes_jogo=ACOES_JOGO, percepcoes=PERCEPCOES, alvos=ALVOS,
        prefabs={**{m: m for m in INIMIGOS}, **{t: t for t in TORRES}}, arquivo=str(arq))])
    cena.criar("Gerente", componentes=[GerenteTD(), LogDSL(), Pausa()])
    return cena
