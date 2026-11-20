"""Erros e diagnósticos com posição (linha, coluna) no código-fonte."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Posicao:
    linha: int
    coluna: int

    def __str__(self) -> str:
        return f"{self.linha}:{self.coluna}"


@dataclass
class Diagnostico:
    fase: str          # "lexico" | "sintatico" | "semantico" | "execucao"
    mensagem: str
    pos: Posicao | None = None
    gravidade: str = "erro"   # "erro" | "aviso"

    def formatar(self, fonte: str | None = None, arquivo: str = "<fonte>") -> str:
        onde = f"{arquivo}:{self.pos}" if self.pos else arquivo
        txt = f"{onde}: {self.gravidade} {self.fase}: {self.mensagem}"
        if fonte and self.pos:
            linhas = fonte.splitlines()
            if 0 < self.pos.linha <= len(linhas):
                linha = linhas[self.pos.linha - 1]
                txt += f"\n    {linha}\n    {' ' * (self.pos.coluna - 1)}^"
        return txt


class ErroCompilacao(Exception):
    """Levantado quando há erros; carrega todos os diagnósticos encontrados."""

    def __init__(self, diagnosticos: list[Diagnostico]):
        self.diagnosticos = diagnosticos
        super().__init__("\n".join(d.formatar() for d in diagnosticos))


class ErroExecucao(Exception):
    pass
