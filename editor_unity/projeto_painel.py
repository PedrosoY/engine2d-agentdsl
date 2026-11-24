"""Painel Project: pastas e arquivos de Assets/ (com miniaturas)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pygame

from .widgets import COR, icone_arquivo, icone_pasta, painel, recortar

CORES_EXT = {".py": (60, 120, 200), ".agt": (150, 90, 200), ".cena": (90, 160, 90), ".prefab": (70, 150, 210),
             ".json": (120, 120, 120), ".txt": (120, 120, 120), ".mapa": (200, 140, 60), ".ogg": (200, 90, 120),
             ".wav": (200, 90, 120), ".ttf": (110, 110, 160)}
NOMES_EXT = {".py": "PY", ".agt": "AGT", ".cena": "CENA", ".prefab": "PREF", ".json": "JSON", ".txt": "TXT",
             ".mapa": "MAPA", ".ogg": "SOM", ".wav": "SOM", ".ttf": "FONTE"}


class ProjetoMixin:
    def _init_projeto(self):
        self.pasta_atual: Path | None = None
        self.rolagem_proj = 0
        self.rolagem_pastas = 0

    def _desenhar_baixo(self, ui):
        area, clicada = painel(ui, self.r_baixo, abas=["Project", f"Console ({self._n_erros()})"],
                               aba_ativa=self.aba_baixo)
        if clicada is not None and self.livre("baixo"):
            self.aba_baixo = clicada
        if self.aba_baixo == 0:
            self._desenhar_projeto(ui, area)
        else:
            self._desenhar_console(ui, area)

    def _desenhar_projeto(self, ui, area):
        ent = self.motor.entrada
        livre = self.livre("baixo")
        raiz = self.projeto.raiz
        if self.pasta_atual is None or not self.pasta_atual.exists():
            self.pasta_atual = raiz / "Assets"
        # --- árvore de pastas (esquerda) ---
        esq = pygame.Rect(area.x, area.y, 190, area.h)
        pygame.draw.rect(ui.surface, COR["fundo2"], esq)
        pastas, itens = self._listar_disco(raiz)
        if livre and ent.roda and esq.collidepoint(ent.mouse_tela):
            self.rolagem_pastas -= ent.roda * 40
        self.rolagem_pastas = max(0, min(self.rolagem_pastas, len(pastas) * 20 + 8 - esq.h))
        with recortar(ui, esq):
            y = esq.y + 4 - self.rolagem_pastas
            for p, nivel in pastas:
                r = pygame.Rect(esq.x, y, esq.w, 20)
                if p == self.pasta_atual:
                    pygame.draw.rect(ui.surface, COR["selecao"], r)
                elif livre and r.collidepoint(ent.mouse_tela):
                    pygame.draw.rect(ui.surface, COR["hover"], r)
                icone_pasta(ui, (r.x + 6 + nivel * 12, r.y + 1, 22, 20))
                ui.texto(r.x + 30 + nivel * 12, r.centery, p.name, 13, ancora="midleft", sombra=False)
                if livre and r.collidepoint(ent.mouse_tela) and esq.collidepoint(ent.mouse_tela) and ent.clicou(1):
                    ent.consumir_clique()
                    self.pasta_atual = p
                    self.rolagem_proj = 0
                y += 20
        # --- caminho e itens da pasta atual (direita) ---
        dir_ = pygame.Rect(esq.right + 1, area.y, area.right - esq.right - 1, area.h)
        rel = self.pasta_atual.relative_to(raiz).parts
        ui.texto(dir_.x + 8, dir_.y + 10, "  ›  ".join(rel), 13, ancora="midleft", sombra=False, cor=COR["texto2"])
        ui.texto(dir_.right - 8, dir_.y + 10, "botão direito: criar · clique duplo: abrir · arraste para a cena",
                 11, ancora="midright", sombra=False, cor=COR["texto2"])
        grade = pygame.Rect(dir_.x, dir_.y + 22, dir_.w, dir_.h - 22)
        tam = 76
        cols = max(1, grade.w // (tam + 8))
        linhas = (len(itens) + cols - 1) // cols
        if livre and ent.roda and grade.collidepoint(ent.mouse_tela):
            self.rolagem_proj = max(0, min(self.rolagem_proj - ent.roda * 30, max(0, linhas * (tam + 22) - grade.h)))
        clicou_item = False
        with recortar(ui, grade):
            for i, p in enumerate(itens):
                cx = grade.x + 8 + (i % cols) * (tam + 8)
                cy = grade.y + 4 + (i // cols) * (tam + 22) - self.rolagem_proj
                r = pygame.Rect(cx, cy, tam, tam + 18)
                if p == self.asset_selecionado:
                    pygame.draw.rect(ui.surface, COR["selecao"], r, border_radius=4)
                elif livre and r.collidepoint(ent.mouse_tela):
                    pygame.draw.rect(ui.surface, COR["hover"], r, border_radius=4)
                icone = pygame.Rect(cx + 6, cy + 4, tam - 12, tam - 12)
                if p.is_dir():
                    icone_pasta(ui, icone)
                elif p.suffix.lower() in (".png", ".jpg"):
                    try:
                        img = ui.imagem(self.projeto.relativo(p), tam - 16)
                        ui.surface.blit(img, img.get_rect(center=icone.center))
                    except Exception:
                        icone_arquivo(ui, icone, "IMG", (150, 150, 150))
                else:
                    icone_arquivo(ui, icone, NOMES_EXT.get(p.suffix.lower(), p.suffix[1:4].upper() or "?"),
                                  CORES_EXT.get(p.suffix.lower(), (120, 120, 120)))
                nome = p.stem if len(p.stem) <= 11 else p.stem[:10] + "…"
                ui.texto(r.centerx, r.bottom - 8, nome, 12, ancora="center", sombra=False)
                if livre and r.collidepoint(ent.mouse_tela):
                    if ent.clicou(1):
                        clicou_item = True
                        ent.consumir_clique()
                        if self.clique_duplo.testar(("asset", str(p))):
                            self.abrir_asset(p)
                        elif p.is_file():
                            # Só seleciona o arquivo ao SOLTAR sem arrastar: assim dá para arrastar a
                            # imagem até o Inspector do objeto selecionado sem ele sumir.
                            self.iniciar_arrasto("asset", p, p.name, ao_clicar=lambda p=p: self._selecionar_asset(p))
                        else:
                            self._selecionar_asset(p)
                    elif ent.clicou(3):
                        clicou_item = True
                        self.asset_selecionado = p
                        self.abrir_popup(*ent.mouse_tela, self._itens_contexto_asset(p), largura=210)
        if livre and not clicou_item and grade.collidepoint(ent.mouse_tela):
            if ent.clicou(3):
                self.abrir_popup(*ent.mouse_tela, self._itens_criar_asset(self.pasta_atual), largura=210)
            elif ent.clicou(1):
                self.asset_selecionado = None
        if self.arrasto is not None and self.arrasto.ativo and self.arrasto.tipo == "objeto" \
                and dir_.collidepoint(ent.mouse_tela):
            pygame.draw.rect(ui.surface, COR["destaque"], dir_, 2)
            ui.texto(dir_.centerx, dir_.bottom - 14, "solte para criar um prefab aqui", 12, ancora="center",
                     sombra=False, cor=COR["destaque"])

    def _selecionar_asset(self, p):
        self.asset_selecionado = p
        self.selecionado = None

    def _listar_disco(self, raiz):
        """Lê as pastas e arquivos no máximo 2x por segundo (ler o disco todo quadro deixa o editor lento)."""
        import time
        chave = str(self.pasta_atual)
        cache = getattr(self, "_cache_disco", None)
        if cache and cache[0] == chave and time.time() - cache[1] < 0.5:
            return cache[2], cache[3]
        pastas = []

        def visitar(p, nivel):
            pastas.append((p, nivel))
            for f in sorted(x for x in p.iterdir() if x.is_dir() and not x.name.startswith((".", "__"))):
                visitar(f, nivel + 1)
        visitar(raiz / "Assets", 0)
        itens = sorted(self.pasta_atual.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        itens = [p for p in itens if not p.name.startswith((".", "__")) and p.suffix != ".pyc"]
        self._cache_disco = (chave, time.time(), pastas, itens)
        return pastas, itens

    def _itens_criar_asset(self, pasta):
        return [("Criar Script", lambda: self.menu_criar_script(pasta), ""),
                ("Criar Agente DSL (.agt)", lambda: self.menu_criar_agente(pasta), ""),
                ("Criar Pasta", lambda: self.menu_criar_pasta(pasta), ""),
                ("Criar Cena", lambda: self._criar_cena_em(pasta), ""), None,
                ("Importar imagens...", self.menu_importar, ""),
                ("Mostrar no Explorer", lambda: self.mostrar_no_explorer(pasta), "")]

    def _itens_contexto_asset(self, p):
        itens = [("Abrir", lambda: self.abrir_asset(p), "")]
        if p.suffix.lower() == ".agt":
            itens.append(("Verificar (compilar)", lambda: self.verificar_agt(p), ""))
        itens += [("Renomear", lambda: self.renomear_asset(p), ""),
                  ("Duplicar", lambda: self.duplicar_asset(p), "") if p.is_file() else ("Duplicar", None, ""),
                  ("Mostrar no Explorer", lambda: self.mostrar_no_explorer(p.parent), ""), None,
                  ("Excluir", lambda: self.excluir_asset(p), "Del")]
        return itens

    def _criar_cena_em(self, pasta):
        def ok(nome):
            arq = pasta / f"{nome.strip()}.cena"
            arq.write_text(json.dumps({"nome": arq.stem, "objetos": [
                {"nome": "Câmera", "transform": {"x": self.projeto.largura / 2, "y": self.projeto.altura / 2},
                 "componentes": [{"tipo": "CameraPrincipal", "campos": {}}]}]}, indent=2), encoding="utf-8")
            self.log(f"Cena criada: {self.projeto.relativo(arq)} (clique duas vezes para abrir)")
        self.pedir_texto("Nome da cena", "Fase1", ok)

    def abrir_asset(self, p: Path):
        ext = p.suffix.lower()
        if p.is_dir():
            self.pasta_atual = p
            self.rolagem_proj = 0
        elif ext == ".cena":
            self.abrir_cena(p)
        elif ext in (".py", ".agt", ".json", ".txt", ".mapa"):
            self.abrir_arquivo_externo(p)
        elif ext == ".prefab":
            self.instanciar_prefab(p, self.cam.x, self.cam.y)
        else:
            self._selecionar_asset(p)

    def renomear_asset(self, p: Path):
        def ok(nome):
            novo = p.with_name(nome.strip() + ("" if p.is_dir() else p.suffix))
            if novo.exists():
                self.log(f"Já existe {novo.name}", "aviso")
                return
            antigo_rel = self.projeto.relativo(p)
            p.rename(novo)
            self.asset_selecionado = novo
            self._atualizar_referencias(antigo_rel, self.projeto.relativo(novo))
            if self.caminho_cena == p:
                self.caminho_cena = novo
        self.pedir_texto("Novo nome", p.stem if p.is_file() else p.name, ok)

    def _atualizar_referencias(self, antigo, novo):
        """Renomeou um arquivo: atualiza campos da cena aberta que apontavam para ele."""
        n = 0
        for go in self.cena.objetos:
            for comp in go.componentes:
                for campo in comp._todos_campos():
                    v = getattr(comp, campo, None)
                    if isinstance(v, str) and v.startswith(antigo):
                        setattr(comp, campo, novo + v[len(antigo):])
                        n += 1
        if n:
            self.modificado = True
            self.log(f"{n} referência(s) na cena atualizada(s) para {novo}")

    def duplicar_asset(self, p: Path):
        k = 1
        while (alvo := p.with_name(f"{p.stem} {k}{p.suffix}")).exists():
            k += 1
        shutil.copy(p, alvo)
        self.asset_selecionado = alvo

    def excluir_asset(self, p: Path):
        def ok():
            lixeira = self.projeto.raiz / "Library" / "Lixeira"
            lixeira.mkdir(parents=True, exist_ok=True)
            destino = lixeira / p.name
            k = 1
            while destino.exists():
                destino = lixeira / f"{p.stem} ({k}){p.suffix}"
                k += 1
            shutil.move(str(p), str(destino))      # vai para Library/Lixeira (dá para recuperar)
            self.asset_selecionado = None
            self.log(f"{p.name} movido para Library/Lixeira")
        self.confirmar(f"Excluir '{p.name}'? (vai para a pasta Library/Lixeira do projeto)", ok)
