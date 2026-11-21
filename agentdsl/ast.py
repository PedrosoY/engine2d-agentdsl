"""Árvore sintática abstrata (representação interna) da DSL."""
from __future__ import annotations

from dataclasses import dataclass, field

from .erros import Posicao


# --- termos e expressões ---------------------------------------------------
@dataclass
class Numero:
    valor: float
    pos: Posicao | None = None

    def __str__(self):
        v = self.valor
        return str(int(v)) if float(v).is_integer() else str(v)


@dataclass
class Texto:
    valor: str
    pos: Posicao | None = None

    def __str__(self):
        return f'"{self.valor}"'


@dataclass
class Atomo:
    """Constante simbólica, ex.: jogador, normal."""
    nome: str
    pos: Posicao | None = None

    def __str__(self):
        return self.nome


@dataclass
class Variavel:
    nome: str
    pos: Posicao | None = None

    def __str__(self):
        return self.nome


@dataclass
class BinOp:
    op: str          # + - * /
    esq: object
    dir: object
    pos: Posicao | None = None

    def __str__(self):
        return f"({self.esq} {self.op} {self.dir})"


@dataclass
class Negativo:
    expr: object
    pos: Posicao | None = None

    def __str__(self):
        return f"-{self.expr}"


# --- literais, crenças e condições -----------------------------------------
@dataclass
class Literal:
    """predicado(arg1, ..., argN) — usado em crenças, eventos e contexto."""
    nome: str
    args: list = field(default_factory=list)
    pos: Posicao | None = None

    @property
    def aridade(self) -> int:
        return len(self.args)

    def __str__(self):
        return self.nome + (f"({', '.join(map(str, self.args))})" if self.args else "")


@dataclass
class CondLiteral:
    literal: Literal
    negado: bool = False
    pos: Posicao | None = None

    def __str__(self):
        return ("nao " if self.negado else "") + str(self.literal)


@dataclass
class Comparacao:
    op: str          # < <= > >= == !=
    esq: object
    dir: object
    pos: Posicao | None = None

    def __str__(self):
        return f"{self.esq} {self.op} {self.dir}"


@dataclass
class Verdadeiro:
    pos: Posicao | None = None

    def __str__(self):
        return "verdadeiro"


# --- ações do corpo do plano -----------------------------------------------
@dataclass
class AcaoCrenca:
    """+lit (adicionar), -lit (remover) ou -+lit (substituir: remove as de mesmo nome/aridade)."""
    op: str          # "+", "-", "-+"
    literal: Literal
    pos: Posicao | None = None

    def __str__(self):
        return f"{self.op}{self.literal}"


@dataclass
class AcaoExterna:
    """Ação enviada ao ambiente (engine), ex.: mover(10, 0)."""
    nome: str
    args: list = field(default_factory=list)
    pos: Posicao | None = None

    def __str__(self):
        return self.nome + (f"({', '.join(map(str, self.args))})" if self.args else "")


# --- estrutura do programa -------------------------------------------------
@dataclass
class Evento:
    op: str          # "+" adição | "-" remoção
    literal: Literal
    pos: Posicao | None = None

    def __str__(self):
        return f"{self.op}{self.literal}"


@dataclass
class Plano:
    """P = (E, C, A): evento disparador, contexto e ações (eq. 2 do artigo)."""
    evento: Evento
    contexto: list = field(default_factory=list)   # conjunção de condições
    acoes: list = field(default_factory=list)
    pos: Posicao | None = None

    def __str__(self):
        ctx = f" : {' & '.join(map(str, self.contexto))}" if self.contexto else ""
        return f"{self.evento}{ctx} <- {'; '.join(map(str, self.acoes))}."


@dataclass
class DeclSprite:
    imagem: str
    x: float = 0.0
    y: float = 0.0
    camada: int = 1
    pos: Posicao | None = None


@dataclass
class Agente:
    """A = (I, S, B): identificador, sprite associado e base de crenças (eq. 6)."""
    nome: str
    sprite: DeclSprite | None
    crencas: list = field(default_factory=list)
    planos: list = field(default_factory=list)
    pos: Posicao | None = None
    pai: str | None = None     # herança: "agente guarda2 : guarda1 ..."
    pai_pos: Posicao | None = None
    eh_modelo: bool = False    # "modelo": não é criado no início; o jogo cria instâncias


@dataclass
class Programa:
    agentes: list = field(default_factory=list)


def imprimir_arvore(no, nivel: int = 0) -> str:
    """Representação indentada da AST (usada no comando `ast` da CLI e no artigo)."""
    pad = "  " * nivel
    if isinstance(no, Programa):
        return "Programa\n" + "\n".join(imprimir_arvore(a, nivel + 1) for a in no.agentes)
    if isinstance(no, Agente):
        linhas = [f"{pad}{'Modelo' if no.eh_modelo else 'Agente'} {no.nome}" + (f" : {no.pai}" if no.pai else "")]
        if no.sprite:
            s = no.sprite
            linhas.append(f"{pad}  Sprite \"{s.imagem}\" em ({s.x}, {s.y}) camada {s.camada}")
        for c in no.crencas:
            linhas.append(f"{pad}  Crenca {c}")
        for p in no.planos:
            linhas.append(f"{pad}  Plano")
            linhas.append(f"{pad}    Evento {'adicao' if p.evento.op == '+' else 'remocao'} {p.evento.literal}")
            for c in p.contexto:
                linhas.append(f"{pad}    Contexto {c}")
            for a in p.acoes:
                tipo = "AcaoCrenca" if isinstance(a, AcaoCrenca) else "Acao"
                linhas.append(f"{pad}    {tipo} {a}")
        return "\n".join(linhas)
    return pad + str(no)
