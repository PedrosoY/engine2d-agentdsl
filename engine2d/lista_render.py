"""Lista de renderização: os sprites visíveis e a ordenação por camada (L_A < L_B ⇒ A antes).

A chave de ordenação é (camada de desenho, ordem na camada, ordem na hierarquia): primeiro a camada
de desenho (lista do projeto: Fundo, Padrao, Frente...), depois o número "ordem" do SpriteRenderer e,
empatando, quem vem depois na Hierarchy é desenhado por cima.
"""
from __future__ import annotations

from .sprite import Sprite


class ListaRenderizacao:
    """Guarda os sprites a desenhar e os entrega ordenados por camada.

    A ordenação é estável: dentro da mesma camada vale a ordem de inserção
    (o último adicionado aparece por cima). A lista só é reordenada quando
    um sprite entra, sai ou muda de camada, não a cada quadro.
    """

    def __init__(self, agrupar_texturas: bool = False):
        # agrupar_texturas=True: dentro da MESMA camada ordena também pela textura.
        # A ordem entre camadas continua garantida, mas a ordem de inserção dentro
        # de uma camada deixa de valer. Reduz as quebras de lote no renderizador.
        self.agrupar_texturas = agrupar_texturas
        # dict em vez de list: mantém a ordem de inserção e remove em O(1) (partículas e tiros
        # entram e saem às dezenas por quadro)
        self._sprites: dict[Sprite, None] = {}
        self._ordenados: list[Sprite] = []
        self._precisa_ordenar = False
        self.ordenacoes = 0  # contador para o benchmark

    def adicionar(self, sprite: Sprite) -> Sprite:
        sprite.lista = self
        self._sprites[sprite] = None
        self._precisa_ordenar = True
        return sprite

    def remover(self, sprite: Sprite) -> None:
        if self._sprites.pop(sprite, 0) is None:
            sprite.lista = None
            self._precisa_ordenar = True

    def limpar(self) -> None:
        for s in self._sprites:
            s.lista = None
        self._sprites.clear()
        self._precisa_ordenar = True

    def marcar_reordenar(self) -> None:
        self._precisa_ordenar = True

    def ordenados(self) -> list[Sprite]:
        """Sprites em ordem de desenho: camada crescente (L_A < L_B ⇒ A antes de B)."""
        if self._precisa_ordenar:
            # sorted() do Python é estável (Timsort): mantém a ordem de inserção.
            # camada de desenho → ordem na camada → ordem na hierarquia → ordem de inserção
            if self.agrupar_texturas:
                chave = lambda s: (*s.chave_ordem, s.textura.id)  # noqa: E731
            else:
                chave = lambda s: s.chave_ordem  # noqa: E731
            self._ordenados = sorted(self._sprites, key=chave)
            self._precisa_ordenar = False
            self.ordenacoes += 1
        return self._ordenados

    def sprite_em(self, x: float, y: float) -> Sprite | None:
        """Sprite visível mais à frente que contém o ponto (para seleção com o mouse)."""
        for s in reversed(self.ordenados()):
            if s.visivel and not s.espaco_tela and s.contem_ponto(x, y):
                return s
        return None

    def por_nome(self, nome: str) -> Sprite | None:
        for s in self._sprites:
            if s.nome == nome:
                return s
        return None

    def __len__(self) -> int:
        return len(self._sprites)

    def __iter__(self):
        return iter(self._sprites)
