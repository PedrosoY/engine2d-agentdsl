"""Peças usadas por vários scripts: efeitos, pausa, tela de fim e log da DSL.

Outros scripts importam daqui com:  from Comum import criar_fumaca, painel_fim ...
"""
from engine2d import Animador, Componente, SpriteRenderer, TempoDeVida
from engine2d.ui import CORES

FUMACA = ["Assets/Sprites/Efeitos/fumaca1.png", "Assets/Sprites/Efeitos/fumaca2.png",
          "Assets/Sprites/Efeitos/fumaca3.png"]


def criar_fumaca(cena, x, y, escala=1.0, camada=6):
    """Explosão animada (três imagens em sequência; o objeto some no fim)."""
    cena.criar("fumaça", x, y, escala=escala, componentes=[
        SpriteRenderer(imagem=FUMACA[2], camada=camada, cor=(1, 1, 1, 0.9)),
        Animador(quadros=",".join(reversed(FUMACA)), fps=14, repetir=False, destruir_ao_fim=True)])


def criar_texto_flutuante(cena, x, y, texto, cor=(255, 230, 120)):
    cena.criar("texto", x, y, componentes=[TextoFlutuante(texto=texto), TempoDeVida(segundos=0.8)])
    cena.objetos[-1].obter("TextoFlutuante").cor_rgb = cor


class TextoFlutuante(Componente):
    CAMPOS = {"texto": "str"}
    texto = ""
    cor_rgb = (255, 230, 120)

    def atualizar(self, dt):
        self.transform.y += 40 * dt

    def desenhar_ui(self, ui):
        x, y = ui.mundo_para_tela(*self.transform.posicao_mundo)
        ui.texto(x, y, self.texto, 16, cor=self.cor_rgb, ancora="center", negrito=True)


class LogDSL(Componente):
    """Mostra no canto da tela as últimas mensagens de imprimir(...) dos agentes."""

    def iniciar(self):
        self.linhas = []
        srv = self.cena.servicos.get("agentes")
        if srv is not None:
            srv.ao_registrar = self.registrar

    def registrar(self, linha, tipo):
        if tipo in ("print", "erro"):
            self.linhas.append((linha, 5.0))
            del self.linhas[:-5]

    def atualizar(self, dt):
        self.linhas = [(l, t - dt) for l, t in self.linhas if t - dt > 0]

    def desenhar_ui(self, ui):
        y = ui.altura - 28
        for linha, _ in reversed(self.linhas):
            ui.texto(14, y, linha, 15, cor=(255, 230, 150) if "ERRO" not in linha else (255, 110, 110))
            y -= 20


class Pausa(Componente):
    """ESC pausa o jogo e mostra Continuar / Reiniciar / Sair."""

    def iniciar(self):
        self.motor.sair_com_esc = False
        self.aberta = False

    def desenhar_ui(self, ui):
        m = self.motor
        if m.entrada.tecla_baixou("escape"):
            self.aberta = not self.aberta
            m.pausado = self.aberta
        if self.aberta:
            ui.sobrepor(self._janela)

    def _janela(self, ui):
        m = self.motor
        ui.retangulo((0, 0, ui.largura, ui.altura), (0, 0, 0, 140), raio=0, bloquear=True)
        cx, cy = ui.largura // 2, ui.altura // 2
        ui.retangulo((cx - 160, cy - 120, 320, 240), borda=CORES["borda"])
        ui.texto(cx, cy - 92, "Pausado", 30, ancora="center", negrito=True)
        if ui.botao((cx - 110, cy - 50, 220, 40), "Continuar"):
            self.aberta = False
            m.pausado = False
        if ui.botao((cx - 110, cy + 0, 220, 40), "Reiniciar"):
            m.trocar_cena(self.cena.servicos["fabrica"])
        if ui.botao((cx - 110, cy + 50, 220, 40), "Sair"):
            m.rodando = False


def painel_fim(ui, motor, cena, titulo, linhas, cor=CORES["destaque"], extra=None):
    """Janela de fim de partida (desenhada por cima de tudo). ``extra`` = (rótulo, função)."""
    ui.sobrepor(lambda u: _painel_fim(u, motor, cena, titulo, linhas, cor, extra))


def _painel_fim(ui, motor, cena, titulo, linhas, cor, extra):
    ui.bloquear((0, 0, ui.largura, ui.altura))
    ui.retangulo((0, 0, ui.largura, ui.altura), (0, 0, 0, 150), raio=0)
    cx, cy = ui.largura // 2, ui.altura // 2
    h = 170 + 26 * len(linhas) + (54 if extra else 0)
    ui.retangulo((cx - 220, cy - h // 2, 440, h), borda=CORES["borda"])
    ui.texto(cx, cy - h // 2 + 36, titulo, 34, cor=cor, ancora="center", negrito=True)
    for i, l in enumerate(linhas):
        ui.texto(cx, cy - h // 2 + 80 + 26 * i, l, 18, ancora="center")
    yb = cy + h // 2 - 60
    if extra and ui.botao((cx - 200, yb - 52, 400, 40), extra[0]):
        extra[1]()
    if ui.botao((cx - 200, yb, 190, 42), "Jogar de novo"):
        motor.trocar_cena(cena.servicos["fabrica"])
    if ui.botao((cx + 10, yb, 190, 42), "Sair"):
        motor.rodando = False
