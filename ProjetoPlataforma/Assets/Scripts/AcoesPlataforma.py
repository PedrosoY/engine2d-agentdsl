"""Ações e percepções que o jogo de plataforma acrescenta à AgentDSL (usadas em plataforma.agt)."""
from agentdsl.interpretador import Simbolo
from engine2d.projeto import acao_dsl, alvo_dsl, percepcao_dsl

import Plataforma as P

for nome, *tipos in [("ativado",), ("no_chao",), ("jogador_lado", "atomo"), ("jogador_perto",),
                     ("parede_a_frente",), ("buraco_a_frente",), ("pisado",), ("batido",),
                     ("tempo", "num"), ("moedas", "num")]:
    percepcao_dsl(nome, *tipos)
alvo_dsl("jogador", "esquerda", "direita", "andar", "parado", "voar", "concha", "pulo", "achatado",
         "moeda_bloco", "cogumelo", *P.SONS)


def _txt(v):
    return v.nome if isinstance(v, Simbolo) else str(v)


def _inimigo(corpo):
    return corpo.obter("Inimigo") if corpo is not None and corpo.gameobject is not None else None


def _bloco(corpo):
    return corpo.obter("Bloco") if corpo is not None and corpo.gameobject is not None else None


@acao_dsl("andar", "atomo", "num", descricao="anda para a esquerda/direita com a velocidade dada")
def andar(corpo, agente, lado, vel):
    i = _inimigo(corpo)
    if i:
        i.andar(_txt(lado), vel)


@acao_dsl("virar", descricao="passa a andar para o outro lado")
def virar(corpo, agente):
    i = _inimigo(corpo)
    if i:
        i.virar()


@acao_dsl("parar", descricao="fica parado")
def parar(corpo, agente):
    i = _inimigo(corpo)
    if i:
        i.parar()


@acao_dsl("patrulhar_voando", "num", "num", descricao="voa de um lado para o outro (distância, velocidade)")
def patrulhar_voando(corpo, agente, dist, vel):
    i = _inimigo(corpo)
    if i:
        i.patrulhar_voando(dist, vel)


@acao_dsl("pular_para_jogador", "num", "num", descricao="pula na direção do jogador (vel. horizontal, vertical)")
def pular_para_jogador(corpo, agente, vx, vy):
    i = _inimigo(corpo)
    if i:
        i.pular_para_jogador(vx, vy)


@acao_dsl("animacao", "atomo", descricao="troca a animação (andar, parado, voar, concha, pulo, achatado)")
def animacao(corpo, agente, nome):
    i = _inimigo(corpo)
    if i:
        i.animacao(_txt(nome))


@acao_dsl("achatar", descricao="foi derrotado: achata, some e dá os pontos da crença pontos(P)")
def achatar(corpo, agente):
    i = _inimigo(corpo)
    if i:
        pontos = next((a[0] for _, a in agente.crencas_com("pontos", 1)), 0)
        i.achatar(pontos)


@acao_dsl("quicar_bloco", descricao="o bloco dá um pulinho")
def quicar_bloco(corpo, agente):
    b = _bloco(corpo)
    if b:
        b.quicar()


@acao_dsl("esvaziar", descricao="o bloco vira um bloco vazio")
def esvaziar(corpo, agente):
    b = _bloco(corpo)
    if b:
        b.esvaziar()


@acao_dsl("soltar", "atomo", descricao="faz sair de cima do bloco o prefab dado (moeda_bloco, cogumelo)")
def soltar(corpo, agente, prefab):
    b = _bloco(corpo)
    if b:
        b.soltar(_txt(prefab))


@acao_dsl("tocar", "atomo", descricao="toca um som (pulo, moeda, batida, dano, poder, pisao...)")
def tocar(corpo, agente, som):
    P.tocar(agente.sistema.ambiente.cena, _txt(som))


@acao_dsl("avisar", "texto", descricao="mensagem grande na tela")
def avisar(corpo, agente, texto):
    h = P.hud(agente.sistema.ambiente.cena)
    if h:
        h.banner(str(texto))


@acao_dsl("ganhar_vida", descricao="o jogador ganha uma vida")
def ganhar_vida(corpo, agente):
    j = P.jogador(agente.sistema.ambiente.cena)
    if j:
        j.ganhar_vida()
        P.tocar(agente.sistema.ambiente.cena, "poder")


@acao_dsl("acabou_o_tempo", descricao="o tempo acabou: fim de jogo")
def acabou_o_tempo(corpo, agente):
    j = P.jogador(agente.sistema.ambiente.cena)
    if j and not j.morto:
        j.vidas = 0
        j.morrer()
