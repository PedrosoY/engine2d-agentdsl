"""Painel Hierarchy: árvore de GameObjects da cena."""
from __future__ import annotations

import pygame

from .widgets import ALT, COR, botao, painel, recortar, seta


class HierarquiaMixin:
    def _init_hierarquia(self):
        self.rolagem_hier = 0
        self.abertos: set[int] = set()
        self._linhas_hier: list = []

    def _linhas_arvore(self):
        linhas = []

        def visitar(go, nivel):
            if go.oculto:
                return
            linhas.append((go, nivel))
            if go.id in self.abertos:
                for f in go.filhos:
                    visitar(f, nivel + 1)
        for g in self.cena.raizes():
            visitar(g, 0)
        return linhas

    @staticmethod
    def _zona_soltar(r, my):
        """Onde o objeto arrastado cai numa linha: 'antes' (quarto de cima), 'depois' (quarto de
        baixo) ou 'dentro' (meio = vira filho)."""
        if my < r.y + r.h * 0.28:
            return "antes"
        if my > r.bottom - r.h * 0.28:
            return "depois"
        return "dentro"

    def revelar(self, go):
        p = go.pai
        while p is not None:
            self.abertos.add(p.id)
            p = p.pai

    def _desenhar_hierarquia(self, ui):
        area, _ = painel(ui, self.r_hier, titulo="Hierarchy")
        ent = self.motor.entrada
        livre = self.livre("hier")
        if botao(ui, (self.r_hier.right - 30, self.r_hier.y + 2, 26, 18), "+", livre):
            self.abrir_popup(self.r_hier.right - 30, self.r_hier.y + 22, self._itens_criar(None), largura=200)
        nome_cena = (self.caminho_cena.stem if self.caminho_cena else "Nova cena") + (" *" if self.modificado else "")
        seta(ui, area.x + 10, area.y + 11, True)
        ui.texto(area.x + 18, area.y + 4, nome_cena, 13, negrito=True, sombra=False)
        linhas = self._linhas_arvore()
        y0 = area.y + 24
        cabem = max(1, (area.bottom - y0) // ALT)
        if livre and ent.roda:
            self.rolagem_hier = self.rolagem_hier - ent.roda * 3
        self.rolagem_hier = max(0, min(self.rolagem_hier, max(0, len(linhas) - cabem)))
        self._linhas_hier = []
        clicou_em_algo = False
        with recortar(ui, area):
            y = y0
            for go, nivel in linhas[self.rolagem_hier:self.rolagem_hier + cabem]:
                r = pygame.Rect(area.x, y, area.w, ALT)
                self._linhas_hier.append((r, go))
                hover = livre and r.collidepoint(ent.mouse_tela)
                arrastando_aqui = self.arrasto is not None and self.arrasto.ativo and r.collidepoint(ent.mouse_tela)
                if go is self.selecionado:
                    pygame.draw.rect(ui.surface, COR["selecao"], r)
                elif hover:
                    pygame.draw.rect(ui.surface, COR["hover"], r)
                if arrastando_aqui and self.arrasto.tipo == "objeto":
                    zona = self._zona_soltar(r, ent.mouse_tela[1])
                    if zona == "dentro":
                        pygame.draw.rect(ui.surface, COR["destaque"], r, 1)
                    else:                     # linha mostrando onde ele vai entrar
                        yl = r.y if zona == "antes" else r.bottom - 1
                        pygame.draw.line(ui.surface, COR["destaque"], (r.x + 8 + nivel * 14, yl), (r.right, yl), 2)
                elif arrastando_aqui:
                    pygame.draw.rect(ui.surface, COR["destaque"], r, 1)
                x = area.x + 8 + nivel * 14
                alca = pygame.Rect(x, y, 14, ALT)
                if go.filhos:
                    seta(ui, alca.centerx, alca.centery, go.id in self.abertos)
                icone = "●" if go.obter("CameraPrincipal") is None else "■"
                ui.texto(x + 16, r.centery, icone, 11, ancora="midleft", sombra=False,
                         cor=(120, 170, 230) if go.ativo_na_hierarquia else COR["texto2"])
                ui.texto(x + 30, r.centery, go.nome, 13, ancora="midleft", sombra=False,
                         cor=COR["texto"] if go.ativo_na_hierarquia else COR["texto2"])
                if hover and ent.clicou(1):
                    clicou_em_algo = True
                    ent.consumir_clique()
                    if go.filhos and alca.collidepoint(ent.mouse_tela):
                        self.abertos ^= {go.id}
                    else:
                        if self.clique_duplo.testar(("hier", go.id)):
                            self.focar(go)
                        self.selecionado = go
                        self.asset_selecionado = None
                        self.iniciar_arrasto("objeto", go, go.nome)
                if hover and ent.clicou(3):
                    clicou_em_algo = True
                    self.selecionado = go
                    self.abrir_popup(*ent.mouse_tela, self._itens_contexto_objeto(go), largura=210)
                y += ALT
        if livre and not clicou_em_algo:
            if ent.clicou(1) and area.collidepoint(ent.mouse_tela):
                self.selecionado = None
            if ent.clicou(3) and area.collidepoint(ent.mouse_tela):
                self.abrir_popup(*ent.mouse_tela, self._itens_criar(None), largura=200)

    def _itens_criar(self, pai):
        return [("Criar vazio", lambda: self.criar_objeto("vazio", pai=pai), ""),
                ("Sprite", lambda: self.criar_objeto("sprite", pai=pai), ""),
                ("Sprite com física", lambda: self.criar_objeto("fisica", pai=pai), ""),
                ("Câmera", lambda: self.criar_objeto("camera", pai=pai), ""),
                ("Texto (UI)", lambda: self.criar_objeto("texto", pai=pai), ""), None] + self._itens_formas(pai)

    def _itens_contexto_objeto(self, go):
        return [("Criar filho vazio", lambda: self.criar_objeto("vazio", pai=go), ""),
                ("Criar filho sprite", lambda: self.criar_objeto("sprite", pai=go), ""), None,
                ("Renomear", self.renomear_selecionado, "F2"), ("Duplicar", self.duplicar, "Ctrl+D"),
                ("Focar", lambda: self.focar(go), "F"),
                ("Tirar do pai", (lambda: self._mudar_pai(go, None)) if go.pai else None, ""),
                ("Salvar como prefab", lambda: self.salvar_prefab(go, self.projeto.raiz / "Assets" / "Prefabs"), ""),
                None, ("Excluir", self.excluir, "Del")]

    def _mudar_pai(self, go, novo_pai):
        if novo_pai is go or go.pai is novo_pai:
            return
        p = novo_pai
        while p is not None:          # não pode virar filho de um descendente
            if p is go:
                self.log("Não dá para colocar um objeto dentro de um filho dele.", "aviso")
                return
            p = p.pai
        self.marcar()
        go.transform.definir_pai(novo_pai.transform if novo_pai else None, manter_mundo=True)
        if novo_pai is not None:
            self.abertos.add(novo_pai.id)

    def _reordenar(self, go, pai, posicao):
        """Muda a posição do objeto na Hierarchy (e, se preciso, o pai). A ordem vale como desempate
        na ordem de desenho: mais embaixo na lista = desenhado por cima."""
        p = pai
        while p is not None:
            if p is go:
                self.log("Não dá para colocar um objeto dentro de um filho dele.", "aviso")
                return
            p = p.pai
        self.marcar()
        self.cena.mover_na_hierarquia(go, pai, posicao)
        if pai is not None:
            self.abertos.add(pai.id)

    def soltar_na_hierarquia(self, a, mx, my):
        if a.tipo == "objeto":
            linha = next(((r, go) for r, go in self._linhas_hier if r.collidepoint(mx, my)), None)
            go = a.valor
            if linha is None:                     # solto no vazio: vai para o fim da lista, na raiz
                self._reordenar(go, None, len(self.cena.raizes()))
                return
            r, alvo = linha
            zona = self._zona_soltar(r, my)
            if zona == "dentro" or alvo is go:
                self._mudar_pai(go, alvo)
                return
            pai = alvo.pai
            irmaos = pai.filhos if pai else self.cena.raizes()
            pos = irmaos.index(alvo) + (1 if zona == "depois" else 0)
            if go in irmaos and irmaos.index(go) < pos:
                pos -= 1                          # ele mesmo sai da lista antes de entrar de novo
            self._reordenar(go, pai, pos)
        elif a.tipo == "asset":
            arq = a.valor
            alvo = next((go for r, go in self._linhas_hier if r.collidepoint(mx, my)), None)
            if alvo is not None and arq.suffix.lower() in (".png", ".jpg", ".jpeg", ".py", ".agt"):
                self.selecionado = alvo
                self.usar_asset_no_objeto(arq, alvo)       # solto em cima de um objeto: usa nele
            elif arq.suffix.lower() == ".prefab":
                self.instanciar_prefab(arq, self.cam.x, self.cam.y)
            elif arq.suffix.lower() in (".png", ".jpg"):
                self.criar_objeto("sprite", imagem=self.projeto.relativo(arq))
