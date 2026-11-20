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


# ---------------------------------------------------------------- integração com a engine
def test_ponte_executa_acoes_e_gera_percepcoes():
    from conftest import MotorFalso, TexturaFalsa
    from agentdsl.ponte_engine import AmbienteEngine
    from engine2d import Sprite

    amb = AmbienteEngine(MotorFalso(), {"perto", "borda"}, margem=10)
    sis = SistemaAgentes("""
    agente g {
        vivo.
        +vivo <- velocidade(100, 0); mudar_camada(4).
        +perto <- perseguir(alvo, 50).
        -perto <- parar.
        +borda <- inverter.
    }""", ambiente=amb, percepcoes={("perto", 0): (), ("borda", 0): ()}, alvos=("alvo",))
    g = sis.agentes["g"]
    sp = Sprite(TexturaFalsa(), x=100, y=100)
    alvo = Sprite(TexturaFalsa(), x=100, y=300)
    amb.vincular(g, sp)
    amb.registrar_objeto("alvo", alvo)
    sis.iniciar()
    sis.passo()
    assert sp.camada == 4
    amb.atualizar(1.0)
    assert (sp.x, sp.y) == (200, 100)                  # velocidade(100, 0) por 1 s
    amb.atualizar_percepcoes(g, {("perto", ())})
    sis.passo()
    amb.atualizar(1.0)
    assert sp.x < 200 and sp.y > 100                   # andou em direção ao alvo
    amb.atualizar_percepcoes(g, set())
    sis.passo()
    x = sp.x
    amb.atualizar(1.0)
    assert sp.x == x                                    # -perto → parar
    # borda: velocidade para a direita até sair do mapa (800 px)
    amb.executar(g, "velocidade", [1000, 0])
    amb.atualizar(1.0)
    assert sp.x == 790 and g.acredita("borda")
    sis.passo()
    assert amb.estado["g"]["vx"] == -1000              # +borda → inverter
    amb.atualizar(0.01)
    assert not g.acredita("borda")                      # pulso removido no quadro seguinte


def test_exemplo_do_jogo_compila_sem_avisos():
    import jogo
    from agentdsl.semantica import ACOES_ENGINE
    fonte = (EXEMPLOS / "jogo.agt").read_text(encoding="utf-8")
    sis = SistemaAgentes(fonte, acoes={**ACOES_ENGINE, **jogo.ACOES_JOGO}, percepcoes=jogo.PERCEPCOES,
                         alvos=jogo.ALVOS)
    assert not sis.avisos
    assert set(sis.agentes) == {"guarda", "guarda2", "fujao", "fujao2", "fujao3", "estrela"}


@pytest.mark.gpu
def test_jogo_roda_alguns_quadros():
    pytest.importorskip("OpenGL")
    import jogo
    jogo.main(max_quadros=5)
