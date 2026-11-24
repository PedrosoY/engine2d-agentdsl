"""Atalhos do editor de código da Fábrica de Sorvete (estilo VS Code), sem abrir janela."""
import sys
from pathlib import Path

import pygame
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ProjetoSorveteria" / "Assets" / "Scripts"))
from EditorCodigo import EditorCodigo  # noqa: E402

TEXTO = "+ligado <- pegar_casquinha(medio); adicionar_sorvete(creme).\n+!x <- dancar.\n-!x <- !x."


class EntradaFalsa:
    def __init__(self):
        self._baixou, self.segura, self.texto_digitado = set(), set(), ""

    def tecla(self, nome):
        return nome in self.segura

    def tecla_baixou(self, nome):
        return nome in self._baixou


@pytest.fixture
def ed():
    pygame.init()
    e = EditorCodigo(TEXTO)
    e.focado = True
    return e


def aperta(ed, nome, *mods, vezes=1, texto=""):
    ent = EntradaFalsa()
    ent.segura = {f"left {m}" for m in mods}
    for _ in range(vezes):
        ent._baixou = {nome} if nome else set()
        ent.texto_digitado = texto
        ed.teclado(ent)


def test_selecao_com_teclado(ed):
    aperta(ed, "a", "ctrl")
    assert ed.texto_selecionado() == TEXTO
    aperta(ed, "right")
    assert ed.selecao() is None and (ed.lin, ed.col) == (2, 10)
    ed.lin, ed.col = 0, 0
    aperta(ed, "right", "ctrl", "shift", vezes=3)          # "+", "ligado", "<-" (como no VS Code)
    assert ed.texto_selecionado() == "+ligado <-"
    aperta(ed, "right", "shift", vezes=3)
    assert ed.texto_selecionado() == "+ligado <- pe"
    aperta(ed, "end", "shift")
    assert ed.texto_selecionado() == ed.linhas[0]
    aperta(ed, "", texto="Z")                             # digitar substitui a seleção
    assert ed.linhas[0] == "Z"


def test_copiar_recortar_colar_desfazer(ed):
    ed.lin, ed.col = 1, 0
    aperta(ed, "x", "ctrl")                               # sem seleção: recorta a linha toda
    assert ed.linhas == [TEXTO.split("\n")[0], "-!x <- !x."]
    aperta(ed, "v", "ctrl")                               # e cola acima da linha atual
    assert ed.linhas[1] == "+!x <- dancar." and len(ed.linhas) == 3
    aperta(ed, "z", "ctrl")
    assert len(ed.linhas) == 2
    aperta(ed, "y", "ctrl")
    assert len(ed.linhas) == 3


def test_linhas_comentar_indentar(ed):
    ed.lin, ed.col = 1, 0
    aperta(ed, "down", "alt")
    assert ed.linhas[2] == "+!x <- dancar."
    aperta(ed, "up", "alt", "shift")
    assert ed.linhas[2] == ed.linhas[3] == "+!x <- dancar."
    aperta(ed, "k", "ctrl", "shift")
    assert len(ed.linhas) == 3
    ed.lin, ed.col = 1, 0
    aperta(ed, "/", "ctrl")
    assert ed.linhas[1].startswith("// ")
    aperta(ed, ";", "ctrl")
    assert not ed.linhas[1].startswith("//")
    ed.ancora, ed.lin, ed.col = (0, 0), 2, 3
    aperta(ed, "tab")
    assert all(l.startswith("    ") for l in ed.linhas)
    aperta(ed, "tab", "shift")
    assert not any(l.startswith(" ") for l in ed.linhas)


def test_palavras_busca_e_autocompletar(ed):
    ed.lin, ed.col = 0, 13
    aperta(ed, "d", "ctrl")
    assert ed.texto_selecionado() == "pegar_casquinha"
    ed.ancora, ed.lin, ed.col = None, 0, len(ed.linhas[0])
    aperta(ed, "backspace", "ctrl")
    assert ed.linhas[0].endswith("(creme")
    aperta(ed, "home", "ctrl")
    assert (ed.lin, ed.col) == (0, 0)
    aperta(ed, "f", "ctrl")
    for c in "dancar":
        aperta(ed, "", texto=c)
    assert ed.texto_selecionado() == "dancar" and ed.lin == 1
    aperta(ed, "escape")
    assert ed.busca is None
    ed.fonte_sugestoes = lambda p, e: [(n + "(", n, "") for n in ("pegar_casquinha", "pegar_de") if n.startswith(p)]
    ed.definir_texto("+ligado <- ")
    ed.lin, ed.col = 0, 11
    for c in "peg":
        aperta(ed, "", texto=c)
    assert [s[1] for s in ed.sugestoes] == ["pegar_casquinha", "pegar_de"]
    aperta(ed, "down")
    aperta(ed, "tab")
    assert ed.texto == "+ligado <- pegar_de("


def test_quebra_de_linha(ed):
    ed.definir_texto("+ligado <- " + "dancar; " * 30 + "dancar.")
    ed._montar_visual(40)
    assert len(ed._linhas_visuais) > 5 and all(b - a <= 40 for _, a, b in ed._linhas_visuais)
    assert "".join(ed.linhas[0][a:b] for _, a, b in ed._linhas_visuais) == ed.linhas[0]
