"""Editor dentro do jogo (F1).

  ┌ barra: ▶/❚❚  Passo  Salvar  Carregar  Novo  Duplicar  Excluir   FPS…  ┐
  │ Hierarquia │            Cena (seleção, arrasto, gizmos)    │ Inspector │
  └────────────┴───────────────────────────────────────────────┴───────────┘

Atalhos com o editor aberto:
  F5 play/pause · F6 avança um quadro · G mostra/esconde colisores · F foca a seleção
  clique esquerdo seleciona/arrasta · botão direito arrasta a câmera · roda = zoom
  Delete exclui · Ctrl+D duplica · Ctrl+S salva a cena (JSON) · Ctrl+L carrega
  No inspector: clique num valor para digitar (Enter confirma, Esc cancela);
  roda do mouse sobre um número soma/subtrai (Shift ×10, Ctrl ×0,1).
"""
from __future__ import annotations

import math
from pathlib import Path

import pygame

from .cena import objeto_de_dict, objeto_para_dict
from .ui import CORES

LARG_HIER = 250
LARG_INSP = 330
ALT_BARRA = 34
ALT_LINHA = 20


class Editor:
    def __init__(self, motor):
        self.motor = motor
        self.ativo = False
        self.rodando = False
        self.passo_unico = False
        self.selecionado = None
        self.mostrar_colisores = True
        self.rolagem_hier = 0
        self.rolagem_insp = 0
        self.arquivo = Path("cena_salva.json")
        self._arrasto = None          # (dx, dy) do mouse até o objeto
        self._pan = None
        self._edicao = None           # (alvo, campo, tipo, texto)
        self._linhas_insp: list = []  # (rect, alvo, campo, tipo)
        self.mensagem = ("", 0.0)
        self._expandidos: set[int] = set()   # nós abertos na hierarquia (fechados por padrão)

    # ------------------------------------------------------------------
    def alternar(self) -> None:
        self.ativo = not self.ativo
        self.rodando = not self.ativo   # abrir o editor pausa a simulação
        self._edicao = None

    def _avisar(self, texto: str) -> None:
        self.mensagem = (texto, 2.5)

    def processar_entrada(self) -> None:
        ent = self.motor.entrada
        if ent.tecla_baixou("f1"):
            self.alternar()
        if not self.ativo:
            return
        cena = self.motor.cena
        ctrl = ent.tecla("left ctrl") or ent.tecla("right ctrl")

        if self._edicao is not None:
            self._processar_digitacao()
            return
        if ent.tecla_baixou("f5"):
            self.rodando = not self.rodando
        if ent.tecla_baixou("f6"):
            self.rodando, self.passo_unico = False, True
        if ent.tecla_baixou("f") and self.selecionado:      # F foca o objeto selecionado
            cam = self.motor.camera
            cam.x, cam.y = self.selecionado.transform.posicao_mundo
        if ent.tecla_baixou("g"):
            self.mostrar_colisores = not self.mostrar_colisores
        if ent.tecla_baixou("escape"):
            self.selecionado = None
        if ent.tecla_baixou("delete") and self.selecionado:
            self.excluir()
        if ctrl and ent.tecla_baixou("d") and self.selecionado:
            self.duplicar()
        if ctrl and ent.tecla_baixou("s"):
            self.salvar()
        if ctrl and ent.tecla_baixou("l"):
            self.carregar()

        mx, my = ent.mouse_tela
        sobre_paineis = mx < LARG_HIER or mx > self.motor.largura - LARG_INSP or my < ALT_BARRA
        cam = self.motor.camera
        # câmera: botão direito arrasta, roda dá zoom (fora dos painéis)
        if ent.clicou(3) and not sobre_paineis:
            self._pan = (mx, my, cam.x, cam.y)
        if self._pan and ent.mouse_pressionado(3):
            x0, y0, cx, cy = self._pan
            cam.x = cx - (mx - x0) / cam.zoom
            cam.y = cy + (my - y0) / cam.zoom
        elif self._pan:
            self._pan = None
        if ent.roda and not sobre_paineis:
            cam.zoom = max(0.1, min(8.0, cam.zoom * (1.12 ** ent.roda)))
        elif ent.roda and mx < LARG_HIER:
            self.rolagem_hier = max(0, self.rolagem_hier - ent.roda * 3)
        elif ent.roda and mx > self.motor.largura - LARG_INSP:
            if not self._roda_em_campo(ent.roda):
                self.rolagem_insp = max(0, self.rolagem_insp - ent.roda * 3)

        # seleção e arrasto na cena
        if ent.clicou(1) and not sobre_paineis and not self.motor.ui.mouse_sobre_ui():
            wx, wy = ent.mouse_mundo
            go = self._escolher(wx, wy)
            self.selecionado = go
            p = go.pai if go else None
            while p is not None:
                self._expandidos.add(p.id)
                p = p.pai
            if go is not None:
                gx, gy = go.transform.posicao_mundo
                self._arrasto = (gx - wx, gy - wy)
            ent.consumir_clique()
        if self._arrasto and self.selecionado and ent.mouse_pressionado(1):
            wx, wy = ent.mouse_mundo
            self.selecionado.transform.posicao_mundo = (wx + self._arrasto[0], wy + self._arrasto[1])
        elif self._arrasto:
            self._arrasto = None
        if self.selecionado is not None and (self.selecionado.destruido or self.selecionado.cena is not cena):
            self.selecionado = None
        if self.selecionado is not None:   # objetos estáticos selecionados voltam a sincronizar
            for r in self.selecionado.obter_nos_filhos("SpriteRenderer"):
                r._sincronizado = False

    def _escolher(self, wx, wy):
        for sp in reversed(self.motor.cena.lista.ordenados()):
            go = sp.dados.get("gameobject")
            if go is not None and sp.visivel and not go.destruido and sp.contem_ponto(wx, wy):
                return go
        # objetos sem sprite: pelo colisor
        for c in self.motor.cena.fisica.consultar_circulo(wx, wy, 4):
            return c.gameobject
        return None

    # --- ações -------------------------------------------------------------------
    def excluir(self):
        self.selecionado.destruir()
        self._avisar(f"excluído: {self.selecionado.nome}")
        self.selecionado = None

    def duplicar(self):
        go = objeto_de_dict(objeto_para_dict(self.selecionado))
        go.nome += " (cópia)"
        go.transform.x += 24
        go.transform.y -= 24
        if self.selecionado.pai:
            go.transform.definir_pai(self.selecionado.pai.transform)
        self.motor.cena.adicionar(go)
        self.selecionado = go
        self._avisar("duplicado")

    def novo(self):
        cam = self.motor.camera
        go = self.motor.cena.criar("Novo objeto", cam.x, cam.y)
        self.selecionado = go

    def salvar(self):
        try:
            self.motor.cena.salvar(self.arquivo)
            self._avisar(f"cena salva em {self.arquivo}")
        except Exception as e:
            self._avisar(f"erro ao salvar: {e}")

    def carregar(self):
        if not self.arquivo.exists():
            self._avisar(f"{self.arquivo} não existe")
            return
        try:
            self.motor.cena.carregar(self.arquivo)
            self.selecionado = None
            self._avisar(f"cena carregada de {self.arquivo}")
        except Exception as e:
            self._avisar(f"erro ao carregar: {e}")

    # --- edição de campos ---------------------------------------------------------
    def _valor(self, alvo, campo):
        return getattr(alvo, campo)

    def _aplicar(self, alvo, campo, tipo, texto):
        try:
            if tipo == "float":
                v = float(texto.replace(",", "."))
            elif tipo == "int":
                v = int(float(texto.replace(",", ".")))
            elif tipo == "bool":
                v = texto.strip().lower() in ("1", "true", "sim", "verdadeiro")
            elif tipo == "cor":
                partes = [float(p) for p in texto.replace(";", ",").split(",") if p.strip()]
                v = tuple((partes + [1.0])[:4]) if len(partes) >= 3 else self._valor(alvo, campo)
            else:
                v = texto
            if campo == "imagem" and hasattr(alvo, "trocar_imagem"):
                alvo.trocar_imagem(v)
            else:
                setattr(alvo, campo, v)
        except ValueError:
            self._avisar(f"valor inválido para {campo}: {texto!r}")

    def _processar_digitacao(self):
        ent = self.motor.entrada
        alvo, campo, tipo, texto = self._edicao
        if ent.tecla_baixou("escape"):
            self._edicao = None
            return
        if ent.tecla_baixou("return") or ent.tecla_baixou("enter"):
            self._aplicar(alvo, campo, tipo, texto)
            self._edicao = None
            return
        if ent.tecla_baixou("backspace"):
            texto = texto[:-1]
        texto += ent.texto_digitado
        self._edicao = (alvo, campo, tipo, texto)
        if ent.clicou(1):   # clicar fora confirma
            self._aplicar(alvo, campo, tipo, texto)
            self._edicao = None

    def _roda_em_campo(self, roda) -> bool:
        ent = self.motor.entrada
        for rect, alvo, campo, tipo in self._linhas_insp:
            if rect.collidepoint(ent.mouse_tela) and tipo in ("float", "int"):
                passo = 1.0
                if ent.tecla("left shift"):
                    passo = 10.0
                elif ent.tecla("left ctrl"):
                    passo = 0.1
                v = self._valor(alvo, campo) + roda * passo
                setattr(alvo, campo, int(v) if tipo == "int" else round(v, 4))
                return True
        return False

    # --- desenho ----------------------------------------------------------------------
    def desenhar(self, ui) -> None:
        m = self.motor
        if not self.ativo:
            ui.texto(m.largura - 8, m.altura - 6, "F1: depurar", 13, cor=(200, 200, 200), ancora="bottomright")
            return
        self._gizmos(ui)
        self._barra(ui)
        self._hierarquia(ui)
        self._inspector(ui)
        txt, t = self.mensagem
        if t > 0:
            self.mensagem = (txt, t - 1 / 60)
            ui.texto(m.largura / 2, m.altura - 30, txt, 16, cor=CORES["destaque"], ancora="center")

    def _barra(self, ui):
        m = self.motor
        ui.retangulo((0, 0, m.largura, ALT_BARRA), (28, 30, 40, 240), raio=0, bloquear=True)
        x = 6
        botoes = [("|| Pausar" if self.rodando else "> Play", lambda: setattr(self, "rodando", not self.rodando), 92),
                  ("Passo", lambda: setattr(self, "passo_unico", True), 60),
                  ("Salvar", self.salvar, 64), ("Carregar", self.carregar, 74), ("Novo", self.novo, 54),
                  ("Duplicar", self.duplicar if self.selecionado else None, 74),
                  ("Excluir", self.excluir if self.selecionado else None, 64)]
        for rotulo, acao, w in botoes:
            if ui.botao((x, 4, w, 26), rotulo, ativo=acao is not None, tamanho_texto=14) and acao:
                acao()
            x += w + 4
        st = m.renderizador.stats
        cena = m.cena
        info = (f"FPS {m.fps_medio:5.1f} | objetos {len(cena.objetos)} | sprites {st.sprites_desenhados} | "
                f"draw calls {st.chamadas_desenho} | colisores {len(cena.fisica.colisores)} | "
                f"update {m.tempos['atualizar']:.1f} ms  render {m.tempos['render']:.1f} ms")
        ui.texto(m.largura - 8, ALT_BARRA / 2, info, 13, ancora="midright")
        ui.texto(x + 8, ALT_BARRA / 2, "EDITOR" + ("" if self.rodando else " (pausado)"), 14,
                 cor=CORES["destaque"], ancora="midleft", negrito=True)

    def _hierarquia(self, ui):
        m = self.motor
        ent = m.entrada
        h = m.altura - ALT_BARRA
        ui.retangulo((0, ALT_BARRA, LARG_HIER, h), (24, 26, 34, 235), raio=0, bloquear=True)
        ui.texto(8, ALT_BARRA + 6, f"Hierarquia ({len(m.cena.objetos)})", 15, negrito=True)
        linhas = []

        def visitar(go, nivel):
            linhas.append((go, nivel))
            if go.id in self._expandidos:
                for f in go.filhos:
                    visitar(f, nivel + 1)
        for r in m.cena.raizes():
            visitar(r, 0)
        cabem = (h - 34) // ALT_LINHA
        self.rolagem_hier = min(self.rolagem_hier, max(0, len(linhas) - cabem))
        y = ALT_BARRA + 30
        for go, nivel in linhas[self.rolagem_hier:self.rolagem_hier + cabem]:
            r = pygame.Rect(2, y, LARG_HIER - 4, ALT_LINHA)
            if go is self.selecionado:
                ui.retangulo(r, (60, 80, 130), raio=3)
            elif r.collidepoint(ent.mouse_tela):
                ui.retangulo(r, (45, 50, 66), raio=3)
            cor = CORES["texto"] if go.ativo_na_hierarquia else (120, 120, 120)
            aberto = go.id in self._expandidos
            prefixo = ("- " if aberto else "+ ") if go.filhos else "   "
            rotulo = go.nome[:26] + (f"  ({len(go.filhos)})" if go.filhos and not aberto else "")
            ui.texto(8 + nivel * 14, y + 2, prefixo + rotulo, 14, cor=cor, sombra=False)
            if go.tag:
                ui.texto(LARG_HIER - 8, y + 3, go.tag[:10], 11, cor=(150, 150, 170), ancora="topright", sombra=False)
            if r.collidepoint(ent.mouse_tela) and ent.clicou(1):
                if go.filhos and ent.mouse_tela[0] < 22 + nivel * 14:
                    self._expandidos ^= {go.id}      # clicar no +/- abre/fecha
                else:
                    self.selecionado = go
                ent.consumir_clique()
            y += ALT_LINHA
        if len(linhas) > cabem:
            ui.texto(LARG_HIER - 8, m.altura - 6, f"{self.rolagem_hier + 1}-{min(len(linhas), self.rolagem_hier + cabem)} "
                     f"de {len(linhas)} (roda)", 11, cor=(150, 150, 150), ancora="bottomright")

    def _inspector(self, ui):
        m = self.motor
        ent = m.entrada
        x0 = m.largura - LARG_INSP
        h = m.altura - ALT_BARRA
        ui.retangulo((x0, ALT_BARRA, LARG_INSP, h), (24, 26, 34, 235), raio=0, bloquear=True)
        ui.texto(x0 + 8, ALT_BARRA + 6, "Inspector", 15, negrito=True)
        self._linhas_insp = []
        go = self.selecionado
        if go is None:
            ui.texto(x0 + 8, ALT_BARRA + 34, "Clique num objeto na cena", 14, cor=(160, 160, 160))
            ui.texto(x0 + 8, ALT_BARRA + 54, "ou na hierarquia.", 14, cor=(160, 160, 160))
            return
        itens = []   # (tipo_item, ...)
        itens.append(("campo", go, "nome", "str"))
        itens.append(("campo", go, "tag", "str"))
        itens.append(("campo", go, "ativo", "bool"))
        itens.append(("titulo", "Transform", None))
        for c in ("x", "y", "rotacao", "escala_x", "escala_y"):
            itens.append(("campo", go.transform, c, "float"))
        for comp in go.componentes:
            itens.append(("titulo", type(comp).__name__, comp))
            for campo, tipo in comp._todos_campos().items():
                itens.append(("campo", comp, campo, tipo))
            extra = getattr(comp, "linhas_inspector", None)
            if extra:
                for linha in extra():
                    itens.append(("info", linha))
        cabem = (h - 34) // ALT_LINHA
        self.rolagem_insp = min(self.rolagem_insp, max(0, len(itens) - cabem))
        y = ALT_BARRA + 30
        for item in itens[self.rolagem_insp:self.rolagem_insp + cabem]:
            if item[0] == "titulo":
                _, nome, comp = item
                ui.retangulo((x0 + 2, y + 1, LARG_INSP - 4, ALT_LINHA - 2), (44, 50, 70), raio=3)
                ui.texto(x0 + 8, y + 2, nome, 14, negrito=True, sombra=False)
                if comp is not None:
                    r = pygame.Rect(m.largura - 26, y + 2, 16, 16)
                    pygame.draw.rect(ui.surface, (200, 200, 200), r, 1)
                    if comp.habilitado:
                        pygame.draw.rect(ui.surface, CORES["verde"], r.inflate(-6, -6))
                    if r.collidepoint(ent.mouse_tela) and ent.clicou(1):
                        comp.habilitado = not comp.habilitado
                        ent.consumir_clique()
            elif item[0] == "info":
                ui.texto(x0 + 14, y + 3, item[1][:46], 12, cor=(170, 200, 170), sombra=False)
            else:
                _, alvo, campo, tipo = item
                r = pygame.Rect(x0 + 2, y, LARG_INSP - 4, ALT_LINHA)
                self._linhas_insp.append((r, alvo, campo, tipo))
                ui.texto(x0 + 14, y + 2, campo, 13, cor=(190, 190, 200), sombra=False)
                vr = pygame.Rect(x0 + 130, y + 1, LARG_INSP - 136, ALT_LINHA - 2)
                editando = self._edicao is not None and self._edicao[0] is alvo and self._edicao[1] == campo
                ui.retangulo(vr, (60, 70, 100) if editando else (36, 40, 52), raio=3)
                valor = getattr(alvo, campo, "")
                if editando:
                    txt = self._edicao[3] + ("|" if int(m.tempo_total * 2) % 2 == 0 else "")
                elif tipo == "bool":
                    txt = "[x] sim" if valor else "[  ] não"
                elif tipo == "float":
                    txt = f"{valor:.2f}"
                elif tipo == "cor":
                    txt = ", ".join(f"{c:.2f}" for c in valor)
                    pygame.draw.rect(ui.surface, tuple(int(255 * max(0, min(1, c))) for c in valor[:3]),
                                     (vr.right - 18, vr.y + 3, 14, vr.h - 6))
                else:
                    txt = str(valor)
                ui.texto(vr.x + 5, vr.y + 1, txt[:34], 13, sombra=False)
                if r.collidepoint(ent.mouse_tela) and ent.clicou(1):
                    ent.consumir_clique()
                    if tipo == "bool":
                        setattr(alvo, campo, not valor)
                    else:
                        inicial = ", ".join(f"{c:g}" for c in valor) if tipo == "cor" else (
                            f"{valor:g}" if tipo == "float" else str(valor))
                        self._edicao = (alvo, campo, tipo, inicial)
            y += ALT_LINHA

    def _gizmos(self, ui):
        m = self.motor
        cena = m.cena
        if self.mostrar_colisores:
            for c in cena.fisica.colisores:
                if not c.gameobject.ativo_na_hierarquia:
                    continue
                cor = (80, 220, 120) if not c.gatilho else (90, 170, 255)
                self._desenhar_colisor(ui, c, cor)
        go = self.selecionado
        if go is None:
            return
        rend = go.obter("SpriteRenderer")
        if rend is not None and getattr(rend, "sprite", None) is not None:
            mat = rend.sprite.matriz_final()
            from . import matematica as M
            cantos = [ui.mundo_para_tela(*M.aplicar(mat, px, py))
                      for px, py in ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5))]
            pygame.draw.lines(ui.surface, CORES["destaque"], True, cantos, 2)
        x, y = ui.mundo_para_tela(*go.transform.posicao_mundo)
        # eixos locais (vermelho = +x, verde = +y)
        _, _, r, _, _ = go.transform.mundo()
        c, s = math.cos(math.radians(r)), math.sin(math.radians(r))
        ui.linha((x, y), (x + 40 * c, y - 40 * s), (230, 70, 70), 3)
        ui.linha((x, y), (x - 40 * s, y - 40 * c), (70, 220, 90), 3)
        for c2 in go.obter_todos("Colisor"):
            self._desenhar_colisor(ui, c2, CORES["destaque"], 2)

    def _desenhar_colisor(self, ui, c, cor, largura=1):
        cam = self.motor.camera
        cx, cy = ui.mundo_para_tela(*c.centro())
        e = c.escala() * cam.zoom
        if c.forma == "circulo":
            pygame.draw.circle(ui.surface, cor, (int(cx), int(cy)), max(1, int(c.raio * e)), largura)
        else:
            w, h = c.largura * e, c.altura * e
            pygame.draw.rect(ui.surface, cor, (cx - w / 2, cy - h / 2, w, h), largura)
