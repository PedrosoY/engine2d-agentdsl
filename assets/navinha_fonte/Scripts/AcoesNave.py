"""Ações e percepções que a navinha acrescenta à AgentDSL.

Os inimigos e o diretor das ondas (Assets/Agentes/navinha.agt) usam estas ações junto com as
genéricas da engine (velocidade, girar, piscar, invocar, temporizador...).
"""
import math
import random

from agentdsl.interpretador import Simbolo
from engine2d.projeto import acao_dsl, alvo_dsl, percepcao_dsl

import Navinha as N

percepcao_dsl("atingido", "num")
percepcao_dsl("chegou")
percepcao_dsl("jogador_lado", "atomo")
percepcao_dsl("inimigos", "num")       # só o diretor: quantos inimigos há na tela
alvo_dsl("jogador", "esquerda", "direita", "frente", *N.SONS)


def _nave(corpo):
    return corpo.obter("NaveInimiga") if corpo is not None and corpo.gameobject is not None else None


def _tiro(corpo, angulo, vel, imagem=None):
    x, y = corpo.transform.posicao_mundo
    go = corpo.cena.instanciar("Assets/Prefabs/tiro_inimigo.prefab", x, y - 18)
    if imagem:
        go.obter("SpriteRenderer").imagem = imagem
    rb = go.obter("CorpoRigido")
    rb.vx = math.cos(math.radians(angulo)) * vel
    rb.vy = math.sin(math.radians(angulo)) * vel
    return go


def _angulo_jogador(corpo):
    j = N.jogador(corpo.cena)
    if j is None:
        return -90.0
    x, y = corpo.transform.posicao_mundo
    jx, jy = j.transform.posicao_mundo
    return math.degrees(math.atan2(jy - y, jx - x))


@acao_dsl("atirar", "num", "num", descricao="um tiro no ângulo dado (graus; -90 = para baixo) com a velocidade")
def atirar(corpo, agente, angulo, vel):
    if corpo is not None:
        _tiro(corpo, float(angulo), float(vel))
        N.tocar(corpo.cena, "laser_inimigo", 0.2)


@acao_dsl("mirar", "num", descricao="um tiro na direção do jogador")
def mirar(corpo, agente, vel):
    if corpo is not None:
        _tiro(corpo, _angulo_jogador(corpo), float(vel))
        N.tocar(corpo.cena, "laser_inimigo", 0.2)


@acao_dsl("leque", "num", "num", "num", descricao="N tiros abertos em leque (abertura em graus) mirando no jogador")
def leque(corpo, agente, n, abertura, vel):
    if corpo is None:
        return
    n = max(1, int(n))
    centro = _angulo_jogador(corpo)
    for i in range(n):
        a = centro if n == 1 else centro - abertura / 2 + abertura * i / (n - 1)
        _tiro(corpo, a, float(vel))
    N.tocar(corpo.cena, "laser_inimigo", 0.3)


@acao_dsl("anel", "num", "num", descricao="N tiros em círculo; cada anel sai um pouco girado (espiral)")
def anel(corpo, agente, n, vel):
    nave = _nave(corpo)
    if nave is None:
        return
    n = max(1, int(n))
    for i in range(n):
        _tiro(corpo, nave.angulo_anel + 360 * i / n, float(vel))
    nave.angulo_anel += 360 / n / 2.5
    N.tocar(corpo.cena, "laser_inimigo", 0.3)


@acao_dsl("ir_para", "num", "num", "num", descricao="vai até (x, y) e percebe +chegou")
def ir_para(corpo, agente, x, y, vel):
    nave = _nave(corpo)
    if nave is not None:
        nave.ir_para(x, y, vel)


@acao_dsl("descer_ate", "num", "num", descricao="desce (reto) até a altura y e percebe +chegou")
def descer_ate(corpo, agente, y, vel):
    nave = _nave(corpo)
    if nave is not None:
        nave.ir_para(corpo.transform.posicao_mundo[0], y, vel)


@acao_dsl("investir", "num", descricao="dispara na direção do jogador (ataque kamikaze)")
def investir(corpo, agente, vel):
    if corpo is None:
        return
    a = math.radians(_angulo_jogador(corpo))
    corpo.comportamento = None
    corpo._vel(math.cos(a) * vel, math.sin(a) * vel)


@acao_dsl("inverter_x", descricao="troca o lado para onde anda (zigue-zague)")
def inverter_x(corpo, agente):
    if corpo is not None and corpo.rb is not None:
        corpo.rb.vx = -corpo.rb.vx


@acao_dsl("quicar", descricao="passa a voltar quando bate nas bordas da área")
def quicar(corpo, agente):
    nave = _nave(corpo)
    if nave is not None:
        nave.quicar = True


@acao_dsl("cair", "num", descricao="cai para baixo com um pouco de desvio para o lado")
def cair(corpo, agente, vel):
    if corpo is not None:
        corpo._vel(random.uniform(-0.25, 0.25) * vel, -float(vel))


@acao_dsl("espalhar", "num", descricao="sai voando numa direção sorteada (para baixo)")
def espalhar(corpo, agente, vel):
    if corpo is not None:
        a = math.radians(random.uniform(-160, -20))
        corpo._vel(math.cos(a) * vel, math.sin(a) * vel)


@acao_dsl("explodir", descricao="explode (partículas + som) e some, dando os pontos da crença pontos(P)")
def explodir(corpo, agente):
    nave = _nave(corpo)
    if nave is not None:
        pontos = next((a[0] for _, a in agente.crencas_com("pontos", 1)), 0)
        nave.explodir(pontos)


@acao_dsl("soltar_item", "num", descricao="chance (em %) de deixar cair um item")
def soltar_item(corpo, agente, chance):
    if corpo is None or random.uniform(0, 100) >= chance:
        return
    tipo = random.choices(["arma", "escudo", "vida", "pontos"], weights=[45, 25, 8, 22])[0]
    x, y = corpo.transform.posicao_mundo
    corpo.cena.instanciar(f"Assets/Prefabs/item_{tipo}.prefab", x, y)


@acao_dsl("invocar_em", "modelo", "num", "num", descricao="cria um inimigo do modelo na posição (x, y)")
def invocar_em(corpo, agente, modelo, x, y):
    srv = agente.sistema.ambiente
    srv.criar_corpo(modelo.nome if isinstance(modelo, Simbolo) else str(modelo), float(x), float(y))


@acao_dsl("formacao", "modelo", "num", "num", descricao="N inimigos lado a lado no alto da tela, na altura y")
def formacao(corpo, agente, modelo, n, y):
    srv = agente.sistema.ambiente
    nome = modelo.nome if isinstance(modelo, Simbolo) else str(modelo)
    n = max(1, int(n))
    largura = N.DIREITA - N.ESQUERDA - 100
    for i in range(n):
        x = N.CENTRO_X if n == 1 else N.ESQUERDA + 50 + largura * i / (n - 1)
        srv.criar_corpo(nome, x, float(y))


@acao_dsl("avisar", "texto", descricao="mensagem grande no meio da tela")
def avisar(corpo, agente, texto):
    h = N.hud(agente.sistema.ambiente.cena)
    if h is not None:
        h.banner(str(texto))


@acao_dsl("tocar", "atomo", descricao="toca um som (laser, explosao, alerta, item...)")
def tocar(corpo, agente, som):
    N.tocar(agente.sistema.ambiente.cena, str(som))


@acao_dsl("mostrar_vida", "num", "num", descricao="barra de vida do chefe no alto da tela (vida, total)")
def mostrar_vida(corpo, agente, vida, total):
    h = N.hud(agente.sistema.ambiente.cena)
    if h is not None:
        h.vida_chefe = (max(0.0, float(vida)), float(total))


@acao_dsl("vitoria", descricao="o jogador venceu a fase")
def vitoria(corpo, agente):
    h = N.hud(agente.sistema.ambiente.cena)
    if h is not None:
        h.vitoria()
