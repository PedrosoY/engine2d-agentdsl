"""Renderizador 2D: Sprite → Transformação → Vertex Shader → Rasterização → Fragment Shader.

Dois modos, para comparação experimental:

* ``individual``: o pipeline descrito no artigo — uma chamada glDrawArrays por
  sprite, com a matriz de modelo enviada como uniform.
* ``lote``: os sprites (já ordenados por camada) são agrupados em sequências
  consecutivas com a mesma textura; cada grupo vira UMA chamada instanciada
  (glDrawArraysInstanced), com as matrizes calculadas de forma vetorizada no
  numpy. A ordem das camadas é preservada porque só agrupamos sprites vizinhos.
"""
from __future__ import annotations

import ctypes
import math
import time

import numpy as np
from OpenGL import GL

from . import matematica
from .shader import FRAGMENT, VERTEX_INDIVIDUAL, VERTEX_LOTE, Shader

# Quad unitário centrado na origem: 2 triângulos, (x, y, u, v) por vértice.
QUAD = np.array([
    -0.5, -0.5, 0.0, 0.0,
     0.5, -0.5, 1.0, 0.0,
     0.5,  0.5, 1.0, 1.0,
    -0.5, -0.5, 0.0, 0.0,
     0.5,  0.5, 1.0, 1.0,
    -0.5,  0.5, 0.0, 1.0,
], dtype=np.float32)

FLOATS_POR_INSTANCIA = 9 + 4 + 4  # matriz 3x3 + cor + região uv


class Estatisticas:
    def __init__(self):
        self.chamadas_desenho = 0
        self.sprites_desenhados = 0
        self.ms_preparo = 0.0   # CPU: montar matrizes / buffers
        self.ms_envio = 0.0     # CPU: chamadas OpenGL
        self.descartados = 0    # sprites eliminados pelo culling

    def zerar(self):
        self.__init__()


class Renderizador:
    MODOS = ("individual", "lote")

    def __init__(self, largura: int, altura: int, modo: str = "lote"):
        self.largura, self.altura = largura, altura
        self.modo = modo
        self.culling = True   # descarta sprites fora da área visível da câmera
        self.cor_fundo = (0.08, 0.09, 0.12, 1.0)
        self.stats = Estatisticas()

        self.shader_individual = Shader(VERTEX_INDIVIDUAL, FRAGMENT)
        self.shader_lote = Shader(VERTEX_LOTE, FRAGMENT)

        # VBO do quad, compartilhado por todos os sprites (geometria reutilizada).
        self.vbo_quad = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_quad)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, QUAD.nbytes, QUAD, GL.GL_STATIC_DRAW)

        # VAO do modo individual
        self.vao_individual = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao_individual)
        self._atributos_quad()

        # VAO do modo lote (+ buffer de instâncias, crescido sob demanda)
        self.vao_lote = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao_lote)
        self._atributos_quad()
        self.vbo_instancias = GL.glGenBuffers(1)
        self._capacidade_instancias = 0
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_instancias)
        stride = FLOATS_POR_INSTANCIA * 4
        deslocamentos = [(2, 3, 0), (3, 3, 3), (4, 3, 6), (5, 4, 9), (6, 4, 13)]
        for local, tamanho, inicio in deslocamentos:
            GL.glEnableVertexAttribArray(local)
            GL.glVertexAttribPointer(local, tamanho, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                     ctypes.c_void_p(inicio * 4))
            GL.glVertexAttribDivisor(local, 1)
        GL.glBindVertexArray(0)

        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)  # alpha blending
        GL.glDisable(GL.GL_DEPTH_TEST)  # a ordem vem das camadas, não do z-buffer

    @staticmethod
    def _atributos_quad():
        stride = 4 * 4
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(8))

    @property
    def bytes_vram_buffers(self) -> int:
        return QUAD.nbytes + self._capacidade_instancias * FLOATS_POR_INSTANCIA * 4

    def redimensionar(self, largura: int, altura: int) -> None:
        self.largura, self.altura = largura, altura
        GL.glViewport(0, 0, largura, altura)

    def limpar(self) -> None:
        GL.glClearColor(*self.cor_fundo)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

    # ------------------------------------------------------------------
    def desenhar(self, lista, camera, extras_tela=()) -> None:
        """Desenha a lista inteira: primeiro o mundo (com câmera), depois a interface."""
        self.stats.zerar()
        sprites = [s for s in lista.ordenados() if s.visivel]
        mundo = [s for s in sprites if not s.espaco_tela]
        tela = [s for s in sprites if s.espaco_tela] + list(extras_tela)
        if self.culling and mundo:
            mundo = self._recortar(mundo, camera)
        self._desenhar_lista(mundo, camera.view_proj())
        if tela:
            proj_tela = matematica.ortografica(0, self.largura, 0, self.altura)
            self._desenhar_lista(tela, proj_tela)

    def _recortar(self, sprites, camera):
        """View frustum culling 2D (Assarsson): em 2D o "frustum" é o retângulo visível.

        Cada sprite é aproximado por um círculo envolvente (raio = meia diagonal
        escalada); se o círculo não toca o retângulo da câmera, ele é descartado
        antes de chegar à GPU. O teste é vetorizado no numpy.
        """
        n = len(sprites)
        tr = [s.transformacao for s in sprites]
        x = np.fromiter((t.x for t in tr), np.float32, n)
        y = np.fromiter((t.y for t in tr), np.float32, n)
        r = np.fromiter((0.5 * math.hypot(s.largura * t.sx, s.altura * t.sy) for s, t in zip(sprites, tr)),
                        np.float32, n)
        # meia largura/altura da área visível; com rotação da câmera usa o círculo que a envolve
        hw = camera.largura / (2 * camera.zoom)
        hh = camera.altura / (2 * camera.zoom)
        if camera.rotacao % 360:
            hw = hh = math.hypot(hw, hh)
        visivel = (np.abs(x - camera.x) <= hw + r) & (np.abs(y - camera.y) <= hh + r)
        self.stats.descartados = int(n - visivel.sum())
        if visivel.all():
            return sprites
        return [s for s, v in zip(sprites, visivel) if v]

    def _desenhar_lista(self, sprites, view_proj) -> None:
        if not sprites:
            return
        if self.modo == "individual":
            self._individual(sprites, view_proj)
        else:
            self._lote(sprites, view_proj)

    # --- modo individual: uma draw call por sprite -------------------------
    def _individual(self, sprites, view_proj) -> None:
        t0 = time.perf_counter()
        sh = self.shader_individual
        sh.usar()
        sh.mat3("u_viewproj", view_proj)
        sh.int("u_textura", 0)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindVertexArray(self.vao_individual)
        textura_atual = None
        for s in sprites:
            if s.textura is not textura_atual:
                GL.glBindTexture(GL.GL_TEXTURE_2D, s.textura.id)
                textura_atual = s.textura
            sh.mat3("u_modelo", s.matriz_final())   # calcular transformação
            sh.vec4("u_cor", s.cor)
            sh.vec4("u_regiao_uv", s.regiao_uv)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)   # renderizar sprite
            self.stats.chamadas_desenho += 1
        GL.glBindVertexArray(0)
        self.stats.sprites_desenhados += len(sprites)
        self.stats.ms_envio += (time.perf_counter() - t0) * 1000

    # --- modo lote: instancing agrupando texturas consecutivas -------------
    def _lote(self, sprites, view_proj) -> None:
        t0 = time.perf_counter()
        n = len(sprites)
        # Coleta dos atributos (struct-of-arrays) e cálculo vetorizado de M·Tamanho.
        tr = [s.transformacao for s in sprites]
        tx = np.fromiter((t.x for t in tr), np.float32, n)
        ty = np.fromiter((t.y for t in tr), np.float32, n)
        rot = np.fromiter((t.rotacao for t in tr), np.float32, n)
        sx = np.fromiter((t.sx * s.largura for t, s in zip(tr, sprites)), np.float32, n)
        sy = np.fromiter((t.sy * s.altura for t, s in zip(tr, sprites)), np.float32, n)
        m = matematica.modelo_vetorizado(tx, ty, rot, sx, sy)

        dados = np.empty((n, FLOATS_POR_INSTANCIA), dtype=np.float32)
        # GLSL mat3(col0, col1, col2): enviamos as colunas => transposta da linha-maior.
        dados[:, 0:9] = m.transpose(0, 2, 1).reshape(n, 9)
        dados[:, 9:13] = np.array([s.cor for s in sprites], dtype=np.float32)
        dados[:, 13:17] = np.array([s.regiao_uv for s in sprites], dtype=np.float32)

        # Grupos de sprites vizinhos com a mesma textura (preserva a ordem das camadas).
        ids = np.fromiter((s.textura.id for s in sprites), np.int64, n)
        quebras = np.flatnonzero(ids[1:] != ids[:-1]) + 1
        inicios = np.concatenate(([0], quebras))
        fins = np.concatenate((quebras, [n]))
        t1 = time.perf_counter()

        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_instancias)
        if n > self._capacidade_instancias:
            self._capacidade_instancias = max(n, int(self._capacidade_instancias * 1.5), 1024)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, self._capacidade_instancias * FLOATS_POR_INSTANCIA * 4,
                            None, GL.GL_DYNAMIC_DRAW)
        GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, dados.nbytes, dados)

        sh = self.shader_lote
        sh.usar()
        sh.mat3("u_viewproj", view_proj)
        sh.int("u_textura", 0)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindVertexArray(self.vao_lote)
        stride = FLOATS_POR_INSTANCIA * 4
        for ini, fim in zip(inicios, fins):
            GL.glBindTexture(GL.GL_TEXTURE_2D, sprites[ini].textura.id)
            # Reaponta os atributos de instância para o início do grupo.
            base = int(ini) * stride
            for local, inicio in ((2, 0), (3, 3), (4, 6), (5, 9), (6, 13)):
                tamanho = 3 if local <= 4 else 4
                GL.glVertexAttribPointer(local, tamanho, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                         ctypes.c_void_p(base + inicio * 4))
            GL.glDrawArraysInstanced(GL.GL_TRIANGLES, 0, 6, int(fim - ini))
            self.stats.chamadas_desenho += 1
        GL.glBindVertexArray(0)
        self.stats.sprites_desenhados += n
        t2 = time.perf_counter()
        self.stats.ms_preparo += (t1 - t0) * 1000
        self.stats.ms_envio += (t2 - t1) * 1000
