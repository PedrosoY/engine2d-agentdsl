"""Som da engine: efeitos (.ogg/.wav) e música de fundo, usando o mixer do pygame (SDL_mixer).

    self.motor.audio.tocar("Assets/Sons/laser.ogg", volume=0.6)
    self.motor.audio.musica("Assets/Sons/tema.ogg")

Se o computador não tiver saída de som (ou nos testes), tudo continua funcionando em silêncio.
"""
from __future__ import annotations

from pathlib import Path

import pygame


class Audio:
    def __init__(self, pasta_base: Path | None = None, mudo: bool = False):
        self.pasta_base = pasta_base
        self.volume_geral = 1.0
        self.ok = False
        self._sons: dict[str, pygame.mixer.Sound | None] = {}
        self.tocados = 0                    # quantos efeitos já tocaram (testes e estatísticas)
        if mudo:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 512)
            pygame.mixer.set_num_channels(32)
            self.ok = True
        except pygame.error as e:
            print(f"[audio] sem som: {e}")

    def _caminho(self, arquivo) -> Path:
        p = Path(arquivo)
        if not p.is_absolute() and self.pasta_base is not None:
            p = self.pasta_base / p
        return p

    def carregar(self, arquivo):
        chave = str(arquivo)
        if chave not in self._sons:
            som = None
            if self.ok:
                try:
                    som = pygame.mixer.Sound(str(self._caminho(arquivo)))
                except (pygame.error, FileNotFoundError) as e:
                    print(f"[audio] não consegui abrir '{arquivo}': {e}")
            self._sons[chave] = som
        return self._sons[chave]

    def tocar(self, arquivo, volume: float = 1.0, variar: float = 0.0) -> None:
        """Toca um efeito uma vez. ``variar`` sorteia um volume um pouco diferente (tiros repetidos
        ficam menos cansativos)."""
        if not arquivo:
            return
        self.tocados += 1
        som = self.carregar(arquivo)
        if som is None:
            return
        if variar:
            import random
            volume *= 1.0 - random.uniform(0, variar)
        canal = som.play()
        if canal is not None:
            canal.set_volume(max(0.0, min(1.0, volume * self.volume_geral)))

    def musica(self, arquivo, volume: float = 0.5, repetir: bool = True) -> None:
        if not self.ok or not arquivo:
            return
        try:
            pygame.mixer.music.load(str(self._caminho(arquivo)))
            pygame.mixer.music.set_volume(volume * self.volume_geral)
            pygame.mixer.music.play(-1 if repetir else 0)
        except pygame.error as e:
            print(f"[audio] música '{arquivo}': {e}")

    def parar_musica(self) -> None:
        if self.ok:
            pygame.mixer.music.stop()

    def parar_tudo(self) -> None:
        if self.ok:
            pygame.mixer.stop()
            pygame.mixer.music.stop()
