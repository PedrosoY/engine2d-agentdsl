"""Ligação entre os scripts Python e a AgentDSL.

- acao_dsl: cria uma ação nova que pode ser usada nos arquivos .agt
  (o compilador da DSL confere a quantidade e o tipo dos argumentos);
- percepcao_dsl: declara uma crença que os scripts colocam nos agentes;
- alvo_dsl: nomes de objetos que podem aparecer nas ações (ex.: perseguir(jogador, 70)).
"""
from engine2d.projeto import acao_dsl, alvo_dsl, percepcao_dsl

percepcao_dsl("atingido", "num")      # a Bala.py faz: agente.pulsar("atingido", (dano,))
alvo_dsl("jogador")


@acao_dsl("avisar", "texto", descricao="mostra uma mensagem grande na tela")
def avisar(corpo, agente, mensagem):
    # corpo = componente ComportamentoAgente do objeto; agente = o agente da DSL
    placar = corpo.cena.encontrar("Placar") if corpo else None
    if placar is not None:
        placar.obter("Placar").avisar(mensagem)
    print("[DSL]", mensagem)


@acao_dsl("dar_pontos", "num", descricao="soma pontos ao jogador")
def dar_pontos(corpo, agente, quantidade):
    jogador = corpo.cena.encontrar("jogador") if corpo else None
    if jogador is not None:
        jogador.obter("Jogador").pontos += int(quantidade)
