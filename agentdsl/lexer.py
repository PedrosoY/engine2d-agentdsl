"""Analisador léxico escrito à mão.

Funciona como um autômato finito determinístico: o estado é escolhido pelo
primeiro caractere e o lexema é estendido enquanto o caractere seguinte
mantiver o autômato num estado válido (princípio do "maior lexema").

Classes de tokens (expressões regulares equivalentes):
    IDENT    [a-z][a-zA-Z0-9_]*        (palavras reservadas são separadas depois)
    VAR      [A-Z_][a-zA-Z0-9_]*
    NUM      [0-9]+ ("." [0-9]+)?
    TEXTO    '"' ( [^"\\\n] | '\\' . )* '"'
    símbolos { } ( ) , . ; : & + - * / < > <= >= == != <- -+ !
    comentários  // até o fim da linha,  /* ... */
"""
from __future__ import annotations

from dataclasses import dataclass

from .erros import Diagnostico, Posicao

PALAVRAS_RESERVADAS = {
    "agente": "AGENTE",
    "modelo": "MODELO",
    "sprite": "SPRITE",
    "em": "EM",
    "camada": "CAMADA",
    "nao": "NAO",
    "verdadeiro": "VERDADEIRO",
}

# Símbolos de dois caracteres têm prioridade sobre os de um (maior lexema).
SIMBOLOS_2 = {"<-": "SETA", "-+": "MENOS_MAIS", "<=": "MENOR_IGUAL", ">=": "MAIOR_IGUAL",
              "==": "IGUAL", "!=": "DIFERENTE"}
SIMBOLOS_1 = {"{": "ABRE_CHAVE", "}": "FECHA_CHAVE", "(": "ABRE_PAR", ")": "FECHA_PAR",
              ",": "VIRGULA", ".": "PONTO", ";": "PONTO_VIRGULA", ":": "DOIS_PONTOS",
              "&": "E", "+": "MAIS", "-": "MENOS", "*": "VEZES", "/": "DIVIDIDO", "%": "RESTO",
              "<": "MENOR", ">": "MAIOR", "!": "EXCLAMACAO"}


@dataclass(frozen=True)
class Token:
    tipo: str
    lexema: str
    pos: Posicao
    valor: object = None

    def __repr__(self) -> str:
        return f"{self.tipo}({self.lexema!r})@{self.pos}"


class Lexer:
    def __init__(self, fonte: str):
        # Editores no Windows às vezes gravam o BOM do UTF-8 no início do arquivo.
        self.fonte = fonte[1:] if fonte.startswith("﻿") else fonte
        self.i = 0
        self.linha = 1
        self.coluna = 1
        self.erros: list[Diagnostico] = []

    # --- utilitários ------------------------------------------------------
    def _atual(self, k: int = 0) -> str:
        j = self.i + k
        return self.fonte[j] if j < len(self.fonte) else ""

    def _avancar(self) -> str:
        c = self.fonte[self.i]
        self.i += 1
        if c == "\n":
            self.linha += 1
            self.coluna = 1
        else:
            self.coluna += 1
        return c

    def _erro(self, msg: str, pos: Posicao) -> None:
        self.erros.append(Diagnostico("lexico", msg, pos))

    # --- análise ----------------------------------------------------------
    def tokens(self) -> list[Token]:
        saida: list[Token] = []
        while True:
            tok = self.proximo()
            saida.append(tok)
            if tok.tipo == "FIM":
                return saida

    def proximo(self) -> Token:
        self._pular_espacos_e_comentarios()
        pos = Posicao(self.linha, self.coluna)
        c = self._atual()
        if c == "":
            return Token("FIM", "", pos)

        if c.islower():
            return self._identificador(pos)
        if c.isupper() or c == "_":
            return self._variavel(pos)
        if c.isdigit():
            return self._numero(pos)
        if c == '"':
            return self._texto(pos)

        dois = c + self._atual(1)
        if dois in SIMBOLOS_2:
            self._avancar()
            self._avancar()
            return Token(SIMBOLOS_2[dois], dois, pos)
        if c in SIMBOLOS_1:
            self._avancar()
            return Token(SIMBOLOS_1[c], c, pos)

        # Caractere inválido: registra e continua (recuperação de erro léxico).
        self._avancar()
        self._erro(f"caractere inválido {c!r}", pos)
        return self.proximo()

    def _pular_espacos_e_comentarios(self) -> None:
        while True:
            c = self._atual()
            if c and c in " \t\r\n":
                self._avancar()
            elif c == "/" and self._atual(1) == "/":
                while self._atual() not in ("", "\n"):
                    self._avancar()
            elif c == "/" and self._atual(1) == "*":
                pos = Posicao(self.linha, self.coluna)
                self._avancar()
                self._avancar()
                while not (self._atual() == "*" and self._atual(1) == "/"):
                    if self._atual() == "":
                        self._erro("comentário de bloco não fechado", pos)
                        return
                    self._avancar()
                self._avancar()
                self._avancar()
            else:
                return

    def _palavra(self) -> str:
        ini = self.i
        while self._atual() and (self._atual().isalnum() or self._atual() == "_"):
            self._avancar()
        return self.fonte[ini:self.i]

    def _identificador(self, pos: Posicao) -> Token:
        lex = self._palavra()
        return Token(PALAVRAS_RESERVADAS.get(lex, "IDENT"), lex, pos)

    def _variavel(self, pos: Posicao) -> Token:
        return Token("VAR", self._palavra(), pos)

    def _numero(self, pos: Posicao) -> Token:
        ini = self.i
        while self._atual().isdigit():
            self._avancar()
        # Parte fracionária só se houver dígito depois do ponto
        # (assim "vivo(3)." termina o número antes do ponto final).
        if self._atual() == "." and self._atual(1).isdigit():
            self._avancar()
            while self._atual().isdigit():
                self._avancar()
        lex = self.fonte[ini:self.i]
        if self._atual().isalpha() or self._atual() == "_":
            resto = self._palavra()
            self._erro(f"número malformado {lex + resto!r}", pos)
            return Token("NUM", lex, pos, float(lex))
        return Token("NUM", lex, pos, float(lex) if "." in lex else int(lex))

    def _texto(self, pos: Posicao) -> Token:
        self._avancar()  # aspas de abertura
        partes = []
        escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
        while True:
            c = self._atual()
            if c == "" or c == "\n":
                self._erro("texto não fechado (faltou \")", pos)
                break
            self._avancar()
            if c == '"':
                break
            if c == "\\":
                e = self._atual()
                if e in escapes:
                    self._avancar()
                    partes.append(escapes[e])
                else:
                    self._erro(f"sequência de escape inválida '\\{e}'", Posicao(self.linha, self.coluna - 1))
            else:
                partes.append(c)
        valor = "".join(partes)
        return Token("TEXTO", f'"{valor}"', pos, valor)


def tokenizar(fonte: str) -> tuple[list[Token], list[Diagnostico]]:
    lx = Lexer(fonte)
    toks = lx.tokens()
    return toks, lx.erros
