"""Lista de renderização: os sprites visíveis e a ordenação por camada (L_A < L_B ⇒ A antes)."""
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
        self._sprites: list[Sprite] = []
        self._ordenados: list[Sprite] = []
        self._precisa_ordenar = False
        self.ordenacoes = 0  # contador para o benchmark

    def adicionar(self, sprite: Sprite) -> Sprite:
        sprite.lista = self
        self._sprites.append(sprite)
        self._precisa_ordenar = True
        return sprite

    def remover(self, sprite: Sprite) -> None:
        if sprite in self._sprites:
            self._sprites.remove(sprite)
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
            if self.agrupar_texturas:
                chave = lambda s: (s.camada, s.textura.id)  # noqa: E731
            else:
                chave = lambda s: s.camada  # noqa: E731
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
