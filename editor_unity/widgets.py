"""Peças de interface do editor (tema escuro, menus, campos de texto, arrastar e soltar).

Tudo é desenhado em modo imediato na CamadaUI da engine (uma Surface do pygame
enviada como textura): a cada quadro o editor redesenha os painéis e trata o mouse.
"""
from __future__ import annotations

import time

import pygame

# Cores do tema escuro
COR = {
    "fundo": (56, 56, 56), "fundo2": (48, 48, 48), "cabecalho": (40, 40, 40), "barra": (33, 33, 33),
    "borda": (25, 25, 25), "texto": (210, 210, 210), "texto2": (150, 150, 150), "campo": (42, 42, 42),
    "campo_ativo": (30, 30, 30), "selecao": (44, 93, 135), "selecao_fraca": (62, 70, 82),
    "hover": (70, 70, 70), "botao": (88, 88, 88), "botao_hover": (103, 103, 103), "destaque": (64, 128, 196),
    "vermelho": (225, 85, 85), "amarelo": (230, 190, 80), "verde": (110, 190, 110), "eixo_x": (219, 62, 29),
    "eixo_y": (113, 199, 45), "play": (80, 160, 230),
}
ALT = 20          # altura de uma linha de lista/campo


class Popup:
    """Menu suspenso: lista de (rótulo, ação | None, atalho)."""

    def __init__(self, x, y, itens, largura=230, titulo=None):
        self.itens = itens
        self.largura = largura
        self.titulo = titulo
        h = len(itens) * 22 + 6 + (24 if titulo else 0)
        self.rect = pygame.Rect(int(x), int(y), largura, h)

    def ajustar(self, w, h):
        if self.rect.right > w:
            self.rect.x = w - self.rect.w - 2
        if self.rect.bottom > h:
            self.rect.y = max(0, h - self.rect.h - 2)


class Campo:
    """Estado do campo de texto em edição (só um por vez no editor)."""

    def __init__(self, chave, texto, ao_confirmar, numerico=False):
        self.chave = chave
        self.texto = texto
        self.ao_confirmar = ao_confirmar
        self.numerico = numerico
        self.selecionar_tudo = True


class Arrasto:
    """O que está sendo arrastado entre painéis (asset do Project ou GameObject da Hierarchy)."""

    def __init__(self, tipo, valor, rotulo, inicio):
        self.tipo = tipo            # "asset" | "objeto"
        self.valor = valor
        self.rotulo = rotulo
        self.inicio = inicio
        self.ativo = False          # vira True depois de mover alguns pixels


class CliqueDuplo:
    def __init__(self):
        self.ultimo = (None, 0.0)

    def testar(self, alvo) -> bool:
        agora = time.time()
        a, t = self.ultimo
        self.ultimo = (alvo, agora)
        if a == alvo and agora - t < 0.4:
            self.ultimo = (None, 0.0)
            return True
        return False


def recortar(ui, rect):
    """Context manager simples: limita o desenho a ``rect``."""
    class _Clip:
        def __enter__(self_):
            self_.ant = ui.surface.get_clip()
            ui.surface.set_clip(pygame.Rect(rect))

        def __exit__(self_, *a):
            ui.surface.set_clip(self_.ant)
    return _Clip()


def painel(ui, rect, titulo=None, abas=None, aba_ativa=0):
    """Fundo de painel com cabeçalho/abas. Devolve a área útil e a aba clicada."""
    r = pygame.Rect(rect)
    pygame.draw.rect(ui.surface, COR["fundo"], r)
    pygame.draw.rect(ui.surface, COR["borda"], r, 1)
    cab = pygame.Rect(r.x, r.y, r.w, 22)
    pygame.draw.rect(ui.surface, COR["cabecalho"], cab)
    clicada = None
    if abas:
        x = r.x + 2
        for i, nome in enumerate(abas):
            w = ui.fonte(13, True).size(nome)[0] + 22
            ra = pygame.Rect(x, r.y + 2, w, 20)
            pygame.draw.rect(ui.surface, COR["fundo"] if i == aba_ativa else COR["cabecalho"], ra,
                             border_top_left_radius=3, border_top_right_radius=3)
            ui.texto(ra.centerx, ra.centery, nome, 13, cor=COR["texto"] if i == aba_ativa else COR["texto2"],
                     ancora="center", negrito=i == aba_ativa, sombra=False)
            if ra.collidepoint(ui.motor.entrada.mouse_tela) and ui.motor.entrada.clicou(1):
                clicada = i
            x += w + 2
    elif titulo:
        ra = pygame.Rect(r.x + 2, r.y + 2, ui.fonte(13, True).size(titulo)[0] + 22, 20)
        pygame.draw.rect(ui.surface, COR["fundo"], ra, border_top_left_radius=3, border_top_right_radius=3)
        ui.texto(ra.centerx, ra.centery, titulo, 13, ancora="center", negrito=True, sombra=False)
    return pygame.Rect(r.x + 1, r.y + 23, r.w - 2, r.h - 24), clicada


def botao(ui, rect, rotulo, mouse_livre=True, ativo=True, destacado=False, tamanho=13, cor=None):
    r = pygame.Rect(rect)
    ent = ui.motor.entrada
    hover = mouse_livre and ativo and r.collidepoint(ent.mouse_tela)
    fundo = cor or (COR["destaque"] if destacado else (COR["botao_hover"] if hover else COR["botao"]))
    if not ativo:
        fundo = COR["fundo2"]
    pygame.draw.rect(ui.surface, fundo, r, border_radius=3)
    pygame.draw.rect(ui.surface, COR["borda"], r, 1, border_radius=3)
    ui.texto(r.centerx, r.centery, rotulo, tamanho, ancora="center", sombra=False,
             cor=COR["texto"] if ativo else COR["texto2"])
    if hover and ent.clicou(1):
        ent.consumir_clique()     # o clique não vale para mais nada (ex.: o menu que o botão abre)
        return True
    return False


def icone_arquivo(ui, rect, extensao, cor):
    """Ícone genérico: folha com a extensão escrita (para .py, .agt, .cena...)."""
    r = pygame.Rect(rect)
    folha = r.inflate(-r.w * 0.3, -r.h * 0.15)
    pygame.draw.rect(ui.surface, (225, 225, 225), folha, border_radius=3)
    pygame.draw.rect(ui.surface, cor, (folha.x, folha.bottom - folha.h * 0.38, folha.w, folha.h * 0.38),
                     border_bottom_left_radius=3, border_bottom_right_radius=3)
    ui.texto(folha.centerx, folha.bottom - folha.h * 0.19, extensao, max(9, int(folha.h * 0.22)),
             ancora="center", negrito=True, sombra=False, cor=(255, 255, 255))


def icone_pasta(ui, rect):
    r = pygame.Rect(rect).inflate(-8, -14)
    pygame.draw.rect(ui.surface, (196, 160, 80), (r.x, r.y, r.w * 0.45, r.h * 0.25), border_radius=2)
    pygame.draw.rect(ui.surface, (226, 186, 96), (r.x, r.y + r.h * 0.15, r.w, r.h * 0.85), border_radius=3)


def seta(ui, cx, cy, aberto, cor=(170, 170, 170)):
    """Triângulo de abrir/fechar da árvore (▼ aberto, ► fechado)."""
    if aberto:
        pts = [(cx - 4, cy - 2), (cx + 4, cy - 2), (cx, cy + 3)]
    else:
        pts = [(cx - 2, cy - 4), (cx + 3, cy), (cx - 2, cy + 4)]
    pygame.draw.polygon(ui.surface, cor, pts)

