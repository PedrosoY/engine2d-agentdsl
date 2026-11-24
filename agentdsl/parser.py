"""Analisador sintático descendente recursivo (LL(1)).

Cada não terminal da gramática (ver GRAMATICA.md) vira um método. Em caso de
erro, o parser registra o diagnóstico e entra em "modo pânico": descarta
tokens até um ponto de sincronização ('.', '}' ou 'agente') e continua,
para relatar vários erros numa única execução.
"""
from __future__ import annotations

from . import ast as A
from .erros import Diagnostico, ErroCompilacao
from .lexer import Token, tokenizar

OPS_RELACIONAIS = {"MENOR": "<", "MENOR_IGUAL": "<=", "MAIOR": ">", "MAIOR_IGUAL": ">=",
                   "IGUAL": "==", "DIFERENTE": "!="}

NOMES_TOKENS = {
    "AGENTE": "'agente'", "MODELO": "'modelo'", "SPRITE": "'sprite'", "EM": "'em'", "CAMADA": "'camada'",
    "ABRE_CHAVE": "'{'", "FECHA_CHAVE": "'}'", "ABRE_PAR": "'('", "FECHA_PAR": "')'",
    "VIRGULA": "','", "PONTO": "'.'", "PONTO_VIRGULA": "';'", "DOIS_PONTOS": "':'",
    "SETA": "'<-'", "IDENT": "identificador", "VAR": "variável", "NUM": "número",
    "TEXTO": "texto", "FIM": "fim do arquivo",
}


class _Panico(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token]):
        self.toks = tokens
        self.k = 0
        self.erros: list[Diagnostico] = []

    # --- utilitários ------------------------------------------------------
    @property
    def atual(self) -> Token:
        return self.toks[self.k]

    def _ver(self, *tipos: str) -> bool:
        return self.atual.tipo in tipos

    def _consumir(self) -> Token:
        t = self.atual
        if t.tipo != "FIM":
            self.k += 1
        return t

    def _esperar(self, tipo: str, contexto: str = "") -> Token:
        if self.atual.tipo == tipo:
            return self._consumir()
        self._falhar(f"esperava {NOMES_TOKENS.get(tipo, tipo)}"
                     + (f" {contexto}" if contexto else "")
                     + f", encontrou {self._descrever(self.atual)}")

    @staticmethod
    def _descrever(t: Token) -> str:
        return "fim do arquivo" if t.tipo == "FIM" else repr(t.lexema)

    def _falhar(self, msg: str):
        self.erros.append(Diagnostico("sintatico", msg, self.atual.pos))
        raise _Panico()

    def _sincronizar(self, ate=("PONTO", "FECHA_CHAVE", "AGENTE")) -> None:
        while not self._ver("FIM", *ate):
            self._consumir()
        if self._ver("PONTO"):
            self._consumir()

    # --- programa = { agente } FIM ----------------------------------------
    def programa(self) -> A.Programa:
        prog = A.Programa()
        while not self._ver("FIM"):
            try:
                prog.agentes.append(self.agente())
            except _Panico:
                # Pula até o próximo 'agente' para continuar a análise.
                while not self._ver("FIM", "AGENTE", "MODELO"):
                    self._consumir()
        return prog

    # agente = ("agente" | "modelo") IDENT [":" IDENT] [decl_sprite] "{" { crenca | plano } "}"
    def agente(self) -> A.Agente:
        if self._ver("MODELO"):
            ini = self._consumir()
        else:
            ini = self._esperar("AGENTE", "no início da definição ('agente' ou 'modelo')")
        nome = self._esperar("IDENT", "(nome do agente)").lexema
        pai = pai_pos = None
        if self._ver("DOIS_PONTOS"):
            self._consumir()
            t = self._esperar("IDENT", "(nome do agente pai)")
            pai, pai_pos = t.lexema, t.pos
        sprite = self.decl_sprite() if self._ver("SPRITE") else None
        self._esperar("ABRE_CHAVE", f"após o cabeçalho do agente '{nome}'")
        ag = A.Agente(nome, sprite, pos=ini.pos, pai=pai, pai_pos=pai_pos, eh_modelo=ini.tipo == "MODELO")
        while not self._ver("FECHA_CHAVE", "FIM", "AGENTE", "MODELO"):
            try:
                if self._ver("MAIS", "MENOS"):
                    ag.planos.append(self.plano())
                elif self._ver("IDENT"):
                    ag.crencas.append(self.crenca())
                else:
                    self._falhar(f"esperava uma crença ou um plano (+evento / -evento), "
                                 f"encontrou {self._descrever(self.atual)}")
            except _Panico:
                self._sincronizar(("PONTO", "FECHA_CHAVE", "AGENTE", "MODELO"))
        self._esperar("FECHA_CHAVE", f"para fechar o agente '{nome}'")
        return ag

    # decl_sprite = "sprite" TEXTO ["em" "(" numero "," numero ")"] ["camada" numero]
    def decl_sprite(self) -> A.DeclSprite:
        ini = self._consumir()
        img = self._esperar("TEXTO", "(arquivo da imagem)").valor
        d = A.DeclSprite(img, pos=ini.pos)
        if self._ver("EM"):
            self._consumir()
            self._esperar("ABRE_PAR")
            d.x = self.numero_literal()
            self._esperar("VIRGULA")
            d.y = self.numero_literal()
            self._esperar("FECHA_PAR")
        if self._ver("CAMADA"):
            self._consumir()
            d.camada = int(self.numero_literal())
        return d

    def numero_literal(self) -> float:
        sinal = -1 if self._ver("MENOS") and self._consumir() else 1
        return sinal * self._esperar("NUM").valor

    # crenca = literal "."
    def crenca(self) -> A.Literal:
        lit = self.literal()
        self._esperar("PONTO", f"no fim da crença '{lit}'")
        return lit

    # plano = ("+" | "-") ["!"] literal [":" contexto] "<-" corpo "."
    def plano(self) -> A.Plano:
        sinal = self._consumir()
        objetivo = bool(self._ver("EXCLAMACAO") and self._consumir())
        lit = self.literal()
        p = A.Plano(A.Evento(sinal.lexema, lit, sinal.pos, objetivo=objetivo), pos=sinal.pos)
        if self._ver("DOIS_PONTOS"):
            self._consumir()
            p.contexto = self.contexto()
        self._esperar("SETA", "entre o evento/contexto e as ações")
        p.acoes = self.corpo()
        self._esperar("PONTO", "no fim do plano")
        return p

    # contexto = condicao { "&" condicao }
    def contexto(self) -> list:
        conds = [self.condicao()]
        while self._ver("E"):
            self._consumir()
            conds.append(self.condicao())
        return conds

    # condicao = "verdadeiro" | "nao" literal | literal | arg relop arg
    def condicao(self):
        t = self.atual
        if self._ver("VERDADEIRO"):
            self._consumir()
            return A.Verdadeiro(t.pos)
        if self._ver("NAO"):
            self._consumir()
            return A.CondLiteral(self.literal(), negado=True, pos=t.pos)
        if self._ver("IDENT"):
            lit = self.literal()
            if self.atual.tipo in OPS_RELACIONAIS:
                if lit.args:
                    self._falhar(f"'{lit}' é um literal e não pode ser comparado")
                op = OPS_RELACIONAIS[self._consumir().tipo]
                return A.Comparacao(op, A.Atomo(lit.nome, lit.pos), self.arg(), t.pos)
            return A.CondLiteral(lit, pos=t.pos)
        esq = self.arg()
        if self.atual.tipo not in OPS_RELACIONAIS:
            self._falhar(f"esperava um operador relacional (<, <=, >, >=, ==, !=), "
                         f"encontrou {self._descrever(self.atual)}")
        op = OPS_RELACIONAIS[self._consumir().tipo]
        return A.Comparacao(op, esq, self.arg(), t.pos)

    # corpo = acao { ";" acao }
    def corpo(self) -> list:
        acoes = [self.acao()]
        while self._ver("PONTO_VIRGULA"):
            self._consumir()
            acoes.append(self.acao())
        return acoes

    # acao = ("+" | "-" | "-+") literal | IDENT ["(" [args] ")"]
    def acao(self):
        t = self.atual
        if self._ver("MAIS", "MENOS", "MENOS_MAIS"):
            self._consumir()
            return A.AcaoCrenca(t.lexema, self.literal(), t.pos)
        if self._ver("EXCLAMACAO"):
            self._consumir()
            return A.AcaoObjetivo(self.literal(), t.pos)
        if self._ver("IDENT"):
            lit = self.literal()
            return A.AcaoExterna(lit.nome, lit.args, t.pos)
        self._falhar(f"esperava uma ação, encontrou {self._descrever(t)}")

    # literal = IDENT ["(" [args] ")"]
    def literal(self) -> A.Literal:
        t = self._esperar("IDENT", "(nome da crença)")
        lit = A.Literal(t.lexema, [], t.pos)
        if self._ver("ABRE_PAR"):
            self._consumir()
            if not self._ver("FECHA_PAR"):
                lit.args = self.args()
            self._esperar("FECHA_PAR", f"nos argumentos de '{t.lexema}'")
        return lit

    # args = arg { "," arg } ;  arg = TEXTO | expr
    def args(self) -> list:
        lista = [self.arg()]
        while self._ver("VIRGULA"):
            self._consumir()
            lista.append(self.arg())
        return lista

    def arg(self):
        if self._ver("TEXTO"):
            t = self._consumir()
            return A.Texto(t.valor, t.pos)
        return self.expr()

    # expr = termo { ("+" | "-") termo }
    def expr(self):
        e = self.termo()
        while self._ver("MAIS", "MENOS"):
            op = self._consumir()
            e = A.BinOp(op.lexema, e, self.termo(), op.pos)
        return e

    # termo = fator { ("*" | "/" | "%") fator }
    def termo(self):
        e = self.fator()
        while self._ver("VEZES", "DIVIDIDO", "RESTO"):
            op = self._consumir()
            e = A.BinOp(op.lexema, e, self.fator(), op.pos)
        return e

    # fator = NUM | VAR | IDENT | "(" expr ")" | "-" fator
    def fator(self):
        t = self.atual
        if self._ver("NUM"):
            self._consumir()
            return A.Numero(t.valor, t.pos)
        if self._ver("VAR"):
            self._consumir()
            return A.Variavel(t.lexema, t.pos)
        if self._ver("IDENT"):
            self._consumir()
            return A.Atomo(t.lexema, t.pos)
        if self._ver("ABRE_PAR"):
            self._consumir()
            e = self.expr()
            self._esperar("FECHA_PAR", "para fechar a expressão")
            return e
        if self._ver("MENOS"):
            self._consumir()
            f = self.fator()
            if isinstance(f, A.Numero):
                return A.Numero(-f.valor, t.pos)
            return A.Negativo(f, t.pos)
        self._falhar(f"esperava um valor (número, variável ou nome), encontrou {self._descrever(t)}")


def analisar(fonte: str) -> tuple[A.Programa, list[Diagnostico]]:
    """Léxico + sintático. Devolve a AST (possivelmente parcial) e os erros."""
    toks, erros_lex = tokenizar(fonte)
    p = Parser(toks)
    prog = p.programa()
    return prog, erros_lex + p.erros


def analisar_ou_falhar(fonte: str) -> A.Programa:
    prog, erros = analisar(fonte)
    if erros:
        raise ErroCompilacao(erros)
    return prog
