"""Painel Scene: visão da cena com grade, seleção e ferramentas Mover / Girar / Escalar."""
from __future__ import annotations

import math

import pygame

from engine2d import matematica as M
from engine2d.camera import Camera2D

from .widgets import COR, botao, recortar

GRADE = 64


class SceneMixin:
    def _init_scene(self):
        self.cam = Camera2D(800, 600)
        self.ferramenta = "mover"
        self._gizmo = None       # arrasto em andamento: (modo, eixo, dados iniciais)
        self._pan = None
        self.ver_luzes = True    # a Scene mostra a iluminação 2D (botão "Luzes" no alto da Scene)

    # --- conversões tela ↔ mundo (a Scene ocupa só um retângulo da janela) ---------------
    def tela_para_mundo(self, mx, my):
        sv = self.r_scene
        return self.cam.tela_para_mundo(mx - sv.x, my - sv.y)

    def mundo_para_tela(self, x, y):
        sv = self.r_scene
        px, py = M.aplicar(self.cam.view(), x, y)
        return sv.x + sv.w / 2 + px, sv.y + sv.h / 2 - py

    def _enquadrar_camera_inicial(self):
        cam_go = next((g for g in self.cena.objetos if g.obter("CameraPrincipal")), None)
        if cam_go is not None:
            self.cam.x, self.cam.y = cam_go.transform.posicao_mundo
        elif self.projeto:
            self.cam.x, self.cam.y = self.projeto.largura / 2, self.projeto.altura / 2
        self.cam.zoom = 0.75
        sv = getattr(self, "r_scene", None)
        if self.projeto and sv is not None:       # a moldura da câmera do jogo inteira, com folga
            self.cam.zoom = round(min(sv.w / self.projeto.largura, (sv.h - 22) / self.projeto.altura) * 0.9, 3)

    def focar(self, go=None):
        go = go or self.selecionado
        if go is not None:
            self.cam.x, self.cam.y = go.transform.posicao_mundo

    # --- desenho e interação ------------------------------------------------------------
    def _desenhar_scene(self, ui):
        sv = self.r_scene
        ent = self.motor.entrada
        livre = self.livre("scene")
        with recortar(ui, sv):
            self._grade(ui)
            self._moldura_camera(ui)
            colisores, vazios = self._gizmos_da_cena()
            for c in colisores:
                if not c.gameobject.destruido:
                    self._desenhar_colisor(ui, c, (110, 200, 120) if not c.gatilho else (100, 170, 250))
            for go in vazios:
                if not go.destruido:
                    x, y = self.mundo_para_tela(*go.transform.posicao_mundo)
                    pygame.draw.circle(ui.surface, (150, 150, 150), (int(x), int(y)), 4, 1)
            self._gizmos_luzes(ui)
            if self.selecionado is not None and not self.selecionado.destruido:
                if self.pincel is not None and self.mapa_selecionado() is not None:
                    self.desenhar_pincel(ui)              # pintando o mapa: sem gizmo, com prévia do bloco
                else:
                    self._contorno(ui, self.selecionado)
                    self._gizmos(ui, self.selecionado)
                    if self.mapa_selecionado() is not None:
                        self.desenhar_pincel(ui)
        # moldura e rótulo do painel
        pygame.draw.rect(ui.surface, COR["borda"], sv, 1)
        pygame.draw.rect(ui.surface, COR["cabecalho"], (sv.x, sv.y, sv.w, 22))
        ra = pygame.Rect(sv.x + 2, sv.y + 2, 60, 20)
        pygame.draw.rect(ui.surface, COR["fundo"], ra, border_top_left_radius=3, border_top_right_radius=3)
        ui.texto(ra.centerx, ra.centery, "Scene", 13, ancora="center", negrito=True, sombra=False)
        ui.texto(sv.right - 8, sv.y + 11, f"zoom {self.cam.zoom:.2f}  ·  ({self.cam.x:.0f}, {self.cam.y:.0f})"
                 "  ·  botão do meio/direito arrasta, roda = zoom", 12, ancora="midright", sombra=False,
                 cor=COR["texto2"])
        if self.cena.luzes:                          # só aparece quando a cena tem luzes
            rb = pygame.Rect(sv.x + 70, sv.y + 2, 110, 18)
            if botao(ui, rb, "Luzes: ligadas" if self.ver_luzes else "Luzes: desligadas", livre, tamanho=12,
                     destacado=self.ver_luzes):
                self.ver_luzes = not self.ver_luzes
        if self.arrasto is not None and self.arrasto.ativo and sv.collidepoint(ent.mouse_tela):
            pygame.draw.rect(ui.surface, COR["destaque"], sv, 2)
        if not livre and self._gizmo is None and self._pan is None and self._pintura is None:
            return
        self._interagir(ent)

    def _interagir(self, ent):
        mx, my = ent.mouse_tela
        cam = self.cam
        # pan com o botão do meio ou direito
        if (ent.clicou(2) or ent.clicou(3)) and self.livre("scene"):
            self._pan = (mx, my, cam.x, cam.y, 2 if ent.clicou(2) else 3)
        if self._pan:
            x0, y0, cx, cy, b = self._pan
            if ent.mouse_pressionado(b):
                cam.x = cx - (mx - x0) / cam.zoom
                cam.y = cy + (my - y0) / cam.zoom
            else:
                if b == 3 and abs(mx - x0) + abs(my - y0) < 4:   # clique direito parado: menu de criar
                    wx, wy = self.tela_para_mundo(mx, my)
                    self.abrir_popup(mx, my, [(r, (lambda t=t: self.criar_objeto(t, x=wx, y=wy)), "")
                                              for r, t in (("Criar vazio aqui", "vazio"), ("Sprite aqui", "sprite"),
                                                           ("Sprite com física aqui", "fisica"))], largura=200)
                self._pan = None
        if ent.roda and self.livre("scene"):      # zoom em direção ao cursor
            antes = self.tela_para_mundo(mx, my)
            cam.zoom = max(0.05, min(10.0, cam.zoom * (1.15 ** ent.roda)))
            depois = self.tela_para_mundo(mx, my)
            cam.x += antes[0] - depois[0]
            cam.y += antes[1] - depois[1]
        # mapa de tiles com pincel: o clique pinta (Shift apaga, Ctrl pega o bloco)
        if self.pintar_mapa(ent, mx, my):
            return
        # clique esquerdo: alça do gizmo, ou selecionar
        if ent.clicou(1) and self.livre("scene"):
            alca = self._alca_sob_mouse(mx, my) if self.selecionado is not None else None
            if alca is None:
                go = self._escolher(*self.tela_para_mundo(mx, my))
                self.selecionado = go
                self.asset_selecionado = None
                if go is not None:
                    self.revelar(go)
                    alca = "livre"
                    mapa = go.obter("MapaTiles")
                    if mapa is not None:              # clicou num bloco do mapa: já escolhe esse bloco
                        letra = mapa.letra_na_celula(*mapa.celula_em(*self.tela_para_mundo(mx, my)))
                        if letra != mapa.VAZIO:
                            self.escolher_pincel(letra)
                            return
            if alca is not None and self.selecionado is not None:
                t = self.selecionado.transform
                self._gizmo = {"alca": alca, "mouse": (mx, my), "mundo": t.mundo(), "local": (t.x, t.y),
                               "esc": (t.escala_x, t.escala_y), "marcado": False}
        if self._gizmo is not None:
            if ent.mouse_pressionado(1):
                self._arrastar_gizmo(mx, my, ent)
            else:
                self._gizmo = None

    def _gizmos_da_cena(self):
        """Colisores e objetos sem sprite (para desenhar os gizmos). Recalculado 4x por segundo
        ou quando a quantidade de objetos/componentes muda."""
        import time
        assinatura = (id(self.cena), len(self.cena.objetos), sum(len(g.componentes) for g in self.cena.objetos[:50]))
        cache = getattr(self, "_cache_gizmos", None)
        if cache and cache[0] == assinatura and time.time() - cache[1] < 0.25:
            return cache[2], cache[3]
        colisores, vazios = [], []
        for go in self.cena.objetos:
            tem_visual = False
            for c in go.componentes:
                nome = type(c).__name__
                if nome == "Colisor":
                    colisores.append(c)
                elif nome in ("SpriteRenderer", "CameraPrincipal"):
                    tem_visual = True
            if not tem_visual:
                vazios.append(go)
        self._cache_gizmos = (assinatura, time.time(), colisores, vazios)
        return colisores, vazios

    def _gizmos_luzes(self, ui):
        """Luz 2D na Scene: sol amarelo no centro, círculo do raio e, no cone, as bordas."""
        for luz in self.cena.luzes:
            go = luz.gameobject
            if go is None or go.destruido or luz.tipo == "global":
                continue
            d = luz.dados()
            x, y = self.mundo_para_tela(d["x"], d["y"])
            r = d["raio"] * self.cam.zoom
            cor = tuple(int(255 * max(0.3, min(1.0, c))) for c in d["cor"])
            sel = go is self.selecionado
            if sel or r < 400:
                pygame.draw.circle(ui.surface, cor, (int(x), int(y)), max(2, int(r)), 2 if sel else 1)
            if "cone" in d:
                ang, ab = d["cone"]
                for a in (ang - ab / 2, ang + ab / 2):
                    pygame.draw.line(ui.surface, cor, (x, y), (x + r * math.cos(math.radians(a)),
                                                               y - r * math.sin(math.radians(a))), 1)
            pygame.draw.circle(ui.surface, (255, 220, 80), (int(x), int(y)), 6)
            for k in range(8):
                a = math.radians(k * 45)
                pygame.draw.line(ui.surface, (255, 220, 80), (x + 8 * math.cos(a), y + 8 * math.sin(a)),
                                 (x + 12 * math.cos(a), y + 12 * math.sin(a)), 1)

    def _escolher(self, wx, wy):
        for sp in reversed(self.cena.lista.ordenados()):
            go = sp.dados.get("gameobject")
            if go is not None and sp.visivel and not go.destruido and sp.contem_ponto(wx, wy):
                return go
        melhor, dmin = None, (10 / self.cam.zoom) ** 2       # objetos sem sprite: perto do ponto
        for go in self.cena.objetos:
            x, y = go.transform.posicao_mundo
            d = (x - wx) ** 2 + (y - wy) ** 2
            if d < dmin:
                melhor, dmin = go, d
        return melhor

    # --- gizmos -----------------------------------------------------------------------------
    def _pontos_gizmo(self, go):
        x, y = self.mundo_para_tela(*go.transform.posicao_mundo)
        return x, y, 70

    def _alca_sob_mouse(self, mx, my):
        x, y, L = self._pontos_gizmo(self.selecionado)
        if self.ferramenta == "girar":
            d = math.hypot(mx - x, my - y)
            return "giro" if abs(d - L) < 9 else None
        if abs(mx - x) < 9 and abs(my - y) < 9:
            return "livre"
        if abs(my - y) < 8 and x + 10 < mx < x + L + 12:
            return "x"
        if abs(mx - x) < 8 and y - L - 12 < my < y - 10:
            return "y"
        return None

    def _arrastar_gizmo(self, mx, my, ent):
        g = self._gizmo
        go = self.selecionado
        if go is None:
            return
        dx_t, dy_t = mx - g["mouse"][0], my - g["mouse"][1]
        if not g["marcado"] and abs(dx_t) + abs(dy_t) > 1:
            self.marcar()                    # uma entrada no Ctrl+Z por arrasto
            g["marcado"] = True
        if not g["marcado"]:
            return
        t = go.transform
        x0, y0, r0, sx0, sy0 = g["mundo"]
        z = self.cam.zoom
        ctrl = ent.tecla("left ctrl") or ent.tecla("right ctrl")
        if self.ferramenta == "girar" or g["alca"] == "giro":
            cx, cy = self.mundo_para_tela(x0, y0)
            a0 = math.degrees(math.atan2(-(g["mouse"][1] - cy), g["mouse"][0] - cx))
            a1 = math.degrees(math.atan2(-(my - cy), mx - cx))
            ang = r0 + (a1 - a0)
            if ctrl:
                ang = round(ang / 15) * 15
            t.definir_mundo(x0, y0, rotacao=ang)
        elif self.ferramenta == "escalar":
            f = max(0.05, 1 + (dx_t - dy_t) / 150)
            fx = f if g["alca"] in ("x", "livre") else 1
            fy = f if g["alca"] in ("y", "livre") else 1
            ex0, ey0 = g["esc"]
            t.escala_x = round(ex0 * fx, 3)
            t.escala_y = round(ey0 * fy, 3)
        else:
            nx = x0 + (dx_t / z if g["alca"] in ("x", "livre") else 0)
            ny = y0 - (dy_t / z if g["alca"] in ("y", "livre") else 0)
            if ctrl:
                nx, ny = round(nx / 32) * 32, round(ny / 32) * 32
            t.posicao_mundo = (nx, ny)

    def _gizmos(self, ui, go):
        x, y, L = self._pontos_gizmo(go)
        if self.ferramenta == "girar":
            pygame.draw.circle(ui.surface, (80, 140, 230), (int(x), int(y)), L, 2)
            _, _, r, _, _ = go.transform.mundo()
            a = math.radians(r)
            pygame.draw.line(ui.surface, COR["amarelo"], (x, y), (x + L * math.cos(a), y - L * math.sin(a)), 2)
            return
        ponta = "■" if self.ferramenta == "escalar" else "►"
        pygame.draw.line(ui.surface, COR["eixo_x"], (x, y), (x + L, y), 3)
        pygame.draw.line(ui.surface, COR["eixo_y"], (x, y), (x, y - L), 3)
        if ponta == "►":
            pygame.draw.polygon(ui.surface, COR["eixo_x"], [(x + L + 12, y), (x + L, y - 6), (x + L, y + 6)])
            pygame.draw.polygon(ui.surface, COR["eixo_y"], [(x, y - L - 12), (x - 6, y - L), (x + 6, y - L)])
        else:
            pygame.draw.rect(ui.surface, COR["eixo_x"], (x + L - 4, y - 5, 10, 10))
            pygame.draw.rect(ui.surface, COR["eixo_y"], (x - 5, y - L - 4, 10, 10))
        pygame.draw.rect(ui.surface, (230, 230, 230), (x - 7, y - 7, 14, 14), 2)

    def _contorno(self, ui, go):
        for rend in go.obter_nos_filhos("SpriteRenderer"):
            sp = getattr(rend, "sprite", None)
            if sp is None:
                continue
            mat = sp.matriz_final()
            cantos = [self.mundo_para_tela(*M.aplicar(mat, px, py)) for px, py in
                      ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5))]
            pygame.draw.lines(ui.surface, (255, 160, 40) if rend.gameobject is go else (200, 140, 60), True, cantos, 2)

    def _desenhar_colisor(self, ui, c, cor):
        cx, cy = self.mundo_para_tela(*c.centro())
        e = c.escala() * self.cam.zoom
        if c.forma == "circulo":
            pygame.draw.circle(ui.surface, cor, (int(cx), int(cy)), max(1, int(c.raio * e)), 1)
        else:
            w, h = c.largura * e, c.altura * e
            pygame.draw.rect(ui.surface, cor, (cx - w / 2, cy - h / 2, w, h), 1)

    def _moldura_camera(self, ui):
        cam_go = next((g for g in self.cena.objetos if g.obter("CameraPrincipal")), None)
        if cam_go is None or self.projeto is None:
            return
        zoom = cam_go.obter("CameraPrincipal").zoom or 1
        x, y = cam_go.transform.posicao_mundo
        hw, hh = self.projeto.largura / (2 * zoom), self.projeto.altura / (2 * zoom)
        a = self.mundo_para_tela(x - hw, y + hh)
        b = self.mundo_para_tela(x + hw, y - hh)
        pygame.draw.rect(ui.surface, (230, 230, 230), (a[0], a[1], b[0] - a[0], b[1] - a[1]), 1)
        ui.texto(a[0] + 4, a[1] + 3, "Câmera (o que aparece no Play)", 11, sombra=False, cor=(200, 200, 200))

    def _grade(self, ui):
        sv = self.r_scene
        z = self.cam.zoom
        passo = GRADE
        while passo * z < 24:
            passo *= 2
        x0, y1 = self.tela_para_mundo(sv.x, sv.y)
        x1, y0 = self.tela_para_mundo(sv.right, sv.bottom)
        camada = pygame.Surface(sv.size, pygame.SRCALPHA)
        gx = math.floor(x0 / passo) * passo
        while gx <= x1:
            px, _ = self.mundo_para_tela(gx, 0)
            cor = (255, 255, 255, 60) if abs(gx) < 1e-6 else (255, 255, 255, 18)
            pygame.draw.line(camada, cor, (px - sv.x, 0), (px - sv.x, sv.h))
            gx += passo
        gy = math.floor(y0 / passo) * passo
        while gy <= y1:
            _, py = self.mundo_para_tela(0, gy)
            cor = (255, 255, 255, 60) if abs(gy) < 1e-6 else (255, 255, 255, 18)
            pygame.draw.line(camada, cor, (0, py - sv.y), (sv.w, py - sv.y))
            gy += passo
        ui.surface.blit(camada, sv.topleft)
