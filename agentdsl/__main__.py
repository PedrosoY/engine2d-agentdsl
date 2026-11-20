"""Linha de comando da DSL.

    python -m agentdsl tokens     arquivo.agt   # saída do analisador léxico
    python -m agentdsl ast        arquivo.agt   # árvore sintática
    python -m agentdsl simbolos   arquivo.agt   # tabela de símbolos
    python -m agentdsl verificar  arquivo.agt   # léxico + sintático + semântico
    python -m agentdsl executar   arquivo.agt [--passos N] [--perceber agente:crenca ...]
                                                # roda sem gráficos e mostra crenças/ações
    python -m agentdsl jogo       arquivo.agt   # abre o cenário gráfico (engine 2D)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ast as A
from .erros import ErroCompilacao
from .interpretador import AmbienteRegistro, SistemaAgentes, formatar_crenca
from .lexer import tokenizar
from .parser import analisar
from .semantica import AnalisadorSemantico


def _percepcoes_jogo():
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from jogo import ALVOS, PERCEPCOES, ACOES_JOGO
        from .semantica import ACOES_ENGINE
        return PERCEPCOES, {**ACOES_ENGINE, **ACOES_JOGO}, ALVOS
    except Exception:
        return {}, None, ()


def _imprimir_diags(diags, fonte, arquivo) -> int:
    n_erros = 0
    for d in diags:
        print(d.formatar(fonte, arquivo), file=sys.stderr if d.gravidade == "erro" else sys.stdout)
        n_erros += d.gravidade == "erro"
    return n_erros


def main(argv=None) -> int:
    for fluxo in (sys.stdout, sys.stderr):   # console do Windows usa cp1252 por padrão
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(prog="agentdsl", description="AgentDSL — compilador/interpretador")
    ap.add_argument("comando", choices=["tokens", "ast", "simbolos", "verificar", "executar", "jogo"])
    ap.add_argument("arquivo")
    ap.add_argument("--passos", type=int, default=50)
    ap.add_argument("--perceber", nargs="*", default=[],
                    help="injeta percepções, ex.: guarda:jogador_perto  (prefixo - remove)")
    args = ap.parse_args(argv)

    caminho = Path(args.arquivo)
    fonte = caminho.read_text(encoding="utf-8-sig")
    nome = str(caminho)

    if args.comando == "tokens":
        toks, erros = tokenizar(fonte)
        for t in toks:
            print(f"{str(t.pos):>7}  {t.tipo:<13} {t.lexema}")
        return 1 if _imprimir_diags(erros, fonte, nome) else 0

    if args.comando == "jogo":
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import jogo
        return jogo.main(caminho)

    prog, erros = analisar(fonte)
    if erros:
        _imprimir_diags(erros, fonte, nome)
        print(f"\n{len(erros)} erro(s) léxico/sintático(s).", file=sys.stderr)
        return 1
    if args.comando == "ast":
        print(A.imprimir_arvore(prog))
        return 0

    percepcoes, acoes, alvos = _percepcoes_jogo()
    sem = AnalisadorSemantico(acoes, percepcoes, alvos)
    diags = sem.analisar(prog)
    n = _imprimir_diags(diags, fonte, nome)
    if args.comando == "simbolos":
        print(sem.tabela.descrever())
        return 1 if n else 0
    if args.comando == "verificar":
        avisos = len(diags) - n
        print(f"{'OK' if not n else 'FALHOU'}: {len(prog.agentes)} agente(s), "
              f"{sum(len(a.planos) for a in prog.agentes)} plano(s), {n} erro(s), {avisos} aviso(s).")
        return 1 if n else 0
    if n:
        return 1

    # executar (sem gráficos)
    amb = AmbienteRegistro()
    try:
        sis = SistemaAgentes(fonte, ambiente=amb, acoes=acoes, percepcoes=percepcoes, alvos=alvos, arquivo=nome)
    except ErroCompilacao:
        return 1
    sis.ao_registrar = lambda linha, tipo: print(linha)
    sis.iniciar()
    sis.executar_ate_estabilizar(args.passos * 64)
    for p in args.perceber:
        ag_nome, crenca = p.split(":", 1)
        remover = crenca.startswith("-")
        crenca = crenca.lstrip("+-")
        ag = sis.agentes[ag_nome]
        print(f"--- percepção: {'-' if remover else '+'}{crenca} em {ag_nome}")
        (ag.remover if remover else ag.adicionar)(crenca, ())
        sis.executar_ate_estabilizar(args.passos * 64)
    print("\nAções enviadas ao ambiente:")
    for ag, acao, vals in amb.acoes:
        print(f"  {ag}: {acao}({', '.join(map(str, vals))})")
    print("\nCrenças finais:")
    for ag in sis.agentes.values():
        print(f"  {ag.nome}: {', '.join(ag.descrever_crencas()) or '(vazia)'}")
    print(f"\nEstatísticas: {sis.stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
