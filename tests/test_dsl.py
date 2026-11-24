"""Testes da AgentDSL: léxico, sintático, semântico, interpretador e integração."""
from pathlib import Path

import pytest

from agentdsl import ErroCompilacao, SistemaAgentes, Simbolo, analisar, tokenizar
from agentdsl import ast as A
from agentdsl.semantica import AnalisadorSemantico

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


def tipos(fonte):
    toks, erros = tokenizar(fonte)
    assert not erros, erros
    return [t.tipo for t in toks]


def erros_sem(fonte, **kw):
    prog, erros = analisar(fonte)
    assert not erros, [e.mensagem for e in erros]
    return [d for d in AnalisadorSemantico(**kw).analisar(prog) if d.gravidade == "erro"]


def avisos_sem(fonte, **kw):
    prog, _ = analisar(fonte)
    return [d for d in AnalisadorSemantico(**kw).analisar(prog) if d.gravidade == "aviso"]


# ---------------------------------------------------------------- léxico
def test_tokens_basicos_e_maior_lexema():
    assert tipos("+vida(V - 1) <- -+x; a <= 3.5 != b") == [
        "MAIS", "IDENT", "ABRE_PAR", "VAR", "MENOS", "NUM", "FECHA_PAR", "SETA", "MENOS_MAIS", "IDENT",
        "PONTO_VIRGULA", "IDENT", "MENOR_IGUAL", "NUM", "DIFERENTE", "IDENT", "FIM"]


def test_numero_seguido_de_ponto_final():
    toks, _ = tokenizar("vida(3).")
    assert [(t.tipo, t.valor) for t in toks[:5]] == [("IDENT", None), ("ABRE_PAR", None), ("NUM", 3),
                                                     ("FECHA_PAR", None), ("PONTO", None)]


def test_palavras_reservadas_texto_e_comentarios():
    toks, erros = tokenizar('agente a sprite "x\\"y.png" // comentario\n /* bloco\n */ nao')
    assert not erros
    assert [t.tipo for t in toks] == ["AGENTE", "IDENT", "SPRITE", "TEXTO", "NAO", "FIM"]
    assert toks[3].valor == 'x"y.png'
    assert toks[4].pos.linha == 3


@pytest.mark.parametrize("fonte, trecho", [
    ("a @ b", "caractere inválido"),
    ("x(12abc)", "número malformado"),
    ('"aberto', "texto não fechado"),
    ("/* sem fim", "comentário de bloco"),
])
def test_erros_lexicos(fonte, trecho):
    _, erros = tokenizar(fonte)
    assert any(trecho in e.mensagem for e in erros)


def test_posicao_dos_tokens():
    toks, _ = tokenizar("agente\n  robo")
    assert (toks[1].pos.linha, toks[1].pos.coluna) == (2, 3)


# ---------------------------------------------------------------- sintático
FONTE_OK = """
agente jogador sprite "j.png" em (10, -20) camada 3 {
    vivo.
    posicao(100, 200).
    +inimigo_proximo : vivo & nao ferido <- atacar.
    +recebeu_dano : vida(V) & V > 1 <- -+vida(V - 1); mover(-10, 2 * (V + 1)).
}
"""


def test_ast_do_exemplo_do_artigo():
    prog, erros = analisar(FONTE_OK)
    assert not erros
    ag = prog.agentes[0]
    assert ag.nome == "jogador"
    assert (ag.sprite.imagem, ag.sprite.x, ag.sprite.y, ag.sprite.camada) == ("j.png", 10, -20, 3)
    assert [str(c) for c in ag.crencas] == ["vivo", "posicao(100, 200)"]
    p1, p2 = ag.planos
    assert (p1.evento.op, p1.evento.literal.nome) == ("+", "inimigo_proximo")
    assert isinstance(p1.contexto[1], A.CondLiteral) and p1.contexto[1].negado
    assert isinstance(p2.contexto[1], A.Comparacao) and p2.contexto[1].op == ">"
    assert isinstance(p2.acoes[0], A.AcaoCrenca) and p2.acoes[0].op == "-+"
    # precedência: 2 * (V + 1)
    arg = p2.acoes[1].args[1]
    assert isinstance(arg, A.BinOp) and arg.op == "*" and isinstance(arg.dir, A.BinOp)


def test_precedencia_aritmetica():
    prog, _ = analisar("agente a { +x <- mover(1 + 2 * 3, 1 - 2 - 3). }")
    e1, e2 = prog.agentes[0].planos[0].acoes[0].args
    assert str(e1) == "(1 + (2 * 3))"
    assert str(e2) == "((1 - 2) - 3)"          # associatividade à esquerda


def test_parser_recupera_e_relata_varios_erros():
    fonte = (EXEMPLOS / "invalidos" / "erro_sintatico.agt").read_text(encoding="utf-8")
    _, erros = analisar(fonte)
    assert len(erros) == 4
    assert [e.pos.linha for e in erros] == [4, 5, 6, 10]


def test_mensagem_diz_o_que_esperava():
    _, erros = analisar("agente a { +x mover(1, 0). }")
    assert "esperava '<-'" in erros[0].mensagem


# ---------------------------------------------------------------- semântico
def test_exemplo_invalido_semantico_tem_os_erros_esperados():
    fonte = (EXEMPLOS / "invalidos" / "erro_semantico.agt").read_text(encoding="utf-8")
    prog, _ = analisar(fonte)
    diags = AnalisadorSemantico().analisar(prog)
    msgs = " | ".join(d.mensagem for d in diags if d.gravidade == "erro")
    for trecho in ["não pode conter variáveis", "ação desconhecida 'velocidad' (quis dizer 'velocidade'?)",
                   "espera 2 argumento(s)", "deveria ser num", "sem estar ligada",
                   "aritmética '*' com valor do tipo atomo", "exige números", "já foi definido",
                   "não existe"]:
        assert trecho in msgs, trecho


def test_variavel_ligada_no_contexto_e_inferencia_de_tipo():
    assert erros_sem("agente a { vida(3). +x : vida(V) <- mover(V, V * 2). }") == []
    # V vem de nome(robo): átomo → erro ao usar em conta
    assert erros_sem("agente a { nome(robo). +x : nome(V) <- mover(V * 2, 0). }")


def test_negacao_exige_variavel_ligada():
    erros = erros_sem("agente a { +x : nao alvo(Y) <- parar. }")
    assert any("na negação" in e.mensagem for e in erros)


def test_tipos_de_crenca_consistentes():
    erros = erros_sem("agente a { vida(3). +x <- +vida(alto). }")
    assert any("argumento 1 de 'vida'" in e.mensagem for e in erros)


def test_avisos():
    av = avisos_sem("agente a { +nunca <- parar. +x : y(Z) <- parar. }")
    msgs = " | ".join(a.mensagem for a in av)
    assert "nunca será gerado" in msgs
    assert "aparece uma só vez" in msgs
    # percepções do ambiente contam como fonte do evento
    assert not avisos_sem("agente a { +perto <- parar. }", percepcoes={("perto", 0): ()})


def test_heranca():
    fonte = """
    agente pai { vivo. vida(3). +vivo <- velocidade(1, 0). +bateu <- inverter. }
    agente filho : pai { vida(5). +vivo <- velocidade(0, 1). }
    """
    sis = SistemaAgentes(fonte, percepcoes={("bateu", 0): ()})
    filho = sis.agentes["filho"]
    assert sorted(str(c) for c in filho.decl.crencas) == ["vida(5)", "vivo"]
    sis.iniciar()
    sis.executar_ate_estabilizar()
    acoes = [a for a in sis.ambiente.acoes if a[0] == "filho"]
    assert acoes == [("filho", "velocidade", (0, 1))]   # plano do filho tem prioridade


def test_heranca_pai_depois_do_filho():
    erros = erros_sem("agente f : p { vivo. } agente p { vivo. }")
    assert any("deve ser declarado antes" in e.mensagem for e in erros)


# ---------------------------------------------------------------- interpretador
def test_crenca_gera_evento_e_plano_com_contexto():
    sis = SistemaAgentes("""
    agente j {
        vivo.
        +inimigo_proximo : vivo <- atacar.
        +inimigo_proximo <- fugir_rapido.
    }""", acoes={"atacar": __import__("agentdsl").Assinatura(()),
                 "fugir_rapido": __import__("agentdsl").Assinatura(())},
        percepcoes={("inimigo_proximo", 0): ()})
    sis.iniciar()
    j = sis.agentes["j"]
    j.adicionar("inimigo_proximo")
    sis.executar_ate_estabilizar()
    assert sis.ambiente.acoes == [("j", "atacar", ())]
    # Sem a crença "vivo", o primeiro plano não é aplicável: cai no segundo.
    j.remover("vivo")
    j.remover("inimigo_proximo")
    j.adicionar("inimigo_proximo")
    sis.executar_ate_estabilizar()
    assert sis.ambiente.acoes[-1] == ("j", "fugir_rapido", ())


def test_contador_com_aritmetica_e_substituicao():
    sis = SistemaAgentes("""
    agente g {
        vida(3).
        +dano : vida(V) & V > 1 <- -+vida(V - 1).
        +dano : vida(1) <- -vida(1); +morto; sumir.
    }""", percepcoes={("dano", 0): ()})
    sis.iniciar()
    g = sis.agentes["g"]
    for esperado in (2, 1):
        g.adicionar("dano")
        sis.executar_ate_estabilizar()
        g.remover("dano")
        assert g.crencas_com("vida", 1) == [("vida", (esperado,))]
    g.adicionar("dano")
    sis.executar_ate_estabilizar()
    assert g.acredita("morto") and not g.crencas_com("vida", 1)
    assert sis.ambiente.acoes == [("g", "sumir", ())]


def test_unificacao_no_gatilho_e_atomos():
    sis = SistemaAgentes("""
    agente s {
        +viu(X, Y) : X == jogador <- mover(Y, 0).
        +viu(X, _Y) : X != jogador <- parar.
    }""", percepcoes={("viu", 2): ("atomo", "num")})
    s = sis.agentes["s"]
    s.adicionar("viu", (Simbolo("jogador"), 7))
    s.adicionar("viu", (Simbolo("gato"), 1))
    sis.executar_ate_estabilizar()
    assert sis.ambiente.acoes == [("s", "mover", (7, 0)), ("s", "parar", ())]


def test_crenca_repetida_nao_gera_evento_novo():
    sis = SistemaAgentes("agente a { +x <- parar. }", percepcoes={("x", 0): ()})
    a = sis.agentes["a"]
    assert a.adicionar("x") and not a.adicionar("x")
    sis.executar_ate_estabilizar()
    assert len(sis.ambiente.acoes) == 1


def test_laco_infinito_e_limitado_por_passo():
    sis = SistemaAgentes("agente a { liga. +liga <- -liga; +desliga. +desliga <- -desliga; +liga. }")
    sis.iniciar()
    assert sis.passo() == sis.max_eventos   # não trava: no máximo N eventos por ciclo


def test_erro_de_compilacao_levanta_excecao():
    with pytest.raises(ErroCompilacao) as e:
        SistemaAgentes("agente a { +x <- voar. }", percepcoes={("x", 0): ()})
    assert "ação desconhecida" in str(e.value)


def test_operador_resto():
    sis = SistemaAgentes("agente a { +t(S) : S % 5 == 0 <- parar. }", percepcoes={("t", 1): ("num",)})
    a = sis.agentes["a"]
    for s in range(11):
        a.adicionar("t", (s,))
    sis.executar_ate_estabilizar()
    assert len(sis.ambiente.acoes) == 3     # 0, 5 e 10


def test_modelo_instancias_independentes():
    sis = SistemaAgentes("""
    modelo inimigo { vida(3). +dano : vida(V) & V > 1 <- -+vida(V - 1). +dano <- morrer. }
    agente diretor { comecou. +comecou <- invocar(inimigo, 2). }
    """, percepcoes={("dano", 0): ()})
    assert set(sis.agentes) == {"diretor"} and set(sis.modelos) == {"inimigo"}
    a, b = sis.criar_instancia("inimigo"), sis.criar_instancia("inimigo")
    assert (a.nome, b.nome) == ("inimigo#1", "inimigo#2")
    a.adicionar("dano")
    sis.executar_ate_estabilizar()
    assert a.crencas_com("vida", 1) == [("vida", (2,))] and b.crencas_com("vida", 1) == [("vida", (3,))]
    sis.remover_instancia(a)
    assert a not in sis.todos()


@pytest.mark.parametrize("fonte, trecho", [
    ("agente d { x. +x <- invocar(fantasma, 1). }", "modelo 'fantasma' não foi declarado"),
    ("agente d { x. +x <- invocar(d, 1). }", "é um agente único, não um modelo"),
    ("modelo m { } agente d { x. +x : t(N) <- invocar(N, 1). }", "escrito diretamente"),
])
def test_tipo_modelo_na_semantica(fonte, trecho):
    erros = erros_sem(fonte, percepcoes={("t", 1): ("atomo",)})
    assert any(trecho in e.mensagem for e in erros), [e.mensagem for e in erros]


def test_temporizador_conta_como_fonte_da_crenca():
    # sem o temporizador, +pronta geraria o aviso "nunca será gerado"
    assert not avisos_sem("agente a { x. +x <- temporizador(1, pronta). +pronta <- parar. }")


# ---------------------------------------------------------------- integração com a engine (sem GPU)
def _cena_com_agentes(fonte, **kw):
    from agentdsl.componente import ServicoAgentes
    from engine2d import Cena
    cena = Cena()
    cena.criar("Agentes", componentes=[ServicoAgentes(fonte=fonte, **kw)])
    cena.atualizar(0)
    return cena


def test_servico_agentes_unicos_temporizador_e_invocacao():
    from agentdsl.componente import ComportamentoAgente
    from engine2d import CorpoRigido
    cena = _cena_com_agentes("""
    modelo bicho { vivo. +vivo <- velocidade(10, 0). }
    agente chefe { pronto. +pronto <- temporizador(0.5, agora). +agora <- invocar(bicho, 3). }
    """)
    srv = cena.servicos["agentes"]
    assert cena.encontrar("agente chefe") is not None           # agente único ganha GameObject
    for _ in range(20):
        cena.atualizar(0.05)                                     # 1 s
    bichos = [g for g in cena.objetos if g.obter(ComportamentoAgente) and g.nome.startswith("bicho#")]
    assert len(bichos) == 3 and len(srv.sis.instancias) == 3
    assert all(g.obter(CorpoRigido).vx == 10 for g in bichos)    # ação velocidade(10, 0) executada
    bichos[0].destruir()
    cena.atualizar(0.01)
    assert len(srv.sis.instancias) == 2                           # destruir remove o agente


def test_percepcoes_so_mudancas_viram_eventos_e_pulsos():
    from agentdsl.componente import ComportamentoAgente
    cena = _cena_com_agentes("modelo m { +perto <- parar. -perto <- parar. +bateu <- parar. }",
                             percepcoes={("perto", 0): (), ("bateu", 0): ()})
    srv = cena.servicos["agentes"]
    go = srv.criar_corpo("m", 0, 0)
    cena.atualizar(0)
    corpo = go.obter(ComportamentoAgente)
    for _ in range(3):
        corpo.perceber({("perto", ())})
        cena.atualizar(0.01)
    corpo.perceber(set())
    cena.atualizar(0.01)
    eventos = [l for l in srv.sis.log if "perto" in l]
    assert len(eventos) == 2                                     # +perto uma vez, -perto uma vez
    cena.motor = type("M", (), {"quadro": 1})()                  # pulso precisa do número do quadro
    corpo.pulsar("bateu")
    assert corpo.ag.acredita("bateu")
    cena.motor.quadro = 2
    cena.atualizar(0.01)
    assert not corpo.ag.acredita("bateu")                        # pulso sai no quadro seguinte


@pytest.mark.parametrize("projeto, agt", [("ProjetoArena", "arena.agt"), ("ProjetoTorres", "torres.agt"),
                                          ("ProjetoExemplo", "inimigos.agt"),
                                          ("ProjetoSorveteria", "fabrica.agt")])
def test_programas_dos_projetos_compilam_sem_avisos(projeto, agt):
    from agentdsl.semantica import ACOES_ENGINE
    from engine2d.projeto import ACOES_DSL, ALVOS_DSL, PERCEPCOES_DSL, Projeto, limpar_registros_dsl
    raiz = Path(__file__).resolve().parent.parent / projeto
    limpar_registros_dsl()
    proj = Projeto(raiz)
    proj.carregar_scripts()
    try:
        assert not proj.erros_scripts, proj.erros_scripts
        fonte = (raiz / "Assets" / "Agentes" / agt).read_text(encoding="utf-8")
        acoes = {**ACOES_ENGINE, **{n: a for n, (a, _) in ACOES_DSL.items()}}
        sis = SistemaAgentes(fonte, acoes=acoes, percepcoes=dict(PERCEPCOES_DSL), alvos=tuple(ALVOS_DSL))
        assert not sis.avisos, sis.formatar_avisos()
    finally:
        proj.descarregar()


def test_negacao_aceita_variavel_anonima():
    fonte = """agente a {
        ok.
        +ok : nao carregando(_X) <- +livre.
        +ok : nao carregando(Y) <- +livre.
    }"""
    with pytest.raises(ErroCompilacao) as e:
        SistemaAgentes(fonte)
    assert "'Y'" in str(e.value) and "'_X'" not in str(e.value)
    sis = SistemaAgentes(fonte.replace("+ok : nao carregando(Y) <- +livre.", ""))
    sis.iniciar()
    sis.executar_ate_estabilizar()
    assert sis.agentes["a"].acredita("livre")


def test_objetivos_estilo_agentspeak():
    """+!g declara como alcançar um objetivo, !g persegue, -!g trata a falha."""
    from agentdsl.semantica import Assinatura
    from agentdsl import AmbienteRegistro
    fonte = """agente a {
        comecar.
        +comecar <- !produzir(2).
        +!produzir(N) : N > 0 <- passo(N); !produzir(N - 1).
        +!produzir(0) <- passo(99).
    }"""
    amb = AmbienteRegistro()
    sis = SistemaAgentes(fonte, ambiente=amb, acoes={"passo": Assinatura(("num",))})
    sis.iniciar()
    sis.executar_ate_estabilizar()
    assert [a[2] for a in amb.acoes] == [(2,), (1,), (99,)]
    with pytest.raises(ErroCompilacao) as e:
        SistemaAgentes("agente b { x. +x <- !produzr. +!produzir <- y. }", acoes={"y": Assinatura(())})
    assert "quis dizer '!produzir'" in str(e.value)
    toks, erros = tokenizar("+!g <- !h. -!g <- x != y.")
    assert not erros and [t.tipo for t in toks].count("EXCLAMACAO") == 3


@pytest.mark.parametrize("arquivo", ["1_tutorial", "2_pedidos", "3_atendente_robo1", "3_sorveteiro_robo2",
                                     "4_linha_robo1", "4_linha_robo2", "5_gerente"])
def test_solucoes_da_sorveteria_compilam(arquivo):
    """As soluções são o conteúdo de UMA janela do jogo: o jogo embrulha em modelo/agente."""
    from agentdsl.semantica import ACOES_ENGINE
    from engine2d.projeto import ACOES_DSL, ALVOS_DSL, PERCEPCOES_DSL, Projeto, limpar_registros_dsl
    raiz = Path(__file__).resolve().parent.parent / "ProjetoSorveteria"
    limpar_registros_dsl()
    proj = Projeto(raiz)
    proj.carregar_scripts()
    try:
        texto = (raiz / "Solucoes" / f"{arquivo}.agt").read_text(encoding="utf-8")
        cab = "agente gerente {" if arquivo == "5_gerente" else "modelo todos {"
        acoes = {**ACOES_ENGINE, **{n: a for n, (a, _) in ACOES_DSL.items()}}
        sis = SistemaAgentes(cab + "\n" + texto + "\n}", acoes=acoes, percepcoes=dict(PERCEPCOES_DSL),
                             alvos=tuple(ALVOS_DSL))
        assert not sis.avisos, sis.formatar_avisos()
    finally:
        proj.descarregar()
