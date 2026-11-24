"""Renderizador 2D: Sprite → Transformação → Vertex Shader → Rasterização → Fragment Shader.

Iluminação 2D (quando a cena tem luzes): antes dos sprites, as luzes são desenhadas num MAPA DE
LUZ (framebuffer do tamanho da tela) que começa com a cor da luz ambiente; cada luz soma sua cor
(mistura aditiva) com queda suave até o raio. Sombras: para cada luz que projeta sombra, os
"volumes de sombra" dos objetos (polígonos que vão do objeto até longe, no sentido oposto à luz)
marcam o stencil buffer, e a luz só é desenhada onde o stencil ficou zerado. Depois, o fragment
shader dos sprites multiplica a cor de cada pixel pela luz daquele pixel.

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
from .shader import (FRAGMENT, FRAGMENT_LUZ, FRAGMENT_SOLIDO, VERTEX_INDIVIDUAL, VERTEX_LOTE, VERTEX_LUZ,
                     VERTEX_SOLIDO, Shader)

# Quad unitário centrado na origem: 2 triângulos, (x, y, u, v) por vértice.
QUAD = np.array([
    -0.5, -0.5, 0.0, 0.0,
     0.5, -0.5, 1.0, 0.0,
     0.5,  0.5, 1.0, 1.0,
    -0.5, -0.5, 0.0, 0.0,
     0.5,  0.5, 1.0, 1.0,
    -0.5,  0.5, 0.0, 1.0,
], dtype=np.float32)

FLOATS_POR_INSTANCIA = 9 + 4 + 4 + 1  # matriz 3x3 + cor + região uv + iluminado


class Estatisticas:
    def __init__(self):
        self.chamadas_desenho = 0
        self.sprites_desenhados = 0
        self.ms_preparo = 0.0   # CPU: montar matrizes / buffers
        self.ms_envio = 0.0     # CPU: chamadas OpenGL
        self.descartados = 0    # sprites eliminados pelo culling
        self.luzes = 0          # luzes desenhadas no mapa de luz
        self.sombras = 0        # triângulos de sombra no stencil

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
        self.shader_luz = Shader(VERTEX_LUZ, FRAGMENT_LUZ)
        self.shader_solido = Shader(VERTEX_SOLIDO, FRAGMENT_SOLIDO)
        self._mapa_luz = None        # (fbo, textura, renderbuffer de stencil, largura, altura)
        self._luz_ativa = None       # (textura do mapa de luz, viewport) enquanto desenha o mundo

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
        deslocamentos = [(2, 3, 0), (3, 3, 3), (4, 3, 6), (5, 4, 9), (6, 4, 13), (7, 1, 17)]
        for local, tamanho, inicio in deslocamentos:
            GL.glEnableVertexAttribArray(local)
            GL.glVertexAttribPointer(local, tamanho, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                     ctypes.c_void_p(inicio * 4))
            GL.glVertexAttribDivisor(local, 1)
        GL.glBindVertexArray(0)

        # VAO das sombras: só posições (x, y) no mundo, num buffer que muda todo quadro
        self.vao_sombra = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao_sombra)
        self.vbo_sombra = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_sombra)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 8, ctypes.c_void_p(0))
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
    def desenhar(self, lista, camera, extras_tela=(), viewport=None, luzes=None) -> None:
        """Desenha a lista inteira: primeiro o mundo (com câmera), depois a interface.

        ``viewport`` = (x, y_de_baixo, largura, altura): desenha o mundo só num retângulo
        da janela (é assim que o editor mostra a Scene entre os painéis).
        ``luzes``: dados da iluminação 2D da cena (``Cena.iluminacao()``) ou None (sem luzes)."""
        self.stats.zerar()
        sprites = [s for s in lista.ordenados() if s.visivel]
        mundo = [s for s in sprites if not s.espaco_tela]
        tela = [s for s in sprites if s.espaco_tela] + list(extras_tela)
        if self.culling and mundo:
            mundo = self._recortar(mundo, camera)
        vp = tuple(int(v) for v in viewport) if viewport is not None else (0, 0, self.largura, self.altura)
        if luzes is not None:
            self._desenhar_mapa_luz(luzes, camera, vp)
            self._luz_ativa = (self._mapa_luz[1], vp)
        GL.glViewport(*vp)
        self._desenhar_lista(mundo, camera.view_proj())
        self._luz_ativa = None
        if viewport is not None:
            GL.glViewport(0, 0, self.largura, self.altura)
        if tela:
            proj_tela = matematica.ortografica(0, self.largura, 0, self.altura)
            self._desenhar_lista(tela, proj_tela)

    # --- iluminação 2D -------------------------------------------------------------------------
    def _garantir_mapa_luz(self, w, h):
        if self._mapa_luz is not None and self._mapa_luz[3:] == (w, h):
            return
        if self._mapa_luz is not None:
            fbo, tex, rbo, _, _ = self._mapa_luz
            GL.glDeleteFramebuffers(1, [fbo])
            GL.glDeleteTextures([tex])
            GL.glDeleteRenderbuffers(1, [rbo])
        tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        # RGBA16F: a luz pode passar de 1 (luzes somadas estouram o branco sem "cortar" a cor)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA16F, w, h, 0, GL.GL_RGBA, GL.GL_FLOAT, None)
        rbo = GL.glGenRenderbuffers(1)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, rbo)
        GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_DEPTH24_STENCIL8, w, h)
        fbo = GL.glGenFramebuffers(1)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, tex, 0)
        GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_DEPTH_STENCIL_ATTACHMENT, GL.GL_RENDERBUFFER, rbo)
        self._mapa_luz = (fbo, tex, rbo, w, h)

    def _desenhar_mapa_luz(self, luzes, camera, vp):
        x, y, w, h = vp
        anterior = GL.glGetIntegerv(GL.GL_FRAMEBUFFER_BINDING)
        self._garantir_mapa_luz(max(1, w), max(1, h))
        fbo = self._mapa_luz[0]
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
        GL.glViewport(0, 0, w, h)
        r, g, b = luzes["ambiente"]
        GL.glClearColor(r, g, b, 1.0)
        GL.glClearStencil(0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_STENCIL_BUFFER_BIT)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE)                     # as luzes se somam
        vproj = camera.view_proj()
        hw, hh = camera.largura / (2 * camera.zoom), camera.altura / (2 * camera.zoom)
        sombras = luzes.get("sombras", [])
        for luz in luzes["pontos"]:
            lx, ly, raio = luz["x"], luz["y"], luz["raio"]
            if abs(lx - camera.x) > hw + raio or abs(ly - camera.y) > hh + raio:
                continue                                           # luz fora da tela
            tri = _volumes_de_sombra(luz, sombras) if luz.get("sombras") and sombras else None
            if tri is not None and len(tri):
                self._marcar_sombras(tri, vproj)
            self._desenhar_luz(luz, vproj)
            if tri is not None and len(tri):
                GL.glDisable(GL.GL_STENCIL_TEST)
                GL.glClear(GL.GL_STENCIL_BUFFER_BIT)
            self.stats.luzes += 1
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, int(anterior))

    def _marcar_sombras(self, tri, vproj):
        """Pinta os volumes de sombra só no stencil (valor 1); a luz depois pula esses pixels."""
        GL.glEnable(GL.GL_STENCIL_TEST)
        GL.glColorMask(GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE)
        GL.glStencilFunc(GL.GL_ALWAYS, 1, 0xFF)
        GL.glStencilOp(GL.GL_KEEP, GL.GL_KEEP, GL.GL_REPLACE)
        sh = self.shader_solido
        sh.usar()
        sh.mat3("u_viewproj", vproj)
        GL.glBindVertexArray(self.vao_sombra)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_sombra)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, tri.nbytes, tri, GL.GL_STREAM_DRAW)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(tri))
        GL.glBindVertexArray(0)
        GL.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)
        GL.glStencilFunc(GL.GL_EQUAL, 0, 0xFF)
        GL.glStencilOp(GL.GL_KEEP, GL.GL_KEEP, GL.GL_KEEP)
        self.stats.sombras += len(tri) // 3

    def _desenhar_luz(self, luz, vproj):
        sh = self.shader_luz
        sh.usar()
        sh.mat3("u_viewproj", vproj)
        d = 2 * luz["raio"]
        sh.mat3("u_modelo", matematica.modelo(luz["x"], luz["y"], 0.0, d, d))
        i = luz["intensidade"]
        GL.glUniform3f(sh._local("u_cor"), luz["cor"][0] * i, luz["cor"][1] * i, luz["cor"][2] * i)
        sh.float("u_interno", max(0.0, min(0.99, luz.get("interno", 0.0))))
        cone = luz.get("cone")
        sh.int("u_cone", 1 if cone else 0)
        if cone:
            ang, abertura = cone
            sh.vec2("u_direcao", (math.cos(math.radians(ang)), math.sin(math.radians(ang))))
            meia = math.radians(max(1.0, min(359.0, abertura)) / 2)
            sh.vec2("u_abertura", (math.cos(meia), 0.15))
        GL.glBindVertexArray(self.vao_individual)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)

    def _uniformes_luz(self, sh):
        ativa = self._luz_ativa
        if ativa is None:
            sh.int("u_com_luz", 0)
            return
        tex, (x, y, w, h) = ativa
        sh.int("u_com_luz", 1)
        sh.int("u_luz", 1)
        GL.glUniform4f(sh._local("u_vp"), x, y, w, h)
        GL.glActiveTexture(GL.GL_TEXTURE1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glActiveTexture(GL.GL_TEXTURE0)

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
        self._uniformes_luz(sh)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindVertexArray(self.vao_individual)
        textura_atual = None
        aditivo = False
        for s in sprites:
            if s.textura is not textura_atual:
                GL.glBindTexture(GL.GL_TEXTURE_2D, s.textura.id)
                textura_atual = s.textura
            if s.aditivo != aditivo:
                aditivo = s.aditivo
                GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE if aditivo else GL.GL_ONE_MINUS_SRC_ALPHA)
            sh.mat3("u_modelo", s.matriz_final())   # calcular transformação
            sh.vec4("u_cor", s.cor)
            sh.vec4("u_regiao_uv", s.regiao_uv)
            sh.float("u_iluminado", 1.0 if s.iluminado else 0.0)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)   # renderizar sprite
            self.stats.chamadas_desenho += 1
        if aditivo:
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
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
        dados[:, 17] = np.fromiter((1.0 if s.iluminado else 0.0 for s in sprites), np.float32, n)

        # Grupos de sprites vizinhos com a mesma textura e o mesmo modo de mistura
        # (preserva a ordem das camadas).
        ids = np.fromiter((s.textura.id * 2 + (1 if s.aditivo else 0) for s in sprites), np.int64, n)
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
        self._uniformes_luz(sh)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindVertexArray(self.vao_lote)
        stride = FLOATS_POR_INSTANCIA * 4
        aditivo = False
        for ini, fim in zip(inicios, fins):
            GL.glBindTexture(GL.GL_TEXTURE_2D, sprites[ini].textura.id)
            if sprites[ini].aditivo != aditivo:          # brilho: soma a cor em vez de cobrir
                aditivo = sprites[ini].aditivo
                GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE if aditivo else GL.GL_ONE_MINUS_SRC_ALPHA)
            # Reaponta os atributos de instância para o início do grupo.
            base = int(ini) * stride
            for local, inicio, tamanho in ((2, 0, 3), (3, 3, 3), (4, 6, 3), (5, 9, 4), (6, 13, 4), (7, 17, 1)):
                GL.glVertexAttribPointer(local, tamanho, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                         ctypes.c_void_p(base + inicio * 4))
            GL.glDrawArraysInstanced(GL.GL_TRIANGLES, 0, 6, int(fim - ini))
            self.stats.chamadas_desenho += 1
        if aditivo:
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glBindVertexArray(0)
        self.stats.sprites_desenhados += n
        t2 = time.perf_counter()
        self.stats.ms_preparo += (t1 - t0) * 1000
        self.stats.ms_envio += (t2 - t1) * 1000


def _volumes_de_sombra(luz, sombras) -> np.ndarray | None:
    """Triângulos (x, y) dos volumes de sombra de todos os objetos perto da luz.

    Círculo: as duas tangentes que saem da luz e tocam o círculo; a sombra é o quadrilátero que
    vai desses pontos até longe. Caixa: cada aresta virada para longe da luz é "esticada" para
    longe dela. (Sombra 2D por volumes, a mesma ideia das sombras com stencil em 3D.)"""
    lx, ly, raio = luz["x"], luz["y"], luz["raio"]
    longe = raio * 3.0
    tri = []
    for s in sombras:
        cx, cy = s["x"], s["y"]
        dx, dy = cx - lx, cy - ly
        d = math.hypot(dx, dy)
        tam = s.get("raio") or math.hypot(s.get("hw", 0), s.get("hh", 0))
        if d > raio + tam or d < 1e-6:
            continue
        if s["forma"] == "circulo":
            r = s["raio"]
            if d <= r:
                continue                       # a luz está dentro do objeto
            base = math.atan2(dy, dx)
            alfa = math.asin(r / d)
            t = math.sqrt(d * d - r * r)
            pts = []
            for sinal in (1, -1):
                a = base + sinal * alfa
                px, py = lx + math.cos(a) * t, ly + math.sin(a) * t
                pts.append((px, py, px + math.cos(a) * longe, py + math.sin(a) * longe))
            (ax, ay, afx, afy), (bx, by, bfx, bfy) = pts
            tri += [(ax, ay), (bx, by), (bfx, bfy), (ax, ay), (bfx, bfy), (afx, afy)]
        else:
            hw, hh = s["hw"], s["hh"]
            cantos = [(cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)]
            if cx - hw <= lx <= cx + hw and cy - hh <= ly <= cy + hh:
                continue
            for i in range(4):
                (ax, ay), (bx, by) = cantos[i], cantos[(i + 1) % 4]
                nx, ny = by - ay, -(bx - ax)                       # normal para fora (sentido anti-horário)
                mx, my = (ax + bx) / 2 - lx, (ay + by) / 2 - ly
                if nx * mx + ny * my <= 0:
                    continue                                       # aresta virada para a luz
                fa = _esticar(ax, ay, lx, ly, longe)
                fb = _esticar(bx, by, lx, ly, longe)
                tri += [(ax, ay), (bx, by), fb, (ax, ay), fb, fa]
    if not tri:
        return None
    return np.array(tri, dtype=np.float32)


def _esticar(x, y, lx, ly, longe):
    dx, dy = x - lx, y - ly
    d = math.hypot(dx, dy) or 1.0
    return x + dx / d * longe, y + dy / d * longe
