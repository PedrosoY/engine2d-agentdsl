"""Janelas flutuantes (como no The Farmer Was Replaced): arrastar pela barra, redimensionar pelo canto,
minimizar e fechar. Tipos: código (controla todos os robôs, um robô ou o gerente), informação e saída."""
import pygame

from EditorCodigo import EditorCodigo

BARRA = 26
CANTO = 18
MIN_W, MIN_H = 260, 150
COR_JANELA = (26, 28, 36)
COR_BARRA = (44, 48, 62)
COR_BARRA_ATIVA = (58, 70, 104)


class Janela:
    contador = 0

    def __init__(self, tipo, rect, titulo=""):
        Janela.contador += 1
        self.id = Janela.contador
        self.tipo = tipo
        self.rect = pygame.Rect(rect)
        self.titulo = titulo
        self.minimizada = False
        self.fechada = False
        self.rolagem = 0

    @property
    def area_visivel(self):
        return pygame.Rect(self.rect.x, self.rect.y, self.rect.w, BARRA) if self.minimizada else self.rect

    def corpo(self):
        return pygame.Rect(self.rect.x + 1, self.rect.y + BARRA, self.rect.w - 2, self.rect.h - BARRA - 1)

    def estado(self):
        return {"tipo": self.tipo, "rect": list(self.rect), "minimizada": self.minimizada, "fechada": self.fechada}


class JanelaCodigo(Janela):
    def __init__(self, rect, alvo="todos", texto=""):
        super().__init__("codigo", rect)
        self.alvo = alvo                 # "todos" | "robo2" | "gerente"
        self.editor = EditorCodigo(texto)
        self.erros = []                  # [(diagnóstico local, mensagem amigável, dica)]
        self.status = ("", (190, 195, 210))

    @property
    def modelo(self):
        return "todos" if self.alvo == "todos" else f"janela{self.id}"

    @property
    def nome_alvo(self):
        return {"todos": "Todos os robôs", "gerente": "Gerente"}.get(self.alvo, self.alvo)

    def estado(self):
        d = super().estado()
        d.update(alvo=self.alvo, texto=self.editor.texto)
        return d


class JanelaInfo(Janela):
    """Janela de informação: mostra o passo do tutorial ou um resumo dos comandos."""

    def __init__(self, rect):
        super().__init__("info", rect, "Informação")


class JanelaSaida(Janela):
    def __init__(self, rect):
        super().__init__("saida", rect, "Saída")


class Arrastar:
    """Controle de arrastar/redimensionar a janela segurada com o mouse."""

    def __init__(self):
        self.janela = None
        self.modo = None        # "mover" ou as bordas puxadas: "d" (direita), "e", "b" (baixo), "db"...
        self.origem = (0, 0)
        self.rect0 = None

    def comecar(self, janela, modo, mouse):
        self.janela, self.modo, self.origem, self.rect0 = janela, modo, mouse, janela.rect.copy()

    def atualizar(self, mouse, pressionado, w_tela, h_tela, topo):
        if self.janela is None:
            return
        if not pressionado:
            self.janela = None
            return
        dx, dy = mouse[0] - self.origem[0], mouse[1] - self.origem[1]
        r, r0 = self.janela.rect, self.rect0
        if self.modo == "mover":
            r.x = max(0, min(w_tela - r.w, r0.x + dx))
            r.y = max(topo, min(h_tela - self.janela.area_visivel.h, r0.y + dy))
            return
        if "d" in self.modo:
            r.w = max(MIN_W, min(w_tela - r.x, r0.w + dx))
        if "e" in self.modo:
            x = max(0, min(r0.right - MIN_W, r0.x + dx))
            r.x, r.w = x, r0.right - x
        if "b" in self.modo:
            r.h = max(MIN_H, min(h_tela - r.y, r0.h + dy))


def manter_na_tela(jan, w_tela, h_tela, topo):
    """A janela inteira fica sempre dentro da tela (também quando a tela muda de tamanho)."""
    r = jan.rect
    r.w = max(MIN_W, min(r.w, w_tela))
    r.h = max(MIN_H, min(r.h, h_tela - topo))
    r.x = max(0, min(r.x, w_tela - r.w))
    r.y = max(topo, min(r.y, h_tela - jan.area_visivel.h))


def borda(jan, mouse):
    """Qual borda da janela está sob o mouse: "" (nenhuma), "d", "e", "b", "db" ou "eb"."""
    if jan.minimizada:
        return ""
    r, (mx, my) = jan.rect, mouse
    if not r.inflate(12, 12).collidepoint(mouse) or my < r.y + BARRA:
        return ""
    if mx >= r.right - CANTO and my >= r.bottom - CANTO:
        return "db"
    if mx <= r.x + CANTO and my >= r.bottom - CANTO:
        return "eb"
    lados = ""
    if mx >= r.right - 5:
        lados += "d"
    elif mx <= r.x + 5:
        lados += "e"
    if my >= r.bottom - 5:
        lados += "b"
    return lados


CURSORES = {"d": "SYSTEM_CURSOR_SIZEWE", "e": "SYSTEM_CURSOR_SIZEWE", "b": "SYSTEM_CURSOR_SIZENS",
            "db": "SYSTEM_CURSOR_SIZENWSE", "eb": "SYSTEM_CURSOR_SIZENESW", "mover": "SYSTEM_CURSOR_SIZEALL"}


def botao(ui, rect, rotulo, ativo_mouse, ent, cor=(56, 60, 76), cor_texto=(230, 232, 240), tamanho=12,
          habilitado=True, dica=None):
    """Botão das janelas: só responde se a janela for a de cima do mouse (``ativo_mouse``)."""
    r = pygame.Rect(rect)
    hover = ativo_mouse and r.collidepoint(ent.mouse_tela)
    c = cor if habilitado else (40, 42, 50)
    if hover and habilitado:
        c = tuple(min(255, v + 25) for v in c)
    pygame.draw.rect(ui.surface, c, r, border_radius=4)
    ui.texto(r.centerx, r.centery, rotulo, tamanho, ancora="center", sombra=False,
             cor=cor_texto if habilitado else (120, 120, 130))
    if hover and dica:
        ui._dica = (dica, ent.mouse_tela)
    if hover and habilitado and ent.clicou(1):
        ent.consumir_clique()
        return True
    return False


def desenhar_moldura(ui, jan, ativa, ent, mouse_aqui):
    """Desenha a moldura e devolve a ação da barra: None | "minimizar" | "fechar"."""
    r = jan.area_visivel
    sombra = pygame.Surface((r.w + 8, r.h + 8), pygame.SRCALPHA)
    pygame.draw.rect(sombra, (0, 0, 0, 70), sombra.get_rect(), border_radius=8)
    ui.surface.blit(sombra, (r.x - 2, r.y + 2))
    pygame.draw.rect(ui.surface, COR_JANELA, r, border_radius=6)
    pygame.draw.rect(ui.surface, COR_BARRA_ATIVA if ativa else COR_BARRA, (r.x, r.y, r.w, BARRA),
                     border_top_left_radius=6, border_top_right_radius=6,
                     border_bottom_left_radius=6 if jan.minimizada else 0,
                     border_bottom_right_radius=6 if jan.minimizada else 0)
    pygame.draw.rect(ui.surface, (90, 140, 220) if ativa else (64, 68, 84), r, 1, border_radius=6)
    acao = None
    if botao(ui, (r.right - 24, r.y + 4, 20, 18), "x", mouse_aqui, ent, cor=(120, 50, 55), dica="fechar"):
        acao = "fechar"
    if botao(ui, (r.right - 48, r.y + 4, 20, 18), "+" if jan.minimizada else "_", mouse_aqui, ent,
             dica="restaurar" if jan.minimizada else "minimizar"):
        acao = "minimizar"
    if not jan.minimizada:      # alça de redimensionar
        cx, cy = r.right - 3, r.bottom - 3
        for k in (4, 8, 12):
            pygame.draw.line(ui.surface, (110, 115, 135), (cx - k, cy), (cx, cy - k), 1)
    return acao


def no_canto(jan, mouse):
    r = jan.rect
    return not jan.minimizada and r.right - CANTO <= mouse[0] <= r.right and r.bottom - CANTO <= mouse[1] <= r.bottom


def na_barra(jan, mouse):
    r = jan.rect
    return r.x <= mouse[0] <= r.right - 52 and r.y <= mouse[1] <= r.y + BARRA
