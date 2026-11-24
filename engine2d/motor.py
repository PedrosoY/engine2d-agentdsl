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
        → sincronizar sprites → UI → ordenar por camada → desenhar → apresentar
    """

    def __init__(self, largura: int = 1280, altura: int = 720, titulo: str = "Engine2D",
                 vsync: bool = True, visivel: bool = True, modo_render: str = "lote",
                 pasta_assets: str | Path | None = None, editor: bool = True,
                 redimensionavel: bool = False, maximizada: bool = False, tela_cheia: bool = False):
        """``tela_cheia``: a janela ocupa o monitor inteiro (sem borda) e o jogo, desenhado na sua
        resolução (largura x altura) num framebuffer, é ampliado para a tela mantendo a proporção."""
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        if not visivel:
            flags |= pygame.HIDDEN
        if (redimensionavel or maximizada) and not tela_cheia:
            flags |= pygame.RESIZABLE
        tamanho_janela = (largura, altura)
        if tela_cheia:
            info = pygame.display.Info()
            tamanho_janela = (info.current_w, info.current_h)
            os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
            flags |= pygame.NOFRAME          # janela sem borda do tamanho do monitor (alt+tab funciona)
        pygame.display.set_mode(tamanho_janela, flags, vsync=1 if vsync else 0)
        pygame.display.set_caption(titulo)
        self.titulo = titulo
        self.largura, self.altura = largura, altura
        self.tela_cheia = tela_cheia
        self.tamanho_janela = tamanho_janela
        # configurações do projeto (Motor.configurar_projeto): valem para toda cena carregada
        self.camadas_desenho: list[str] = ["Fundo", "Padrao", "Frente"]
        self._indices_camadas = {n: i for i, n in enumerate(self.camadas_desenho)}
        self.gravidade = (0.0, 0.0)
        self.colisoes_ignoradas: list[str] = []
        self.tags: list[str] = []

        self.texturas = GerenciadorTexturas(pasta_assets)
        from .audio import Audio
        self.audio = Audio(Path(pasta_assets) if pasta_assets else None,
                           mudo=not visivel or os.environ.get("ENGINE2D_MUDO") == "1")
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
        self._tremor = [0.0, 0.0, 1.0]           # força, tempo que falta, duração
        self.mostrar_estatisticas = False         # F3 liga/desliga o painel
        self.tecla_estatisticas = "f3"            # um jogo que já usa o F3 pode trocar
        self._fps_janela = deque()
        self._eventos_ant = (time.perf_counter(), 0)
        self._eventos_por_s = 0.0
        self.erro_atual = None   # (mensagem, onde) quando um quadro levantou exceção
        if maximizada and visivel and not tela_cheia:
            self.maximizar()
        self._fbo = None
        if tela_cheia:
            self._criar_fbo()
        self.info_gl = {
            "renderer": GL.glGetString(GL.GL_RENDERER).decode(errors="ignore"),
            "versao": GL.glGetString(GL.GL_VERSION).decode(errors="ignore"),
        }

    # --- configurações do projeto --------------------------------------------------------
    def configurar_projeto(self, config: dict) -> None:
        """Camadas de desenho, gravidade, tags e pares de camadas físicas que não colidem
        (``Projeto.configuracoes()``). Valem para a cena atual e para as próximas."""
        self.camadas_desenho = list(config.get("camadas_desenho") or self.camadas_desenho)
        self._indices_camadas = {n: i for i, n in enumerate(self.camadas_desenho)}
        self.gravidade = tuple(config.get("gravidade", self.gravidade))
        self.colisoes_ignoradas = list(config.get("colisoes_ignoradas", self.colisoes_ignoradas))
        self.tags = list(config.get("tags", self.tags))
        if self.cena is not None:
            self._aplicar_fisica(self.cena)

    def indice_camada(self, nome: str) -> int:
        """Posição da camada de desenho (as primeiras ficam atrás). Nome desconhecido = "Padrao"."""
        i = self._indices_camadas.get(nome)
        if i is None:
            i = self._indices_camadas.get("Padrao", 0)
        return i

    def _aplicar_fisica(self, cena) -> None:
        cena.fisica.gravidade = tuple(self.gravidade)
        for par in self.colisoes_ignoradas:
            if ":" in par:
                a, b = (p.strip() for p in par.split(":", 1))
                cena.fisica.ignorar(a, b)

    # --- tela cheia: o jogo desenha num framebuffer e ele é ampliado para o monitor ------------
    def _criar_fbo(self) -> None:
        from .sprite import Sprite
        from .textura import Textura
        self._tex_fbo = Textura(np.zeros((self.altura, self.largura, 4), np.uint8), nome="tela",
                                filtro_suave=True)
        self._fbo = GL.glGenFramebuffers(1)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, self._tex_fbo.id, 0)
        ok = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) == GL.GL_FRAMEBUFFER_COMPLETE
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        if not ok:
            print("[motor] framebuffer incompleto: tela cheia sem ampliação")
            self._fbo = None
            return
        self._sprite_fbo = Sprite(self._tex_fbo, self.largura / 2, self.altura / 2, nome="tela")
        jw, jh = self.tamanho_janela
        esc = min(jw / self.largura, jh / self.altura)
        w, h = int(self.largura * esc), int(self.altura * esc)
        self._area_tela = ((jw - w) // 2, (jh - h) // 2, w, h)     # faixas pretas se a proporção não bater
        x0, y0, w, h = self._area_tela
        self.entrada.converter_mouse = lambda p: ((p[0] - x0) / esc, (p[1] - y0) / esc)

    def _comecar_desenho(self) -> None:
        if self._fbo is not None:
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._fbo)
            GL.glViewport(0, 0, self.largura, self.altura)

    def _apresentar(self) -> None:
        if self._fbo is not None:
            from . import matematica
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
            jw, jh = self.tamanho_janela
            GL.glViewport(0, 0, jw, jh)
            GL.glClearColor(0, 0, 0, 1)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            x0, y0, w, h = self._area_tela
            GL.glViewport(x0, jh - y0 - h, w, h)
            self.renderizador._individual([self._sprite_fbo],
                                          matematica.ortografica(0, self.largura, 0, self.altura))
            GL.glViewport(0, 0, self.largura, self.altura)
        pygame.display.flip()

    # --- janela -------------------------------------------------------------------
    def maximizar(self) -> None:
        """Maximiza a janela (como o botão de maximizar do Windows) e ajusta tudo ao novo tamanho."""
        try:
            from pygame._sdl2.video import Window
            Window.from_display_module().maximize()
        except Exception:
            try:   # alternativa no Windows: pede ao sistema para maximizar a janela
                import ctypes
                hwnd = pygame.display.get_wm_info()["window"]
                ctypes.windll.user32.ShowWindow(hwnd, 3)   # 3 = SW_MAXIMIZE
            except Exception:
                return
        pygame.event.pump()
        self.redimensionar(*pygame.display.get_window_size())

    def redimensionar(self, largura: int, altura: int) -> None:
        """Chamado quando o tamanho da janela muda (maximizar, arrastar a borda)."""
        largura, altura = max(320, int(largura)), max(240, int(altura))
        if (largura, altura) == (self.largura, self.altura):
            return
        self.largura, self.altura = largura, altura
        self.renderizador.redimensionar(largura, altura)
        self.camera.redimensionar(largura, altura)
        self.ui.redimensionar(largura, altura)

    def tratar_evento_janela(self, ev) -> bool:
        """Trata eventos de tamanho de janela. Devolve True se o tamanho mudou."""
        if ev.type == pygame.VIDEORESIZE:
            self.redimensionar(ev.w, ev.h)
            return True
        if ev.type == getattr(pygame, "WINDOWSIZECHANGED", -1):
            self.redimensionar(*pygame.display.get_window_size())
            return True
        return False

    # --- cena -------------------------------------------------------------------
    def carregar_cena(self, cena) -> None:
        if self.cena is not None:
            for g in list(self.cena.objetos):
                self.cena._destruir_agora(g)
        cena.motor = self
        self.cena = cena
        self._aplicar_fisica(cena)
        self.camera.x, self.camera.y, self.camera.zoom = self.largura / 2, self.altura / 2, 1.0
        if self.editor:
            self.editor.selecionado = None

    def trocar_cena(self, fabrica) -> None:
        """Troca de cena no início do próximo quadro (seguro de chamar de dentro de um componente).
        ``fabrica`` é uma Cena, uma função sem argumentos que devolve a Cena, ou o caminho de um
        arquivo .cena (ex.: "Assets/Cenas/Fase1.cena")."""
        if isinstance(fabrica, (str, Path)):
            fabrica = self._fabrica_de_arquivo(fabrica)
        self._proxima_cena = fabrica

    def reiniciar_cena(self) -> None:
        """Recarrega a cena atual do arquivo de onde ela veio (ex.: depois do fim de jogo)."""
        origem = getattr(self.cena, "arquivo", None)
        if origem:
            self.trocar_cena(origem)
        elif self.cena is not None and "fabrica" in self.cena.servicos:
            self.trocar_cena(self.cena.servicos["fabrica"])

    @staticmethod
    def _fabrica_de_arquivo(caminho):
        def criar():
            from .cena import Cena
            c = Cena(Path(caminho).stem)
            c.carregar(caminho)
            return c
        return criar

    def carregar_textura(self, caminho):
        return self.texturas.carregar(caminho)

    # --- tremor de câmera ------------------------------------------------------------------
    def tremer(self, forca: float = 8.0, duracao: float = 0.3) -> None:
        """Faz a tela tremer (explosão, impacto). Vários tremores juntos: vale o mais forte."""
        if forca * duracao >= self._tremor[0] * self._tremor[1]:
            self._tremor = [float(forca), float(duracao), float(duracao)]

    def _deslocamento_tremor(self, dt):
        forca, resta, total = self._tremor
        if resta <= 0:
            return 0.0, 0.0
        self._tremor[1] = max(0.0, resta - dt)
        k = forca * (resta / total) / max(self.camera.zoom, 1e-3)    # vai diminuindo até parar
        import random
        return random.uniform(-k, k), random.uniform(-k, k)

    # --- painel de estatísticas (F3) ---------------------------------------------------------
    def _desenhar_estatisticas(self, ui, dt):
        """F3 em qualquer jogo: o que a engine está fazendo neste quadro."""
        agora = time.perf_counter()
        self._fps_janela.append(agora)
        while self._fps_janela and agora - self._fps_janela[0] > 1.0:
            self._fps_janela.popleft()
        st = self.renderizador.stats
        cena = self.cena
        fis = cena.fisica
        linhas = [
            f"FPS {len(self._fps_janela):3d}   quadro {self.tempos['atualizar'] + self.tempos['ui'] + self.tempos['render']:5.1f} ms",
            f"atualizar {self.tempos['atualizar']:5.1f}  ui {self.tempos['ui']:5.1f}  render {self.tempos['render']:5.1f} ms",
            f"objetos {len(cena.objetos)}   sprites {len(cena.lista)}",
            f"desenhados {st.sprites_desenhados}   culling descartou {st.descartados}",
            f"draw calls {st.chamadas_desenho}   modo {self.renderizador.modo}",
            f"luzes {st.luzes}   triângulos de sombra {st.sombras}",
            f"física: corpos {len(fis.corpos)}  colisores {len(fis.colisores)}  pares {fis.pares_testados}",
        ]
        srv = cena.servicos.get("agentes")
        sis = getattr(srv, "sis", None)
        if sis is not None:
            ev = sis.stats.get("eventos", 0)
            ant_t, ant_ev = self._eventos_ant
            if agora - ant_t >= 0.5:
                self._eventos_por_s = (ev - ant_ev) / (agora - ant_t)
                self._eventos_ant = (agora, ev)
            linhas.append(f"AgentDSL: agentes {len(sis.todos())}   eventos/s {self._eventos_por_s:6.0f}")
        w = 360
        h = 10 + 17 * len(linhas)
        ui.retangulo((8, ui.altura - h - 8, w, h), (0, 0, 0, 175), raio=6)
        for i, l in enumerate(linhas):
            ui.texto(16, ui.altura - h - 3 + 17 * i, l, 13, cor=(150, 255, 170) if i == 0 else (225, 230, 240),
                     sombra=False)

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
        self.ui.desenhar_tardias()
        self.ui.desenhar_sobreposicoes()
        self.ui.desenhar_dicas()
        if self.tecla_estatisticas and self.entrada.tecla_baixou(self.tecla_estatisticas):
            self.mostrar_estatisticas = not self.mostrar_estatisticas
        if self.mostrar_estatisticas:
            self._desenhar_estatisticas(self.ui, dt)
        self.ui.enviar()
        t2 = time.perf_counter()
        self._comecar_desenho()
        self.renderizador.limpar()
        dx, dy = self._deslocamento_tremor(dt)              # tremor de câmera (explosões, impactos)
        self.camera.x += dx
        self.camera.y += dy
        self.renderizador.desenhar(cena.lista, self.camera, extras_tela=[self.ui.sprite],
                                   viewport=(0, 0, self.largura, self.altura), luzes=cena.iluminacao())
        self.camera.x -= dx
        self.camera.y -= dy
        if self._capturas:
            self._salvar_captura(self._capturas.pop(0))
        self._apresentar()
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
                elif self.tratar_evento_janela(ev):
                    pass
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
            self._comecar_desenho()
            self.renderizador.limpar()
            self.renderizador.desenhar(self.cena.lista, self.camera, extras_tela=[ui.sprite])
        except Exception:
            pass
        self._apresentar()

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
