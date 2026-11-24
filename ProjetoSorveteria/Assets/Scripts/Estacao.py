"""Estações da sorveteria. Cada uma atende UM robô por vez (os outros esperam na fila)."""
from engine2d import Componente
from engine2d.ui import CORES
from Itens import icone_item

QUADROS_BATEDEIRA = ["Assets/Sprites/Estacoes/batedeira.png", "Assets/Sprites/Estacoes/batedeira_b.png",
                     "Assets/Sprites/Estacoes/batedeira_c.png"]


class Estacao(Componente):
    """``nome_dsl`` é o nome usado no programa (esta_em(maquina), deixar(bancada1)...).
    Estações ainda não compradas ficam com o objeto inativo."""

    CAMPOS = {"nome_dsl": "str", "titulo": "str"}
    nome_dsl = ""
    titulo = ""

    def iniciar(self):
        self.ocupante = None       # robô usando a estação agora
        self.progresso = 0.0       # 0..1 do trabalho em andamento (desenha a barrinha)
        self.item = None           # só nas bancadas: sorvete deixado por um robô
        self.render = self.obter("SpriteRenderer")
        self.t = 0.0
        self.cena.servicos.setdefault("estacoes", {})[self.nome_dsl] = self

    @property
    def disponivel(self):
        return self.gameobject.ativo

    @property
    def eh_bancada(self):
        return self.nome_dsl.startswith("bancada")

    def ponto(self, desvio=0.0):
        """Onde o robô fica para usar a estação (embaixo dela)."""
        x, y = self.transform.posicao_mundo
        return x + desvio, y - 64

    def reiniciar(self):
        self.ocupante = None
        self.progresso = 0.0
        self.item = None

    def atualizar(self, dt):
        if self.ocupante is not None and (self.ocupante.gameobject is None or self.ocupante.gameobject.destruido):
            self.ocupante = None
        if self.nome_dsl == "batedeira" and self.render:
            self.t += dt
            batendo = self.ocupante is not None and self.progresso > 0
            self.render.trocar_imagem(QUADROS_BATEDEIRA[1 + int(self.t * 8) % 2] if batendo
                                      else QUADROS_BATEDEIRA[0])

    def desenhar_ui(self, ui):
        if not self.motor:
            return
        x, y = ui.mundo_para_tela(*self.transform.posicao_mundo)
        ui.texto(x, y - 54, self.titulo or self.nome_dsl, 13, ancora="center", negrito=True)
        ui.texto(x, y - 39, self.nome_dsl, 11, ancora="center", cor=(255, 230, 140))
        if self.ocupante is not None and self.progresso > 0:
            ui.barra((x - 30, y + 44, 60, 7), self.progresso, cor=CORES["azul"])
        if self.item is not None:
            ui.desenhar_imagem(icone_item(self.item), x, y - 4, tamanho=34)
