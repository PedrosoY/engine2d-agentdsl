"""Painel Inspector: propriedades do objeto ou do arquivo selecionado."""
from __future__ import annotations

import json
from pathlib import Path

import pygame

from engine2d.objeto import REGISTRO_COMPONENTES, ComponenteAusente

from .widgets import ALT, COR, botao, painel, recortar, seta

ROTULOS = {"x": "Posição X", "y": "Posição Y", "rotacao": "Rotação", "escala_x": "Escala X", "escala_y": "Escala Y"}


class InspectorMixin:
    def _init_inspector(self):
        self.rolagem_insp = 0
        self.recolhidos: set[tuple] = set()
        self._campos_insp: list = []      # (rect, alvo, campo, tipo) — para arrastar e soltar
        self._scrub = None                # arrasto sobre o rótulo de um número

    # ------------------------------------------------------------------------------
    def _desenhar_inspector(self, ui):
        area, _ = painel(ui, self.r_insp, titulo="Inspector")
        ent = self.motor.entrada
        livre = self.livre("insp")
        if livre and ent.roda:
            self.rolagem_insp = max(0, self.rolagem_insp - ent.roda * 40)
        self._campos_insp = []
        with recortar(ui, area):
            y = area.y + 6 - self.rolagem_insp
            if self.selecionado is not None and not self.selecionado.destruido:
                y = self._insp_objeto(ui, area, y, livre)
            elif self.asset_selecionado == "configuracoes":
                y = self._insp_configuracoes(ui, area, y, livre)
            elif self.asset_selecionado is not None:
                y = self._insp_asset(ui, area, y, livre)
            else:
                ui.texto(area.x + 10, y + 4, "Nada selecionado.", 13, sombra=False, cor=COR["texto2"])
                ui.texto(area.x + 10, y + 26, "Clique num objeto (Scene/Hierarchy)", 12, sombra=False, cor=COR["texto2"])
                ui.texto(area.x + 10, y + 44, "ou num arquivo (Project).", 12, sombra=False, cor=COR["texto2"])
                y += 70
            altura = y + self.rolagem_insp - area.y
            self.rolagem_insp = min(self.rolagem_insp, max(0, altura - area.h + 20))
        self._atualizar_scrub(ent)

    # --- objeto ---------------------------------------------------------------------
    def _insp_objeto(self, ui, area, y, livre):
        go = self.selecionado
        ent = self.motor.entrada
        x0, w = area.x + 8, area.w - 16
        # cabeçalho: ativo + nome + tag
        cb = pygame.Rect(x0, y + 3, 16, 16)
        self._checkbox(ui, cb, go.ativo, livre, lambda v: self._set(go, "ativo", v))
        r_nome = self.desenhar_campo_texto(ui, (x0 + 24, y, w - 24, 22), ("nome", go.id), go.nome,
                                           lambda t: self._set(go, "nome", t.strip() or go.nome), livre)
        self._campos_insp.append((r_nome, go, "nome", "objeto"))
        y += 28
        ui.texto(x0, y + 10, "Tag", 13, ancora="midleft", sombra=False, cor=COR["texto2"])
        tags = list(self.projeto.tags) if self.projeto else []
        if go.tag and go.tag not in tags:
            tags.append(go.tag)
        r_tag = self._caixa_escolha(ui, (x0 + 70, y, w - 70, 20), go.tag, [""] + tags,
                                    lambda v: self._set(go, "tag", v), livre, extra=("Nova tag...", self._nova_tag))
        self._campos_insp.append((r_tag, go, "tag", "escolha"))
        y += 30
        # Transform
        y = self._titulo_secao(ui, area, y, "Transform", ("t", go.id), None, livre)
        if ("t", go.id) not in self.recolhidos:
            for c in ("x", "y", "rotacao", "escala_x", "escala_y"):
                y = self._linha_campo(ui, area, y, go.transform, c, "float", livre, ROTULOS[c])
            y += 6
        # Componentes
        for comp in list(go.componentes):
            nome = comp.tipo_original if isinstance(comp, ComponenteAusente) else type(comp).__name__
            y = self._titulo_secao(ui, area, y, nome, ("c", id(comp)), comp, livre)
            if ("c", id(comp)) in self.recolhidos:
                continue
            arq_script = self._arquivo_do_script(type(comp))
            if arq_script is not None:
                r = pygame.Rect(x0, y, w, ALT)
                ui.texto(x0 + 6, r.centery, "Script", 13, ancora="midleft", sombra=False, cor=COR["texto2"])
                ui.texto(x0 + 120, r.centery, arq_script.name + "   (clique para abrir)", 13, ancora="midleft",
                         sombra=False, cor=(120, 170, 230))
                if livre and r.collidepoint(ent.mouse_tela) and ent.clicou(1):
                    ent.consumir_clique()
                    self.abrir_arquivo_externo(arq_script)
                y += ALT + 2
            for campo, tipo in comp._todos_campos().items():
                y = self._linha_campo(ui, area, y, comp, campo, tipo, livre)
            if nome == "MapaTiles" and comp._iniciado:
                y = self.desenhar_paleta(ui, area, y + 4, comp, livre)
            extra = getattr(comp, "linhas_inspector", None)
            if extra:
                for linha in extra():
                    ui.texto(x0 + 6, y + 10, linha, 12, ancora="midleft", sombra=False, cor=COR["amarelo"])
                    y += 18
            y += 8
        # Adicionar componente
        y += 6
        self.r_adicionar_componente = pygame.Rect(area.centerx - 110, y, 220, 26)
        if botao(ui, self.r_adicionar_componente, "Adicionar Componente", livre):
            self._popup_adicionar(area.centerx - 125, y + 28)
        return y + 50

    def _arquivo_do_script(self, cls):
        if self.projeto is None:
            return None
        for chave, info in self.projeto.scripts.items():
            if cls.__name__ in info["classes"]:
                return Path(chave)
        return None

    def _popup_adicionar(self, x, y):
        go = self.selecionado
        cats: dict[str, list] = {}
        scripts = set(self.projeto.classes_de_scripts()) if self.projeto else set()
        for nome, cls in sorted(REGISTRO_COMPONENTES.items()):
            menu = getattr(cls, "MENU", "Scripts")
            if not menu or cls is ComponenteAusente:
                continue
            if menu == "Scripts" and nome not in scripts:
                continue           # componentes internos dos jogos de exemplo não aparecem
            cats.setdefault(menu, []).append(nome)
        itens = []
        for cat in ["Renderização", "Luz", "Física", "UI", "Utilitários", "AgentDSL", "Scripts"]:
            if cat not in cats:
                continue
            itens.append((f"— {cat} —", None, ""))
            for nome in cats[cat]:
                itens.append(("    " + nome, (lambda n=nome: self._adicionar_componente(go, n)), ""))
        itens.append(None)
        itens.append(("Novo script...", lambda: self._novo_script_e_adicionar(go), ""))
        self.abrir_popup(x, y, itens, largura=250)

    def _adicionar_componente(self, go, nome):
        self.marcar()
        comp = go.adicionar(REGISTRO_COMPONENTES[nome]())
        self.cena.iniciar_pendentes()
        self.log(f"{nome} adicionado a '{go.nome}'")
        return comp

    def _novo_script_e_adicionar(self, go):
        def ok(nome):
            arq = self.projeto.criar_script(self.projeto.raiz / "Assets" / "Scripts", nome)
            self.recarregar_scripts()
            if arq.stem in REGISTRO_COMPONENTES:
                self._adicionar_componente(go, arq.stem)
            self.log(f"Script criado: {self.projeto.relativo(arq)} — clique em 'Script' no Inspector para editar")
        self.pedir_texto("Nome do novo script", "NovoScript", ok)

    def _titulo_secao(self, ui, area, y, nome, chave, comp, livre):
        ent = self.motor.entrada
        r = pygame.Rect(area.x, y, area.w, 22)
        pygame.draw.rect(ui.surface, COR["fundo2"], r)
        pygame.draw.line(ui.surface, COR["borda"], r.topleft, r.topright)
        aberto = chave not in self.recolhidos
        seta(ui, r.x + 12, r.centery, aberto)
        x = r.x + 24
        if comp is not None:
            self._checkbox(ui, pygame.Rect(x, y + 3, 16, 16), comp.habilitado, livre,
                           lambda v: self._set(comp, "habilitado", v))
            x += 22
        ui.texto(x, r.centery, nome, 13, ancora="midleft", negrito=True, sombra=False,
                 cor=COR["vermelho"] if isinstance(comp, ComponenteAusente) else COR["texto"])
        if comp is not None:
            rm = pygame.Rect(r.right - 26, y + 2, 20, 18)
            if botao(ui, rm, "…", livre):
                go = comp.gameobject
                i = go.componentes.index(comp)
                arq = self._arquivo_do_script(type(comp))
                self.abrir_popup(rm.x - 180, rm.bottom, [
                    ("Remover componente", lambda: self._remover_componente(comp), ""),
                    ("Mover para cima", (lambda: self._mover_componente(comp, -1)) if i > 0 else None, ""),
                    ("Mover para baixo", (lambda: self._mover_componente(comp, 1))
                     if i < len(go.componentes) - 1 else None, ""),
                    ("Restaurar valores padrão", lambda: self._resetar(comp), ""),
                    ("Editar script", (lambda: self.abrir_arquivo_externo(arq)) if arq else None, "")], largura=200)
                return y + 22
        if livre and r.collidepoint(ent.mouse_tela) and ent.clicou(1):
            ent.consumir_clique()
            self.recolhidos ^= {chave}
        return y + 24

    def _caixa_escolha(self, ui, rect, valor, opcoes, ao_escolher, livre, extra=None):
        """Caixa com ▼: clicar abre a lista de opções (tags, camadas de desenho...)."""
        ent = self.motor.entrada
        r = pygame.Rect(rect)
        hover = livre and r.collidepoint(ent.mouse_tela)
        pygame.draw.rect(ui.surface, COR["hover"] if hover else COR["campo"], r, border_radius=3)
        pygame.draw.rect(ui.surface, COR["borda"], r, 1, border_radius=3)
        ui.texto(r.x + 6, r.centery, valor if valor else "(nenhuma)", 13, ancora="midleft", sombra=False,
                 cor=COR["texto"] if valor else COR["texto2"])
        seta(ui, r.right - 10, r.centery, True)
        if hover and ent.clicou(1):
            itens = [(o if o else "(nenhuma)", (lambda o=o: ao_escolher(o)), "atual" if o == valor else "")
                     for o in opcoes]
            if extra:
                itens += [None, (extra[0], extra[1], "")]
            self.abrir_popup(r.x, r.bottom, itens, largura=max(180, r.w))
        return r

    def _nova_tag(self):
        def ok(nome):
            nome = nome.strip()
            if nome and nome not in self.projeto.tags:
                self.projeto.tags.append(nome)
                self.projeto.salvar_config()
                self.motor.configurar_projeto(self.projeto.configuracoes())
            if self.selecionado is not None:
                self._set(self.selecionado, "tag", nome)
        self.pedir_texto("Nome da nova tag", "nova_tag", ok)

    # --- Configurações do projeto -----------------------------------------------------------
    CONFIG = [("nome", "Nome do jogo", "texto"), ("largura", "Largura (px)", "int"), ("altura", "Altura (px)", "int"),
              ("gravidade_x", "Gravidade X", "num"), ("gravidade_y", "Gravidade Y", "num"),
              ("camadas_desenho", "Camadas de desenho", "lista"), ("tags", "Tags", "lista"),
              ("colisoes_ignoradas", "Não colidem", "lista")]

    def _insp_configuracoes(self, ui, area, y, livre):
        p = self.projeto
        x0, w = area.x + 8, area.w - 16
        ui.texto(x0 + 2, y + 4, "Configurações do projeto", 15, negrito=True, sombra=False)
        ui.texto(x0 + 2, y + 26, "salvas em projeto.json; valem para todas as cenas", 11, sombra=False,
                 cor=COR["texto2"])
        y += 50
        valores = {"nome": p.nome, "largura": p.largura, "altura": p.altura, "gravidade_x": p.gravidade[0],
                   "gravidade_y": p.gravidade[1], "camadas_desenho": ", ".join(p.camadas_desenho),
                   "tags": ", ".join(p.tags), "colisoes_ignoradas": ", ".join(p.colisoes_ignoradas)}
        for chave, rotulo, tipo in self.CONFIG:
            ui.texto(x0 + 4, y + 10, rotulo, 13, ancora="midleft", sombra=False, cor=COR["texto2"])
            v = valores[chave]
            r = self.desenhar_campo_texto(ui, (x0 + 140, y, w - 140, ALT - 2), ("config", chave),
                                          f"{v:g}" if isinstance(v, float) else v,
                                          lambda t, c=chave, tp=tipo: self._set_config(c, tp, t), livre)
            self._campos_insp.append((r, p, chave, "config"))
            y += ALT + 6
        dicas = ["Camadas de desenho: a primeira da lista fica atrás de todas.",
                 "Na mesma camada: menor 'ordem' atrás; empatou, quem vem",
                 "depois na Hierarchy fica na frente.",
                 "Não colidem: pares de camadas físicas, ex.: tiro:tiro, item:inimigo",
                 "Gravidade em px/s² (jogo de plataforma: Y = -1800; visto de cima: 0)."]
        for d in dicas:
            ui.texto(x0 + 4, y + 8, d, 11, ancora="midleft", sombra=False, cor=COR["texto2"])
            y += 16
        return y + 10

    def _set_config(self, chave, tipo, texto):
        p = self.projeto
        try:
            if tipo == "lista":
                valor = [s.strip() for s in texto.split(",") if s.strip()]
                if chave == "camadas_desenho" and not valor:
                    valor = ["Padrao"]
            elif tipo == "int":
                valor = int(float(texto.replace(",", ".")))
            elif tipo == "num":
                valor = float(texto.replace(",", "."))
            else:
                valor = texto.strip() or p.nome
        except ValueError:
            self.log(f"'{texto}' não é um número", "aviso")
            return
        if chave == "gravidade_x":
            p.gravidade = (valor, p.gravidade[1])
        elif chave == "gravidade_y":
            p.gravidade = (p.gravidade[0], valor)
        else:
            setattr(p, chave, valor)
        p.salvar_config()
        self.motor.configurar_projeto(p.configuracoes())
        self.log(f"Configurações do projeto: {chave} atualizado")

    def _checkbox(self, ui, r, valor, livre, ao_mudar):
        ent = self.motor.entrada
        pygame.draw.rect(ui.surface, COR["campo"], r, border_radius=2)
        pygame.draw.rect(ui.surface, COR["borda"], r, 1, border_radius=2)
        if valor:
            pygame.draw.lines(ui.surface, (220, 220, 220), False,
                              [(r.x + 3, r.centery), (r.x + 7, r.bottom - 4), (r.right - 3, r.y + 4)], 2)
        if livre and r.collidepoint(ent.mouse_tela) and ent.clicou(1):
            ent.consumir_clique()
            ao_mudar(not valor)

    def _linha_campo(self, ui, area, y, alvo, campo, tipo, livre, rotulo=None):
        ent = self.motor.entrada
        x0, w = area.x + 8, area.w - 16
        rot = rotulo or campo.replace("_", " ").capitalize()
        rr = pygame.Rect(x0, y, 120, ALT)
        ui.texto(x0 + 6, rr.centery, rot, 13, ancora="midleft", sombra=False, cor=COR["texto2"])
        vr = pygame.Rect(x0 + 124, y + 1, w - 124, ALT - 2)
        valor = getattr(alvo, campo, None)
        chave = (id(alvo), campo)
        if tipo != "str":
            self._campos_insp.append((vr, alvo, campo, tipo))
        if tipo in ("float", "int"):
            if livre and rr.collidepoint(ent.mouse_tela):
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEWE)
                if ent.clicou(1):     # arrastar sobre o rótulo muda o valor
                    ent.consumir_clique()
                    self._scrub = {"alvo": alvo, "campo": campo, "tipo": tipo, "x": ent.mouse_tela[0],
                                   "v0": valor, "marcado": False}
            txt = f"{valor:g}" if tipo == "float" else str(valor)
            self.desenhar_campo_texto(ui, vr, chave, txt, lambda t, a=alvo, c=campo, tp=tipo: self._set_num(a, c, tp, t),
                                      livre, numerico=True)
        elif tipo == "bool":
            self._checkbox(ui, pygame.Rect(vr.x, vr.y + 1, 16, 16), bool(valor), livre,
                           lambda v, a=alvo, c=campo: self._set(a, c, v))
        elif tipo.startswith("escolha:"):                 # lista fixa de opções, ex.: "escolha:circulo,caixa"
            opcoes = tipo.split(":", 1)[1].split(",")
            self._caixa_escolha(ui, vr, str(valor), opcoes, lambda v, a=alvo, c=campo: self._set(a, c, v), livre)
        elif tipo == "camada_desenho":
            opcoes = list(self.projeto.camadas_desenho) if self.projeto else ["Padrao"]
            if valor not in opcoes:
                opcoes.append(valor)
            self._caixa_escolha(ui, vr, valor, opcoes, lambda v, a=alvo, c=campo: self._set(a, c, v), livre,
                                extra=("Editar camadas...", self.abrir_configuracoes))
        elif tipo == "cor":
            cor = tuple(valor) + (1.0,) * (4 - len(valor))
            amostra = pygame.Rect(vr.right - 40, vr.y + 2, 36, vr.h - 4)
            txt = ", ".join(f"{c:g}" for c in cor)
            self.desenhar_campo_texto(ui, (vr.x, vr.y, vr.w - 46, vr.h), chave, txt,
                                      lambda t, a=alvo, c=campo: self._set_cor(a, c, t), livre)
            pygame.draw.rect(ui.surface, tuple(int(255 * max(0, min(1, c))) for c in cor[:3]), amostra)
            pygame.draw.rect(ui.surface, COR["borda"], amostra, 1)
        else:
            arrastando = self.arrasto is not None and self.arrasto.ativo and vr.collidepoint(ent.mouse_tela)
            self.desenhar_campo_texto(ui, vr, chave, "" if valor is None else valor,
                                      lambda t, a=alvo, c=campo: self._set(a, c, t), livre)
            if arrastando:
                pygame.draw.rect(ui.surface, COR["destaque"], vr, 2, border_radius=3)
            if campo in ("imagem", "arquivo") and not valor:
                ui.texto(vr.x + 6, vr.centery, "arraste um arquivo do Project aqui", 11, ancora="midleft",
                         sombra=False, cor=COR["texto2"])
            self._campos_insp.append((vr, alvo, campo, tipo))
        return y + ALT + 2

    def _atualizar_scrub(self, ent):
        s = self._scrub
        if s is None:
            return
        if not ent.mouse_pressionado(1):
            self._scrub = None
            return
        dx = ent.mouse_tela[0] - s["x"]
        if dx and not s["marcado"]:
            self.marcar()
            s["marcado"] = True
        passo = 1.0 if s["campo"] in ("x", "y", "rotacao") or s["tipo"] == "int" else 0.01
        if ent.tecla("left shift"):
            passo *= 10
        v = s["v0"] + dx * passo
        setattr(s["alvo"], s["campo"], int(round(v)) if s["tipo"] == "int" else round(v, 3))

    # --- alterações com desfazer ------------------------------------------------------
    def _set(self, alvo, campo, valor):
        if getattr(alvo, campo, None) == valor:
            return
        self.marcar()
        if campo == "imagem" and hasattr(alvo, "trocar_imagem"):
            alvo.trocar_imagem(valor)
        else:
            setattr(alvo, campo, valor)

    def _set_num(self, alvo, campo, tipo, texto):
        try:
            v = float(texto.replace(",", "."))
        except ValueError:
            self.log(f"'{texto}' não é um número", "aviso")
            return
        self._set(alvo, campo, int(v) if tipo == "int" else v)

    def _set_cor(self, alvo, campo, texto):
        try:
            partes = [float(p) for p in texto.replace(";", ",").split(",") if p.strip()]
        except ValueError:
            self.log("Cor: use 4 números entre 0 e 1, ex.: 1, 0.5, 0.5, 1", "aviso")
            return
        if len(partes) >= 3:
            self._set(alvo, campo, tuple((partes + [1.0])[:4]))

    def _remover_componente(self, comp):
        self.marcar()
        comp.gameobject.remover_componente(comp)

    def _mover_componente(self, comp, d):
        self.marcar()
        lista = comp.gameobject.componentes
        i = lista.index(comp)
        lista[i], lista[i + d] = lista[i + d], lista[i]

    def _resetar(self, comp):
        self.marcar()
        cls = type(comp)
        for campo in comp._todos_campos():
            if campo in comp.__dict__:
                if campo == "imagem" and hasattr(comp, "trocar_imagem"):
                    comp.trocar_imagem(getattr(cls, campo))
                else:
                    delattr(comp, campo)

    def soltar_no_inspector(self, a, mx, my):
        if a.tipo != "asset":
            return
        if self.soltar_na_paleta(a, mx, my):
            return
        for r, alvo, campo, tipo in self._campos_insp:
            if r.collidepoint(mx, my) and tipo == "str":
                self._set(alvo, campo, self.projeto.relativo(a.valor))
                return
        if self.selecionado is not None:          # solto no meio do Inspector: usa no objeto
            self.usar_asset_no_objeto(a.valor, self.selecionado)

    def usar_asset_no_objeto(self, arq: Path, go):
        """Arquivo solto sobre um objeto: imagem vira o sprite dele, script vira componente,
        .agt vira o arquivo do ServicoAgentes."""
        ext = arq.suffix.lower()
        rel = self.projeto.relativo(arq)
        if ext in (".png", ".jpg", ".jpeg"):
            sr = go.obter("SpriteRenderer")
            if sr is None:
                sr = self._adicionar_componente(go, "SpriteRenderer")
            self._set(sr, "imagem", rel)
            self.log(f"'{go.nome}' agora usa a imagem {arq.name}")
        elif ext == ".py":
            classes = self.projeto.scripts.get(str(arq), {}).get("classes", [])
            if not classes:
                self.log(f"{arq.name} não tem nenhuma classe Componente (ou está com erro)", "aviso")
            for nome in classes:
                self._adicionar_componente(go, nome)
        elif ext == ".agt":
            srv = go.obter("ServicoAgentes") or self._adicionar_componente(go, "ServicoAgentes")
            self._set(srv, "arquivo", rel)
        elif ext == ".prefab":
            x, y = go.transform.posicao_mundo
            self.instanciar_prefab(arq, x, y)

    # --- arquivo selecionado -------------------------------------------------------------
    def _insp_asset(self, ui, area, y, livre):
        arq = self.asset_selecionado
        x0 = area.x + 10
        if not arq.exists():
            self.asset_selecionado = None
            return y
        ui.texto(x0, y + 4, arq.name, 15, negrito=True, sombra=False)
        ui.texto(x0, y + 26, self.projeto.relativo(arq), 11, sombra=False, cor=COR["texto2"])
        y += 50
        ext = arq.suffix.lower()
        if ext in (".png", ".jpg"):
            img = ui.imagem(self.projeto.relativo(arq), min(area.w - 40, 220))
            r = img.get_rect(midtop=(area.centerx, y))
            pygame.draw.rect(ui.surface, COR["fundo2"], r.inflate(12, 12))
            ui.surface.blit(img, r)
            y = r.bottom + 14
            w, h = pygame.image.load(str(arq)).get_size()
            ui.texto(x0, y, f"{w} × {h} pixels", 13, sombra=False)
            ui.texto(x0, y + 22, "Arraste para a Scene para criar um objeto,", 12, sombra=False, cor=COR["texto2"])
            ui.texto(x0, y + 38, "ou para o campo 'imagem' de um SpriteRenderer.", 12, sombra=False, cor=COR["texto2"])
            return y + 70
        if ext in (".ogg", ".wav"):
            if botao(ui, (x0, y, 120, 26), "Ouvir", livre, destacado=True):
                self.motor.audio.tocar(str(arq))
            ui.texto(x0, y + 40, "Som: toque pelo script com self.motor.audio.tocar(...)", 12, sombra=False,
                     cor=COR["texto2"])
            ui.texto(x0, y + 58, "ou com o componente FonteAudio.", 12, sombra=False, cor=COR["texto2"])
            return y + 90
        if ext in (".py", ".agt", ".cena", ".prefab", ".json", ".txt", ".mapa"):
            if ext == ".mapa":
                if botao(ui, (x0, y, 160, 26), "Abrir para editar", livre, destacado=True):
                    self.abrir_arquivo_externo(arq)
                ui.texto(x0 + 170, y + 13, "use no componente MapaTiles", 12, ancora="midleft", sombra=False,
                         cor=COR["texto2"])
            if ext == ".py" and botao(ui, (x0, y, 200, 26), "Abrir no editor de código", livre, destacado=True):
                self.abrir_arquivo_externo(arq)
            if ext == ".agt":
                if botao(ui, (x0, y, 150, 26), "Abrir para editar", livre, destacado=True):
                    self.abrir_arquivo_externo(arq)
                if botao(ui, (x0 + 160, y, 150, 26), "Verificar (compilar)", livre):
                    self.verificar_agt(arq)
            if ext == ".cena" and botao(ui, (x0, y, 160, 26), "Abrir cena", livre, destacado=True):
                self.abrir_cena(arq)
            if ext == ".prefab":
                ui.texto(x0, y + 6, "Arraste para a Scene para criar uma cópia.", 12, sombra=False, cor=COR["texto2"])
            y += 36
            try:
                linhas = arq.read_text(encoding="utf-8-sig").splitlines()
            except Exception:
                linhas = ["(não foi possível ler)"]
            caixa = pygame.Rect(area.x + 6, y, area.w - 12, min(len(linhas), 60) * 16 + 10)
            pygame.draw.rect(ui.surface, COR["campo"], caixa)
            for i, l in enumerate(linhas[:60]):
                ui.texto(caixa.x + 6, caixa.y + 5 + i * 16, l.replace("\t", "    ")[:60], 12, sombra=False,
                         cor=(200, 200, 160) if l.strip().startswith(("#", "//")) else COR["texto"])
            return caixa.bottom + 10
        return y

    def verificar_agt(self, arq):
        """Roda o compilador da DSL (léxico, sintático e semântico) e mostra o resultado no Console."""
        from agentdsl.parser import analisar
        from agentdsl.semantica import ACOES_ENGINE, AnalisadorSemantico
        from engine2d.projeto import ACOES_DSL, ALVOS_DSL, PERCEPCOES_DSL
        self.aba_baixo = 1
        fonte = arq.read_text(encoding="utf-8-sig")
        prog, erros = analisar(fonte)
        diags = list(erros)
        if not erros:
            acoes = {**ACOES_ENGINE, **{n: a for n, (a, _) in ACOES_DSL.items()}}
            diags += AnalisadorSemantico(acoes, PERCEPCOES_DSL, alvos=tuple(ALVOS_DSL) or ("jogador",)).analisar(prog)
        for d in diags:
            self.log(d.formatar(None, arq.name), "erro" if d.gravidade == "erro" else "aviso")
        n = sum(d.gravidade == "erro" for d in diags)
        self.log(f"{arq.name}: {'OK' if n == 0 else 'com erros'} — {len(prog.agentes)} agente(s)/modelo(s), "
                 f"{n} erro(s), {len(diags) - n} aviso(s)", "info" if n == 0 else "erro")
