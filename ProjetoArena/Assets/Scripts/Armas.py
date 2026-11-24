"""Projéteis, serras e onda de choque + as ações da DSL usadas pelas armas e pelo atirador.

As armas em si (quando atirar, quanto dano por nível) estão em Assets/Agentes/arena.agt.
"""
import math
import random

from engine2d import Colisor, Componente, CorpoRigido, SpriteRenderer, TempoDeVida
from engine2d.projeto import acao_dsl

BALA = "Assets/Sprites/Efeitos/bala.png"
FOGO = "Assets/Sprites/Efeitos/fogo.png"
SERRA = "Assets/Sprites/Efeitos/serra.png"
ANEL = "Assets/Sprites/Efeitos/anel.png"


class Projetil(Componente):
    CAMPOS = {"dano": "float", "perfuracao": "int", "alvo": "str"}
    dano = 5.0
    perfuracao = 1
    alvo = "inimigo"      # camada física que este projétil fere ("inimigo" ou "jogador")

    def iniciar(self):
        self.atingidos = set()

    def ao_entrar_colisao(self, outro):
        if self.perfuracao <= 0 or outro.camada_fisica != self.alvo:
            return
        go = outro.gameobject
        if go.id in self.atingidos:
            return
        self.atingidos.add(go.id)
        if self.alvo == "inimigo":
            ini = go.obter("Inimigo")
            if ini:
                ini.receber_dano(self.dano)
        else:
            j = go.obter("Jogador")
            if j:
                j.ferir(self.dano)
        self.perfuracao -= 1
        if self.perfuracao <= 0:
            self.gameobject.destruir()


class Serra(Componente):
    """Lâmina que orbita o jogador: é filha de um pivô que gira (hierarquia de objetos)."""

    CAMPOS = {"dano": "float"}
    dano = 8.0

    def iniciar(self):
        self.recarga = {}

    def atualizar(self, dt):
        self.transform.rotacao += 720 * dt
        for k in list(self.recarga):
            self.recarga[k] -= dt
            if self.recarga[k] <= 0:
                del self.recarga[k]

    def ao_entrar_colisao(self, outro):
        if outro.camada_fisica != "inimigo":
            return
        go = outro.gameobject
        if go.id in self.recarga:
            return
        self.recarga[go.id] = 0.5
        ini = go.obter("Inimigo")
        if ini:
            ini.receber_dano(self.dano)


class Girar(Componente):
    CAMPOS = {"velocidade": "float"}
    velocidade = 180.0

    def atualizar(self, dt):
        self.transform.rotacao += self.velocidade * dt


class Anel(Componente):
    """Efeito visual da onda de choque: cresce e some."""
    CAMPOS = {"raio": "float"}
    raio = 150.0

    def iniciar(self):
        self.t = 0.0
        self.render = self.obter("SpriteRenderer")

    def atualizar(self, dt):
        self.t += dt
        f = min(1.0, self.t / 0.3)
        s = (self.raio * 2 / 256) * (0.3 + 0.7 * f)
        self.transform.escala_x = self.transform.escala_y = s
        self.render.cor = (1, 1, 1, 1 - f)
        if f >= 1:
            self.gameobject.destruir()


def criar_projetil(cena, x, y, ang, vel, dano, perfuracao, alvo, imagem, escala=1.0, camada_fisica="projetil"):
    rad = math.radians(ang)
    cena.criar("projétil", x, y, rotacao=ang, escala=escala, componentes=[
        SpriteRenderer(imagem=imagem, camada=4),
        CorpoRigido(vx=math.cos(rad) * vel, vy=math.sin(rad) * vel, cinematico=True),
        Colisor(raio=8, gatilho=True, camada_fisica=camada_fisica),
        Projetil(dano=dano, perfuracao=int(perfuracao), alvo=alvo),
        TempoDeVida(segundos=1.6)])


# ---------------------------------------------------------------------------------------
# Ações da DSL (corpo = ComportamentoAgente do objeto que executou a ação)
# ---------------------------------------------------------------------------------------
@acao_dsl("atirar_mais_proximo", "num", "num", "num", "num",
          descricao="tiros nos inimigos mais próximos (dano, velocidade, quantidade, perfuração)")
def atirar_mais_proximo(corpo, agente, dano, vel, qtd, perfura):
    cena = corpo.cena
    g = cena.servicos["gerente"]
    jx, jy = g.jogador_go.transform.posicao_mundo
    inimigos = []
    for c in cena.fisica.consultar_circulo(jx, jy, 650, camada="inimigo"):
        cx, cy = c.centro()
        inimigos.append(((cx - jx) ** 2 + (cy - jy) ** 2, cx, cy))
    if not inimigos:
        return
    inimigos.sort()
    for i in range(max(1, int(qtd))):
        _, cx, cy = inimigos[i % len(inimigos)]
        ang = math.degrees(math.atan2(cy - jy, cx - jx)) + (0 if i < len(inimigos) else random.uniform(-12, 12))
        criar_projetil(cena, jx, jy, ang, vel, dano * g.jogador.multiplicador_dano, perfura, "inimigo", BALA, 0.9)


@acao_dsl("atirar_no_jogador", "num", "num", descricao="projétil inimigo (dano, velocidade)")
def atirar_no_jogador(corpo, agente, dano, vel):
    cena = corpo.cena
    g = cena.servicos["gerente"]
    x, y = corpo.transform.posicao_mundo
    jx, jy = g.jogador_go.transform.posicao_mundo
    ang = math.degrees(math.atan2(jy - y, jx - x))
    corpo.transform.rotacao = ang
    criar_projetil(cena, x, y, ang, vel, dano, 1, "jogador", FOGO, 0.7, camada_fisica="projetil_inimigo")


@acao_dsl("serras", "num", "num", "num", "num", descricao="serras orbitando o jogador (qtd, dano, raio, velocidade)")
def serras(corpo, agente, qtd, dano, raio, vel):
    cena = corpo.cena
    g = cena.servicos["gerente"]
    j = g.jogador_go
    antigo = cena.encontrar("Pivô das serras")
    if antigo is not None:
        antigo.destruir()
    pivo = cena.criar("Pivô das serras", 0, 0, pai=j, componentes=[Girar(velocidade=float(vel))])
    qtd = max(1, int(qtd))
    for i in range(qtd):
        a = 2 * math.pi * i / qtd
        cena.criar(f"serra {i + 1}", math.cos(a) * raio, math.sin(a) * raio, pai=pivo, escala=0.8,
                   componentes=[SpriteRenderer(imagem=SERRA, camada=4),
                                Colisor(raio=22, gatilho=True, camada_fisica="projetil"),
                                Serra(dano=float(dano) * g.jogador.multiplicador_dano)])


@acao_dsl("onda_de_choque", "num", "num", descricao="dano em área em volta do jogador (dano, raio)")
def onda_de_choque(corpo, agente, dano, raio):
    cena = corpo.cena
    g = cena.servicos["gerente"]
    jx, jy = g.jogador_go.transform.posicao_mundo
    for c in cena.fisica.consultar_circulo(jx, jy, float(raio), camada="inimigo"):
        ini = c.gameobject.obter("Inimigo")
        if ini:
            ini.receber_dano(float(dano) * g.jogador.multiplicador_dano)
    cena.criar("onda", jx, jy, componentes=[SpriteRenderer(imagem=ANEL, camada=5), Anel(raio=float(raio))])
