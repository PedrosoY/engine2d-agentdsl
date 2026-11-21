"""Motor: janela, contexto OpenGL, loop principal e serviços globais."""
from __future__ import annotations

import os
import sys
import time
import traceback
from collections import deque
from pathlib import Path

import numpy as np
import pygame
from OpenGL import GL

from .camera import Camera2D
from .entrada import Entrada
from .renderizador import Renderizador
from .textura import GerenciadorTexturas


class Motor:
    """Ponto de entrada da engine.

    Loop de cada quadro:
        eventos → entrada → [editor] → cena.atualizar (Start/Update/física/Destroy)
        → sincronizar sprites → UI (OnGUI) → ordenar por camada → desenhar → apresentar
    """

    def __init__(self, largura: int = 1280, altura: int = 720, titulo: str = "Engine2D",
                 vsync: bool = True, visivel: bool = True, modo_render: str = "lote",
                 pasta_assets: str | Path | None = None, editor: bool = True):
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        if not visivel:
            flags |= pygame.HIDDEN
        pygame.display.set_mode((largura, altura), flags, vsync=1 if vsync else 0)
        pygame.display.set_caption(titulo)
        self.titulo = titulo
        self.largura, self.altura = largura, altura

        self.texturas = GerenciadorTexturas(pasta_assets)
        self.renderizador = Renderizador(largura, altura, modo_render)
        self.camera = Camera2D(largura, altura)
        self.entrada = Entrada(self)
        from .ui import CamadaUI
        self.ui = CamadaUI(self)
        self.cena = None
        self.editor = None
        if editor:
            from .editor import Editor
            self.editor = Editor(self)
        self.rodando = False
        self.pausado = False
        self.escala_tempo = 1.0
        self.sair_com_esc = True
        self.quadro = 0
        self.tempo_total = 0.0
        self._tempos_quadro = deque(maxlen=120)
        self.tempos = {"atualizar": 0.0, "render": 0.0, "ui": 0.0}
        self._capturas: list = []
        self._proxima_cena = None
        self.erro_atual = None   # (mensagem, onde) quando um quadro levantou exceção
        self.info_gl = {
            "renderer": GL.glGetString(GL.GL_RENDERER).decode(errors="ignore"),
            "versao": GL.glGetString(GL.GL_VERSION).decode(errors="ignore"),
        }

    # --- cena -------------------------------------------------------------------
    def carregar_cena(self, cena) -> None:
        if self.cena is not None:
            for g in list(self.cena.objetos):
                self.cena._destruir_agora(g)
        cena.motor = self
        self.cena = cena
        self.camera.x, self.camera.y, self.camera.zoom = self.largura / 2, self.altura / 2, 1.0
        if self.editor:
            self.editor.selecionado = None

    def trocar_cena(self, fabrica) -> None:
        """Troca de cena no início do próximo quadro (seguro de chamar de dentro de um componente).
        ``fabrica`` é uma Cena ou uma função sem argumentos que devolve a Cena."""
        self._proxima_cena = fabrica

    def carregar_textura(self, caminho):
        return self.texturas.carregar(caminho)

    # --- métricas -------------------------------------------------------------------
    @property
    def fps_medio(self) -> float:
        return 1.0 / max(float(np.mean(self._tempos_quadro)), 1e-9) if self._tempos_quadro else 0.0

    @property
    def ms_quadro_medio(self) -> float:
        return float(np.mean(self._tempos_quadro) * 1000) if self._tempos_quadro else 0.0

    # --- loop -----------------------------------------------------------------------
    def passo(self, dt: float) -> None:
        """Um quadro completo (também usado pelos testes e benchmarks)."""
        if self._proxima_cena is not None:
            fab, self._proxima_cena = self._proxima_cena, None
            self.pausado, self.escala_tempo = False, 1.0
            self.carregar_cena(fab() if callable(fab) else fab)
        cena = self.cena
        ed = self.editor
        self.ui.limpar()
        t0 = time.perf_counter()
        if ed is not None:
            ed.processar_entrada()
        simular = not self.pausado and not (ed is not None and ed.ativo and not ed.rodando)
        if ed is not None and ed.passo_unico:
            simular, ed.passo_unico = True, False
        if simular:
            cena.atualizar(dt * self.escala_tempo)
        else:
            cena.iniciar_pendentes()
            cena.processar_destruicoes(0.0)
        cena.sincronizar_render()
        t1 = time.perf_counter()
        cena.desenhar_ui(self.ui)
        if ed is not None:
            ed.desenhar(self.ui)
        self.ui.desenhar_sobreposicoes()
        self.ui.desenhar_dicas()
        self.ui.enviar()
        t2 = time.perf_counter()
        self.renderizador.limpar()
        self.renderizador.desenhar(cena.lista, self.camera, extras_tela=[self.ui.sprite])
        if self._capturas:
            self._salvar_captura(self._capturas.pop(0))
        pygame.display.flip()
        t3 = time.perf_counter()
        k = 0.1
        self.tempos["atualizar"] += ((t1 - t0) * 1000 - self.tempos["atualizar"]) * k
        self.tempos["ui"] += ((t2 - t1) * 1000 - self.tempos["ui"]) * k
        self.tempos["render"] += ((t3 - t2) * 1000 - self.tempos["render"]) * k

    def executar(self, cena=None, max_quadros: int | None = None, captura: str | None = None) -> None:
        if cena is not None:
            self.carregar_cena(cena)
        self.rodando = True
        anterior = time.perf_counter()
        while self.rodando:
            agora = time.perf_counter()
            dt = min(agora - anterior, 0.05)
            anterior = agora
            self.entrada.novo_quadro()
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.rodando = False
                elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE and self.sair_com_esc \
                        and not (self.editor and self.editor.ativo):
                    self.rodando = False
                self.entrada.processar(ev)
            if max_quadros is not None and captura and self.quadro == max_quadros - 1:
                self._capturas.append(captura)
            if self.erro_atual is not None:
                self._quadro_de_erro()
            else:
                try:
                    self.passo(dt)
                except Exception as e:   # um bug num componente não pode congelar a janela
                    if os.environ.get("ENGINE2D_LEVANTAR_ERROS") == "1":
                        raise
                    self._registrar_erro(e)
            self._tempos_quadro.append(dt)
            self.tempo_total += dt
            self.quadro += 1
            if max_quadros is not None and self.quadro >= max_quadros:
                self.rodando = False

    # --- erros ---------------------------------------------------------------------
    def _registrar_erro(self, e: Exception) -> None:
        """Guarda o traceback em erros.log, mostra na tela e pausa (em vez de travar)."""
        detalhe = traceback.format_exc()
        print(detalhe, file=sys.stderr, flush=True)
        try:
            with open("erros.log", "a", encoding="utf-8") as f:
                f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} (quadro {self.quadro}, cena "
                        f"{getattr(self.cena, 'nome', '?')})\n{detalhe}\n")
        except OSError:
            pass
        linhas = [l.strip() for l in detalhe.strip().splitlines()]
        onde = next((l for l in reversed(linhas) if l.startswith("File ") and "engine_agentes" in l), "")
        self.erro_atual = (f"{type(e).__name__}: {e}"[:150], onde[-150:])

    def _quadro_de_erro(self) -> None:
        """Tela de erro: ENTER continua, F2 reinicia a cena atual, ESC sai."""
        ent = self.entrada
        if ent.tecla_baixou("return"):
            self.erro_atual = None
            return
        if ent.tecla_baixou("f2") and self.cena is not None and "fabrica" in self.cena.servicos:
            self.erro_atual = None
            self.trocar_cena(self.cena.servicos["fabrica"])
            return
        if ent.tecla_baixou("escape"):
            self.rodando = False
            return
        from .ui import CORES
        ui = self.ui
        ui.limpar()
        ui.retangulo((90, 200, ui.largura - 180, 300), (40, 10, 10, 235), borda=CORES["vermelho"])
        ui.texto(ui.largura / 2, 240, "Ocorreu um erro no jogo", 28, cor=CORES["vermelho"], ancora="center",
                 negrito=True)
        msg, onde = self.erro_atual
        ui.texto(ui.largura / 2, 300, msg, 16, ancora="center")
        ui.texto(ui.largura / 2, 330, onde, 13, ancora="center", cor=(200, 200, 200))
        ui.texto(ui.largura / 2, 380, "Detalhes completos em erros.log", 15, ancora="center", cor=(220, 220, 220))
        ui.texto(ui.largura / 2, 440, "ENTER continua  ·  F2 reinicia a cena  ·  ESC sai", 18, ancora="center",
                 cor=CORES["destaque"])
        try:
            ui.enviar()
            self.renderizador.limpar()
            self.renderizador.desenhar(self.cena.lista, self.camera, extras_tela=[ui.sprite])
        except Exception:
            pass
        pygame.display.flip()

    def capturar_tela(self, caminho) -> None:
        """Salva o próximo quadro desenhado como PNG."""
        self._capturas.append(caminho)

    def _salvar_captura(self, caminho) -> None:
        from PIL import Image
        GL.glPixelStorei(GL.GL_PACK_ALIGNMENT, 1)
        dados = GL.glReadPixels(0, 0, self.largura, self.altura, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
        img = Image.frombytes("RGBA", (self.largura, self.altura), dados)
        img.transpose(Image.FLIP_TOP_BOTTOM).save(caminho)

    def encerrar(self) -> None:
        pygame.quit()
