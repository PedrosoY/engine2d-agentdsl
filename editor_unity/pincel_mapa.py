"""Paleta e pincel do MapaTiles: editar o mapa clicando nos blocos, direto na Scene.

* Selecione o objeto do mapa (ou clique num bloco dele na Scene): o Inspector mostra a PALETA.
* Clique num bloco da paleta e pinte clicando/arrastando na Scene.
* Shift + clique/arrastar apaga. Ctrl + clique pega o bloco que está na célula (conta-gotas).
* Arraste uma imagem ou um prefab do Project para a paleta: vira um bloco novo.
* Esc (ou "Parar de pintar") volta ao modo normal (mover o objeto com o gizmo).
* Ctrl+Z desfaz a pintura. O arquivo .mapa é salvo sozinho.
"""
from __future__ import annotations

from pathlib import Path

import pygame

from .widgets import COR, botao

TAM = 46            # tamanho de um quadradinho da paleta


class PincelMapaMixin:
    def _init_pincel(self):
        self.pincel: str | None = None          # letra escolhida na paleta ("." = borracha)
        self._pincel_go = None                  # o objeto do mapa em que o pincel vale
        self._pintura = None                    # pintura em andamento (arrastando)
        self._r_paleta = None

    # --- qual mapa ------------------------------------------------------------------------------
    def mapa_selecionado(self):
        go = self.selecionado
        if go is None or go.destruido:
            return None
        return go.obter("MapaTiles")

    def _conferir_pincel(self):
        """O pincel só vale enquanto o mesmo mapa estiver selecionado."""
        if self.pincel is not None and (self.selecionado is None or self.selecionado is not self._pincel_go):
            self.pincel = None
            self._pintura = None

    def escolher_pincel(self, letra):
        self.pincel = letra
        self._pincel_go = self.selecionado

    def _garantir_arquivo(self, mapa):
        """Mapa sem arquivo ainda: cria Assets/Fases/<nome>.mapa."""
        if mapa.arquivo:
            return
        nome = "".join(ch for ch in mapa.gameobject.nome.lower() if ch.isalnum() or ch == "_") or "mapa"
        pasta = self.projeto.raiz / "Assets" / "Fases"
        pasta.mkdir(parents=True, exist_ok=True)
        arq = pasta / f"{nome}.mapa"
        k = 2
        while arq.exists():
            arq = pasta / f"{nome}{k}.mapa"
            k += 1
        mapa.arquivo = self.projeto.relativo(arq)
        mapa.salvar()
        self.modificado = True
        self.log(f"Mapa novo: {mapa.arquivo}")

    # --- desfazer -----------------------------------------------------------------------------------
    def _foto_mapa(self, mapa):
        t = mapa.transform
        return ("mapa", self._caminho_de(mapa.gameobject), mapa.texto(), (t.x, t.y))

    def _caminho_de(self, go):
        partes = []
        while go is not None:
            partes.append(go.nome)
            go = go.pai
        return list(reversed(partes))

    def _guardar_desfazer_mapa(self, foto):
        self.desfazer_pilha.append(foto)
        del self.desfazer_pilha[:-60]
        self.refazer_pilha.clear()

    def desfazer_mapa(self, foto, para):
        """Volta o mapa para a ``foto`` e guarda o estado atual em ``para`` (refazer/desfazer)."""
        _, caminho, texto, (x, y) = foto
        self._selecionar_por_caminho(caminho)
        mapa = self.mapa_selecionado()
        if mapa is None:
            return
        para.append(self._foto_mapa(mapa))
        mapa.transform.x, mapa.transform.y = x, y
        mapa.carregar_texto(texto)

    # --- Scene: pintar ----------------------------------------------------------------------------
    def pintar_mapa(self, ent, mx, my) -> bool:
        """Trata o mouse na Scene quando há um pincel. Devolve True se usou o clique."""
        self._conferir_pincel()
        mapa = self.mapa_selecionado()
        p = self._pintura
        if p is not None:                                   # arrastando: continua pintando
            if mapa is None or not ent.mouse_pressionado(1):
                self._terminar_pintura(mapa)
                return True
            self._pintar_ate(mapa, *mapa.celula_em(*self.tela_para_mundo(mx, my)))
            return True
        if mapa is None or not ent.clicou(1) or not self.livre("scene"):
            return False
        ctrl = ent.tecla("left ctrl") or ent.tecla("right ctrl")
        c, r = mapa.celula_em(*self.tela_para_mundo(mx, my))
        if ctrl:                                            # conta-gotas
            letra = mapa.letra_na_celula(c, r)
            self.escolher_pincel(letra)
            return True
        if self.pincel is None:
            return False
        self._garantir_arquivo(mapa)
        shift = ent.tecla("left shift") or ent.tecla("right shift")
        self._pintura = {"foto": self._foto_mapa(mapa), "letra": mapa.VAZIO if shift else self.pincel,
                         "ultima": None, "mudou": False, "origem": (mapa.transform.x, mapa.transform.y)}
        self._pintar_ate(mapa, c, r)
        return True

    def _pintar_ate(self, mapa, c, r):
        """Pinta da última célula até (c, r) sem pular células quando o mouse anda rápido."""
        p = self._pintura
        ultima = p["ultima"]
        celulas = [(c, r)]
        if ultima is not None and ultima != (c, r):
            (c0, r0), n = ultima, max(abs(c - ultima[0]), abs(r - ultima[1]))
            celulas = [(round(c0 + (c - c0) * i / n), round(r0 + (r - r0) * i / n)) for i in range(1, n + 1)]
        elif ultima == (c, r):
            return
        for cc, rr in celulas:
            x_antes, y_antes = mapa.transform.x, mapa.transform.y
            if mapa.definir_celula(cc, rr, p["letra"]):
                p["mudou"] = True
                # o mapa cresceu para a esquerda/cima: as próximas células mudam de número
                dc = round((x_antes - mapa.transform.x) / mapa.tamanho_celula)
                dr = round((mapa.transform.y - y_antes) / mapa.tamanho_celula)
                c, r = c + dc, r + dr
                celulas = [(a + dc, b + dr) for a, b in celulas]
        p["ultima"] = (c, r)

    def _terminar_pintura(self, mapa):
        p, self._pintura = self._pintura, None
        if p is None or mapa is None or not p["mudou"]:
            return
        mapa.salvar()
        self._guardar_desfazer_mapa(p["foto"])
        if (mapa.transform.x, mapa.transform.y) != p["origem"]:
            self.modificado = True                   # o objeto andou (o mapa cresceu para a esquerda/cima)

    def desenhar_pincel(self, ui):
        """Quadrado na célula sob o mouse, com a prévia do bloco escolhido."""
        self._conferir_pincel()
        mapa = self.mapa_selecionado()
        if mapa is None or not self.r_scene.collidepoint(self.motor.entrada.mouse_tela):
            return
        ent = self.motor.entrada
        c, r = mapa.celula_em(*self.tela_para_mundo(*ent.mouse_tela))
        cx, cy = mapa.centro_da_celula(c, r)
        meio = mapa.tamanho_celula / 2
        a = self.mundo_para_tela(cx - meio, cy + meio)
        b = self.mundo_para_tela(cx + meio, cy - meio)
        rect = pygame.Rect(int(a[0]), int(a[1]), max(2, int(b[0] - a[0])), max(2, int(b[1] - a[1])))
        if self.pincel is None:
            pygame.draw.rect(ui.surface, (230, 230, 230), rect, 1)
            return
        apagando = ent.tecla("left shift") or ent.tecla("right shift") or self.pincel == mapa.VAZIO
        img = None if apagando else mapa.imagem_do_bloco(self.pincel)
        if img:
            try:
                prev = pygame.transform.smoothscale(ui.imagem(img), rect.size).copy()
                prev.set_alpha(150)
                ui.surface.blit(prev, rect)
            except Exception:
                pass
        pygame.draw.rect(ui.surface, COR["vermelho"] if apagando else COR["amarelo"], rect, 2)

    # --- Inspector: a paleta -------------------------------------------------------------------------
    def desenhar_paleta(self, ui, area, y, mapa, livre):
        ent = self.motor.entrada
        x0, w = area.x + 8, area.w - 16
        ui.texto(x0 + 4, y + 9, "Paleta", 13, ancora="midleft", negrito=True, sombra=False)
        ui.texto(x0 + 60, y + 9, "clique num bloco e pinte na Scene", 11, ancora="midleft", sombra=False,
                 cor=COR["texto2"])
        y += 22
        letras = [mapa.VAZIO] + list(mapa.legenda)
        cols = max(1, (w - 4) // (TAM + 4))
        linhas = (len(letras) + cols) // cols
        self._r_paleta = pygame.Rect(x0, y, w, linhas * (TAM + 4) + 4)
        pygame.draw.rect(ui.surface, COR["campo"], self._r_paleta, border_radius=4)
        if self.arrasto is not None and self.arrasto.ativo and self._r_paleta.collidepoint(ent.mouse_tela):
            pygame.draw.rect(ui.surface, COR["destaque"], self._r_paleta, 2, border_radius=4)
        self._quadros_paleta = []
        dica = None
        for i, letra in enumerate(letras):
            r = pygame.Rect(x0 + 4 + (i % cols) * (TAM + 4), y + 4 + (i // cols) * (TAM + 4), TAM, TAM)
            self._quadros_paleta.append((r, letra))
            escolhido = self.pincel == letra and self._pincel_go is self.selecionado
            hover = livre and r.collidepoint(ent.mouse_tela)
            pygame.draw.rect(ui.surface, COR["hover"] if hover else COR["fundo2"], r, border_radius=3)
            if letra == mapa.VAZIO:                       # borracha
                pygame.draw.line(ui.surface, COR["vermelho"], (r.x + 12, r.y + 12), (r.right - 12, r.bottom - 12), 3)
                pygame.draw.line(ui.surface, COR["vermelho"], (r.right - 12, r.y + 12), (r.x + 12, r.bottom - 12), 3)
                nome = "borracha (apaga)"
            else:
                img = mapa.imagem_do_bloco(letra)
                if img:
                    try:
                        s = ui.imagem(img, TAM - 8)
                        ui.surface.blit(s, s.get_rect(center=r.center))
                    except Exception:
                        pass
                d = mapa.legenda[letra]
                ui.texto(r.right - 3, r.bottom - 1, letra, 11, ancora="bottomright", sombra=True)
                nome = Path(d.get("imagem") or d.get("prefab", "")).stem
                if d.get("prefab"):
                    nome += " (prefab)"
                elif d.get("solido"):
                    nome += " (sólido)"
                elif d.get("so_por_cima"):
                    nome += " (atravessável)"
            if escolhido:
                pygame.draw.rect(ui.surface, COR["amarelo"], r, 2, border_radius=3)
            if hover:
                dica = nome
                if ent.clicou(1):
                    ent.consumir_clique()
                    self.escolher_pincel(None if escolhido else letra)
        y = self._r_paleta.bottom + 4
        if dica:
            ui.texto(x0 + 4, y + 8, dica, 12, ancora="midleft", sombra=False, cor=COR["amarelo"])
        y += 18
        letra = self.pincel if self._pincel_go is self.selecionado else None
        if letra and letra != mapa.VAZIO and letra in mapa.legenda:
            d = mapa.legenda[letra]
            if "imagem" in d:
                for chave, rotulo in (("solido", "Sólido (chão/parede)"), ("so_por_cima", "Atravessável por baixo")):
                    cb = pygame.Rect(x0 + 6, y + 2, 16, 16)
                    self._checkbox(ui, cb, d.get(chave, False), livre,
                                   lambda v, k=chave, l=letra: self._mudar_bloco(mapa, l, **{k: v}))
                    self._campos_insp.append((cb, mapa, f"bloco_{chave}", "bool"))
                    ui.texto(x0 + 30, y + 10, rotulo, 12, ancora="midleft", sombra=False)
                    y += 22
            if botao(ui, (x0 + 4, y, 150, 22), "Tirar da paleta", livre, tamanho=12):
                self._remover_bloco(mapa, letra)
            y += 28
        if self.pincel is not None and self._pincel_go is self.selecionado:
            if botao(ui, (x0 + 4, y, 150, 22), "Parar de pintar (Esc)", livre, tamanho=12):
                self.pincel = None
            y += 28
        for d in ("Shift + clique apaga · Ctrl + clique pega o bloco",
                  "Arraste uma imagem/prefab do Project para cá",
                  "para criar um bloco novo. Ctrl+Z desfaz."):
            ui.texto(x0 + 4, y + 7, d, 11, ancora="midleft", sombra=False, cor=COR["texto2"])
            y += 15
        return y + 8

    def soltar_na_paleta(self, a, mx, my) -> bool:
        """Imagem ou prefab solto na paleta: vira um bloco novo (e já fica escolhido)."""
        mapa = self.mapa_selecionado()
        if mapa is None or self._r_paleta is None or not self._r_paleta.collidepoint(mx, my) or a.tipo != "asset":
            return False
        arq: Path = a.valor
        ext = arq.suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".prefab"):
            self.log("Para a paleta: arraste uma imagem (.png) ou um prefab", "aviso")
            return True
        self._garantir_arquivo(mapa)
        foto = self._foto_mapa(mapa)
        rel = self.projeto.relativo(arq)
        letra = mapa.adicionar_bloco(prefab=rel) if ext == ".prefab" else mapa.adicionar_bloco(imagem=rel, solido=True)
        mapa.salvar()
        self._guardar_desfazer_mapa(foto)
        self.escolher_pincel(letra)
        self.log(f"Bloco '{letra}' = {arq.name} na paleta" + ("" if ext == ".prefab" else " (sólido)"))
        return True

    def _mudar_bloco(self, mapa, letra, **campos):
        foto = self._foto_mapa(mapa)
        mapa.definir_bloco(letra, **campos)
        mapa.salvar()
        self._guardar_desfazer_mapa(foto)

    def _remover_bloco(self, mapa, letra):
        foto = self._foto_mapa(mapa)
        mapa.remover_bloco(letra)
        mapa.salvar()
        self._guardar_desfazer_mapa(foto)
        self.pincel = None
