"""Interpretador: crenças → eventos → seleção de plano → contexto → ações.

Ciclo de raciocínio (simplificação do ciclo do Jason):
  1. Uma alteração na base de crenças B_t → B_{t+1} gera um evento (+b ou -b).
  2. O evento entra na fila do agente.
  3. Para o evento da frente da fila, buscam-se os planos RELEVANTES
     (mesmo tipo, nome e aridade e cujo gatilho unifica com o evento).
  4. O primeiro plano (ordem do código) cujo CONTEXTO é satisfeito é APLICÁVEL.
  5. As ações do corpo são executadas em ordem. Ações de crença geram novos
     eventos (processados nos próximos passos); ações externas vão para o ambiente.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from . import ast as A
from .erros import Diagnostico, ErroCompilacao, ErroExecucao
from .parser import analisar
from .semantica import AnalisadorSemantico


@dataclass(frozen=True)
class Simbolo:
    """Valor de um átomo em tempo de execução (distinto de um texto)."""
    nome: str

    def __str__(self):
        return self.nome

    __repr__ = __str__


def formatar_valor(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, str):
        return f'"{v}"'
    return str(v)


def formatar_crenca(c) -> str:
    nome, args = c
    return nome + (f"({', '.join(formatar_valor(a) for a in args)})" if args else "")


# ---------------------------------------------------------------------------
# Avaliação de expressões e unificação
# ---------------------------------------------------------------------------
def avaliar(no, subst: dict):
    if isinstance(no, A.Numero):
        return no.valor
    if isinstance(no, A.Texto):
        return no.valor
    if isinstance(no, A.Atomo):
        return Simbolo(no.nome)
    if isinstance(no, A.Variavel):
        if no.nome not in subst:
            raise ErroExecucao(f"variável '{no.nome}' sem valor")
        return subst[no.nome]
    if isinstance(no, A.Negativo):
        return -avaliar(no.expr, subst)
    if isinstance(no, A.BinOp):
        a, b = avaliar(no.esq, subst), avaliar(no.dir, subst)
        if not all(isinstance(x, (int, float)) for x in (a, b)):
            raise ErroExecucao(f"operação '{no.op}' com valores não numéricos ({a}, {b})")
        if no.op == "+":
            return a + b
        if no.op == "-":
            return a - b
        if no.op == "*":
            return a * b
        if b == 0:
            raise ErroExecucao("divisão por zero")
        if no.op == "%":
            return a % b
        return a / b
    raise ErroExecucao(f"expressão desconhecida {no!r}")


def unificar(padroes: list, valores: tuple, subst: dict) -> dict | None:
    """Unifica argumentos do literal (AST) com valores concretos. Devolve nova substituição ou None."""
    if len(padroes) != len(valores):
        return None
    s = dict(subst)
    for p, v in zip(padroes, valores):
        if isinstance(p, A.Variavel):
            if p.nome.startswith("_") and p.nome == "_":
                continue
            if p.nome in s:
                if s[p.nome] != v:
                    return None
            else:
                s[p.nome] = v
        else:
            if avaliar(p, s) != v:
                return None
    return s


COMPARADORES = {
    "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
}


# ---------------------------------------------------------------------------
# Agente em tempo de execução
# ---------------------------------------------------------------------------
class Agente:
    def __init__(self, decl: A.Agente, sistema: "SistemaAgentes", nome: str | None = None):
        self.nome = nome or decl.nome
        self.modelo = decl.nome
        self.decl = decl
        self.sistema = sistema
        self.crencas: set[tuple] = set()
        self.fila: deque = deque()
        self.sprite = None            # preenchido pela ponte com a engine (versão antiga)
        self.corpo = None             # ComportamentoAgente que liga o agente a um GameObject
        self.vivo = True
        self.log: deque = deque(maxlen=8)
        self.planos = sistema._planos_por_modelo.get(decl.nome)
        if self.planos is None:   # índice evento → planos, compartilhado entre instâncias
            self.planos = {}
            for p in decl.planos:
                chave = (p.evento.op, p.evento.literal.nome, p.evento.literal.aridade)
                self.planos.setdefault(chave, []).append(p)
            sistema._planos_por_modelo[decl.nome] = self.planos

    # --- base de crenças: cada alteração produz um evento (eq. 7) ----------
    def adicionar(self, nome: str, args: tuple = ()) -> bool:
        c = (nome, tuple(args))
        if c in self.crencas:
            return False
        self.crencas.add(c)
        self.fila.append(("+", c))
        return True

    def remover(self, nome: str, args: tuple = ()) -> bool:
        c = (nome, tuple(args))
        if c not in self.crencas:
            return False
        self.crencas.discard(c)
        self.fila.append(("-", c))
        return True

    def acredita(self, nome: str, *args) -> bool:
        return (nome, tuple(args)) in self.crencas

    def crencas_com(self, nome: str, aridade: int):
        return [c for c in self.crencas if c[0] == nome and len(c[1]) == aridade]

    # --- consulta do contexto (gera todas as substituições que satisfazem) --
    def _satisfaz(self, conds: list, subst: dict):
        if not conds:
            yield subst
            return
        c, resto = conds[0], conds[1:]
        if isinstance(c, A.Verdadeiro):
            yield from self._satisfaz(resto, subst)
        elif isinstance(c, A.Comparacao):
            a, b = avaliar(c.esq, subst), avaliar(c.dir, subst)
            try:
                ok = COMPARADORES[c.op](a, b)
            except TypeError:
                ok = False
            if ok:
                yield from self._satisfaz(resto, subst)
        elif isinstance(c, A.CondLiteral):
            lit = c.literal
            if c.negado:   # negação por falha
                if not any(unificar(lit.args, args, subst) is not None
                           for args in (x[1] for x in self.crencas_com(lit.nome, lit.aridade))):
                    yield from self._satisfaz(resto, subst)
            else:
                for _, args in sorted(self.crencas_com(lit.nome, lit.aridade), key=str):
                    s2 = unificar(lit.args, args, subst)
                    if s2 is not None:
                        yield from self._satisfaz(resto, s2)

    # --- um passo do ciclo de raciocínio ------------------------------------
    def passo(self) -> bool:
        """Processa UM evento da fila. Devolve False se a fila estava vazia."""
        if not self.fila:
            return False
        op, (nome, args) = self.fila.popleft()
        self.sistema.stats["eventos"] += 1
        relevantes = self.planos.get((op, nome, len(args)), [])
        for plano in relevantes:
            s = unificar(plano.evento.literal.args, args, {})
            if s is None:
                continue
            s_ctx = next(self._satisfaz(plano.contexto, s), None)
            if s_ctx is None:
                continue
            self.sistema.registrar(self, f"{op}{formatar_crenca((nome, args))} -> plano linha {plano.pos.linha}")
            try:
                self._executar(plano, s_ctx)
            except ErroExecucao as e:   # erro em tempo de execução não derruba o jogo
                self.sistema.registrar(self, f"ERRO (linha {plano.pos.linha}): {e}", tipo="erro")
            return True
        return True

    def _executar(self, plano: A.Plano, s: dict) -> None:
        self.sistema.stats["planos"] += 1
        for acao in plano.acoes:
            if isinstance(acao, A.AcaoCrenca):
                lit = acao.literal
                vals = tuple(avaliar(a, s) for a in lit.args)
                if acao.op == "+":
                    self.adicionar(lit.nome, vals)
                elif acao.op == "-":
                    self.remover(lit.nome, vals)
                else:  # -+ : substitui todas as crenças com mesmo nome/aridade
                    for _, antigos in self.crencas_com(lit.nome, lit.aridade):
                        if antigos != vals:
                            self.remover(lit.nome, antigos)
                    self.adicionar(lit.nome, vals)
            else:
                vals = [avaliar(a, s) for a in acao.args]
                self.sistema.stats["acoes"] += 1
                if acao.nome == "imprimir":
                    self.sistema.registrar(self, " ".join(v if isinstance(v, str) else formatar_valor(v)
                                                          for v in vals), tipo="print")
                else:
                    self.sistema.ambiente.executar(self, acao.nome, vals)

    def descrever_crencas(self) -> list[str]:
        return sorted(formatar_crenca(c) for c in self.crencas)


# ---------------------------------------------------------------------------
class AmbienteRegistro:
    """Ambiente padrão sem gráficos: só registra as ações (usado em testes/CLI)."""

    def __init__(self):
        self.acoes: list[tuple] = []

    def executar(self, agente, nome, args):
        self.acoes.append((agente.nome, nome, tuple(args)))


class SistemaAgentes:
    """Compila um programa da DSL e mantém os agentes executando."""

    def __init__(self, fonte: str, ambiente=None, acoes=None, percepcoes=None, alvos=(),
                 arquivo: str = "<fonte>", max_eventos_por_passo: int = 64):
        self.fonte = fonte
        self.arquivo = arquivo
        self.ambiente = ambiente or AmbienteRegistro()
        self.max_eventos = max_eventos_por_passo
        self.stats = {"eventos": 0, "planos": 0, "acoes": 0}
        self.log: deque = deque(maxlen=200)
        self.ao_registrar = None

        prog, erros = analisar(fonte)
        if erros:
            raise ErroCompilacao(erros)
        sem = AnalisadorSemantico(acoes, percepcoes, alvos)
        diags = sem.analisar(prog)
        self.avisos = [d for d in diags if d.gravidade == "aviso"]
        erros = [d for d in diags if d.gravidade == "erro"]
        if erros:
            raise ErroCompilacao(erros)
        self.programa = prog
        self.tabela = sem.tabela
        self._planos_por_modelo: dict[str, dict] = {}
        self.modelos: dict[str, A.Agente] = {d.nome: d for d in prog.agentes if d.eh_modelo}
        # "agente" = instância única criada no início; "modelo" = criado sob demanda.
        self.agentes: dict[str, Agente] = {d.nome: Agente(d, self) for d in prog.agentes if not d.eh_modelo}
        self.instancias: list[Agente] = []
        self._contador: dict[str, int] = {}

    def criar_instancia(self, modelo: str, nome: str | None = None) -> Agente:
        """Cria um agente a partir de um ``modelo``; as crenças iniciais geram eventos +b."""
        decl = self.modelos.get(modelo)
        if decl is None:
            raise KeyError(f"modelo '{modelo}' não existe no programa")
        n = self._contador[modelo] = self._contador.get(modelo, 0) + 1
        ag = Agente(decl, self, nome or f"{modelo}#{n}")
        for c in decl.crencas:
            ag.adicionar(c.nome, tuple(avaliar(a, {}) for a in c.args))
        self.instancias.append(ag)
        return ag

    def remover_instancia(self, ag: Agente) -> None:
        ag.vivo = False
        if ag in self.instancias:
            self.instancias.remove(ag)

    def todos(self) -> list[Agente]:
        return list(self.agentes.values()) + self.instancias

    def iniciar(self) -> None:
        """Carrega as crenças iniciais. Como no Jason, cada uma gera um evento +b."""
        for ag in self.agentes.values():
            for c in ag.decl.crencas:
                ag.adicionar(c.nome, tuple(avaliar(a, {}) for a in c.args))

    def passo(self) -> int:
        """Um ciclo para todos os agentes; processa até ``max_eventos`` eventos de cada."""
        total = 0
        for ag in self.todos():
            if not ag.vivo:
                continue
            n = 0
            while n < self.max_eventos and ag.passo():
                n += 1
            total += n
        return total

    def executar_ate_estabilizar(self, limite: int = 10_000) -> int:
        total = 0
        while total < limite:
            n = self.passo()
            if n == 0:
                break
            total += n
        return total

    def registrar(self, agente, texto: str, tipo: str = "evento") -> None:
        linha = f"[{agente.nome}] {texto}"
        self.log.append(linha)
        agente.log.append(texto)
        if self.ao_registrar:
            self.ao_registrar(linha, tipo)

    def formatar_avisos(self) -> list[str]:
        return [d.formatar(self.fonte, self.arquivo) for d in self.avisos]


def compilar(fonte: str, **kw) -> SistemaAgentes:
    return SistemaAgentes(fonte, **kw)


__all__ = ["SistemaAgentes", "Agente", "Simbolo", "AmbienteRegistro", "compilar",
           "Diagnostico", "ErroCompilacao", "ErroExecucao", "formatar_crenca"]
