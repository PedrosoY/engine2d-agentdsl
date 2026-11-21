"""Avaliação da AgentDSL (parte de Compiladores).

1. Desempenho do front-end: tempo de léxico, sintático e semântico para
   programas gerados com 10 a 2000 agentes (tokens/s).
2. Desempenho do interpretador: eventos processados por segundo.
3. Concisão: DSL x Python equivalente para o mesmo comportamento (guarda).

Saída: resultados/dsl_*.csv e resultados/dsl_frontend.png
"""
import csv
import io
import statistics
import sys
import time
import tokenize
from pathlib import Path

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

from agentdsl import SistemaAgentes  # noqa: E402
from agentdsl.lexer import Lexer  # noqa: E402
from agentdsl.parser import Parser  # noqa: E402
from agentdsl.semantica import AnalisadorSemantico  # noqa: E402

PASTA = RAIZ / "resultados"
MODELO = """
agente guarda{i} sprite "guarda.png" em ({x}, {y}) camada 2 {{
    vivo.
    vida(3).
    patrulhando.
    +vivo <- velocidade(90, 0).
    +borda : patrulhando <- inverter.
    +jogador_perto : vivo <- -patrulhando; perseguir(jogador, 125).
    -jogador_perto : vivo <- +patrulhando; velocidade(90, 0).
    +recebeu_dano : vida(V) & V > 1 <- -+vida(V - 1); rotacionar(30).
    +recebeu_dano : vida(1) <- -vida(1); -vivo; parar; sumir.
}}
"""
PERC = {("borda", 0): (), ("jogador_perto", 0): (), ("recebeu_dano", 0): ()}


def gerar(n):
    return "".join(MODELO.format(i=i, x=i % 1000, y=i % 700) for i in range(n))


def medir(f, rep):
    tempos = []
    for _ in range(rep):
        t0 = time.perf_counter()
        r = f()
        tempos.append((time.perf_counter() - t0) * 1000)
    return statistics.median(tempos), r


def frontend():
    linhas = []
    for n in (10, 50, 100, 500, 1000, 2000):
        fonte = gerar(n)
        rep = 15 if n <= 500 else 5
        t_lex, toks = medir(lambda: Lexer(fonte).tokens(), rep)
        t_par, prog = medir(lambda: Parser(toks).programa(), rep)

        def sem():
            from agentdsl.parser import analisar
            p, _ = analisar(fonte)   # o semântico altera a AST (herança): reparse
            t0 = time.perf_counter()
            AnalisadorSemantico(percepcoes=PERC, alvos=("jogador",)).analisar(p)
            return (time.perf_counter() - t0) * 1000
        t_sem = statistics.median(sem() for _ in range(rep))
        linhas.append({"agentes": n, "linhas": fonte.count("\n"), "tokens": len(toks),
                       "ms_lexico": round(t_lex, 3), "ms_sintatico": round(t_par, 3),
                       "ms_semantico": round(t_sem, 3),
                       "tokens_por_s": round(len(toks) / ((t_lex + t_par) / 1000)),
                       })
        print(f"front-end n={n:5d}: {len(toks):7d} tokens  léxico {t_lex:8.2f} ms  "
              f"sintático {t_par:8.2f} ms  semântico {t_sem:8.2f} ms")
    return linhas


def interpretador():
    linhas = []
    for n in (10, 100, 1000):
        sis = SistemaAgentes(gerar(n), percepcoes=PERC, alvos=("jogador",))
        sis.iniciar()
        sis.executar_ate_estabilizar(10**7)
        ags = list(sis.agentes.values())
        rodadas = max(1, 20000 // n)
        sis.stats["eventos"] = 0
        t0 = time.perf_counter()
        for _ in range(rodadas):
            for a in ags:
                a.adicionar("jogador_perto")
                a.adicionar("recebeu_dano")
            sis.executar_ate_estabilizar(10**7)
            for a in ags:
                a.remover("jogador_perto")
                a.remover("recebeu_dano")
                a.remover("vida", (2,))
                a.adicionar("vida", (3,))
            sis.executar_ate_estabilizar(10**7)
        dt = time.perf_counter() - t0
        ev = sis.stats["eventos"]
        linhas.append({"agentes": n, "eventos": ev, "segundos": round(dt, 3),
                       "eventos_por_s": round(ev / dt), "us_por_evento": round(dt / ev * 1e6, 2)})
        print(f"interpretador n={n:5d}: {ev} eventos em {dt:.2f} s → {ev / dt:,.0f} eventos/s")
    return linhas


def contar_python(caminho):
    src = Path(caminho).read_text(encoding="utf-8")
    toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                              tokenize.DEDENT, tokenize.ENDMARKER, tokenize.STRING)
            or (t.type == tokenize.STRING and not t.string.startswith('"""'))]
    # descarta a docstring do módulo
    sem_doc = src.split('"""', 2)[2] if src.lstrip().startswith('"""') else src
    linhas = [l for l in sem_doc.splitlines() if l.strip() and not l.strip().startswith("#")]
    return len(linhas), len(toks)


def _bloco(fonte, cabecalho):
    """Recorta 'modelo X ... { ... }' do arquivo (até a chave que fecha)."""
    ini = fonte.index(cabecalho)
    fim = fonte.index("\n}", ini) + 2
    return fonte[ini:fim]


def concisao():
    fonte = (RAIZ / "jogos" / "arena" / "arena.agt").read_text(encoding="utf-8")
    trecho = _bloco(fonte, "modelo zumbi ") + "\n" + _bloco(fonte, "modelo atirador ")
    linhas_dsl = [l for l in trecho.splitlines() if l.strip() and not l.strip().startswith("//")]
    toks_dsl = len(Lexer(trecho).tokens()) - 1
    l_py, t_py = contar_python(RAIZ / "comparacao" / "inimigos_em_python.py")
    r = [{"versao": "AgentDSL", "linhas": len(linhas_dsl), "tokens": toks_dsl},
         {"versao": "Python", "linhas": l_py, "tokens": t_py}]
    print(f"concisão (zumbi + atirador): DSL {len(linhas_dsl)} linhas/{toks_dsl} tokens  x  "
          f"Python {l_py} linhas/{t_py} tokens")
    return r


def salvar(nome, linhas):
    with open(PASTA / nome, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)


def main():
    PASTA.mkdir(exist_ok=True)
    fe = frontend()
    it = interpretador()
    co = concisao()
    salvar("dsl_frontend.csv", fe)
    salvar("dsl_interpretador.csv", it)
    salvar("dsl_concisao.csv", co)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4))
    xs = [l["tokens"] for l in fe]
    for chave, rot in (("ms_lexico", "léxico"), ("ms_sintatico", "sintático"), ("ms_semantico", "semântico")):
        ax.plot(xs, [l[chave] for l in fe], marker="o", label=rot)
    ax.set(xscale="log", yscale="log", xlabel="tokens no programa", ylabel="tempo (ms, mediana)",
           title="Front-end da AgentDSL")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(PASTA / "dsl_frontend.png", dpi=150)
    print("Resultados em", PASTA)


if __name__ == "__main__":
    main()
