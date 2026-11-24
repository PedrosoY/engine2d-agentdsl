"""Montar um projeto inteiro USANDO O EDITOR, com o robô (mouse e teclado simulados).

Cada passo é o que uma pessoa faria: criar pastas pelo botão direito do Project, importar arquivos
(como arrastar do Windows), criar scripts e agentes pelo menu, arrastar imagens para a Scene,
renomear com F2, preencher o Inspector, adicionar componentes pelo botão, arrastar objetos para
o Project (prefab) e salvar a cena. Usado por montar_navinha.py e montar_plataforma.py.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path


class Montador:
    def __init__(self, destino: Path, nome: str, fonte: Path, largura=1280, altura=720, ver=False):
        from engine2d.projeto import Projeto
        from .robo import RoboEditor
        self.fonte = Path(fonte)
        self.destino = Path(destino)
        if self.destino.exists():
            shutil.rmtree(self.destino)
        Projeto.criar(self.destino, nome)               # o mesmo que "Novo projeto..." no Hub
        self.r = RoboEditor(self.destino, tamanho=(1600, 900), visivel=ver)
        self.app = self.r.app
        self.configurar(largura=largura, altura=altura)

    # --- Configurações do projeto (Editar → Configurações do projeto...) --------------------------------
    def configurar(self, **campos):
        """Preenche campos das Configurações do projeto no Inspector (listas como "a, b, c")."""
        self.r.menu("Editar", "Configurações do projeto...")
        assert self.app.asset_selecionado == "configuracoes"
        for chave, valor in campos.items():
            if isinstance(valor, (list, tuple)):
                valor = ", ".join(str(v) for v in valor)
            self.r.preencher(chave, valor, "Projeto")
        self.app.asset_selecionado = None

    # --- painel Project ----------------------------------------------------------------------------
    def puxar_divisoria(self, quanto=110):
        """Arrasta a borda entre a Scene e o Project para cima (o Project fica mais alto)."""
        a = self.app.r_baixo
        self.r.arrastar((a.centerx, a.top), (a.centerx, a.top - quanto))
        assert self.app.r_baixo.top < a.top - quanto + 10, (a, self.app.r_baixo)

    def abrir_pasta(self, *caminho):
        for nome in caminho:
            self.r.clicar(*self.r.pasta_projeto(nome))
        assert self.app.pasta_atual.name == caminho[-1], self.app.pasta_atual

    def criar_pasta(self, nome):
        self.menu_grade("Criar Pasta")
        self.r.responder(nome)
        self.app._cache_disco = None

    def menu_grade(self, item):
        """Botão direito num lugar vazio da grade de arquivos do Project."""
        a = self.app.r_baixo
        self.r.clicar(a.right - 40, a.bottom - 20, botao=3)
        self.r.clicar(*self.r.item_popup(item))

    def importar(self, arquivos):
        for arq in arquivos:
            self.app.importar_arquivo(Path(arq))      # = arrastar o arquivo do Windows para o Project
        self.app._cache_disco = None
        self.r.quadros(2)

    def importar_em(self, caminho_pasta, arquivos):
        """Cria as pastas que faltam (botão direito → Criar Pasta) e importa os arquivos nela."""
        partes = caminho_pasta.split("/")
        for i, nome in enumerate(partes):
            if not (self.app.projeto.raiz / "Assets" / Path(*partes[:i + 1])).exists():
                if i == 0:
                    self.r.clicar(*self.r.pasta_projeto("Assets"))
                else:
                    self.abrir_pasta(*partes[:i])
                self.criar_pasta(nome)
        self.abrir_pasta(*partes)
        self.importar(arquivos)

    def esperar_scripts(self):
        """O editor confere os scripts uma vez por segundo."""
        t = time.time()
        while time.time() - t < 1.2:
            self.r.quadros(1)
        erros = list(self.app.projeto.erros_scripts)
        assert not erros, erros

    def criar_script(self, nome):
        """Project → botão direito → Criar Script; o código é o que se digitaria no VS Code."""
        self.menu_grade("Criar Script")
        self.r.responder(nome)
        arq = self.app.projeto.raiz / "Assets" / "Scripts" / f"{nome}.py"
        assert arq.exists(), f"o editor não criou {arq}"
        arq.write_text((self.fonte / "Scripts" / f"{nome}.py").read_text(encoding="utf-8"), encoding="utf-8")
        os.utime(arq, (time.time() + 1, time.time() + 1))

    def criar_agente(self, nome):
        """Project → botão direito → Criar Agente DSL; depois Verificar (compilar) tem que dar OK."""
        self.abrir_pasta("Agentes")
        self.menu_grade("Criar Agente DSL (.agt)")
        self.r.responder(nome)
        agt = self.app.projeto.raiz / "Assets/Agentes" / f"{nome}.agt"
        agt.write_text((self.fonte / "Agentes" / f"{nome}.agt").read_text(encoding="utf-8"), encoding="utf-8")
        self.app._cache_disco = None
        self.r.clicar(*self.r.item_projeto(f"{nome}.agt"), botao=3)
        self.r.clicar(*self.r.item_popup("Verificar (compilar)"))
        ultima = self.r.console(1)[0]
        assert "OK" in ultima, self.r.console(15)
        return ultima

    # --- Scene / Hierarchy / Inspector ------------------------------------------------------------------
    def sprite(self, imagem, x, y, nome, *pasta):
        """Arrasta a imagem do Project para a Scene, no ponto (x, y) do mundo, e renomeia (F2)."""
        self.abrir_pasta(*pasta)
        self.r.arrastar(self.r.item_projeto(imagem), self.r.mundo(x, y))
        go = self.app.selecionado
        assert go is not None and go.obter("SpriteRenderer").imagem.endswith(imagem), go
        self.renomear(nome)
        return go

    def vazio(self, nome, x=None, y=None):
        self.r.menu("GameObject", "Criar vazio")
        go = self.app.selecionado
        self.renomear(nome)
        if x is not None:
            self.campos("Transform", x=x, y=y)
        return go

    def filho(self, pai, nome, tipo="Criar filho vazio"):
        self.r.clicar(*self.r.linha_hierarquia(pai), botao=3)
        self.r.clicar(*self.r.item_popup(tipo))
        self.renomear(nome)
        return self.app.selecionado

    def renomear(self, nome):
        self.r.tecla("f2")
        self.r.responder(nome)
        assert self.app.selecionado.nome == nome, self.app.selecionado

    def selecionar(self, nome):
        self.r.clicar(*self.r.linha_hierarquia(nome))
        assert self.app.selecionado is not None and self.app.selecionado.nome == nome

    def comp(self, nome, **campos):
        """Adiciona um componente pelo botão e preenche os campos."""
        if self.app.selecionado.obter(nome) is None:
            self.r.adicionar_componente(nome)
        assert self.app.selecionado.obter(nome) is not None, f"{nome} não foi adicionado"
        self.campos(nome, **campos)

    def campos(self, componente, **campos):
        go = self.app.selecionado
        alvo = go.transform if componente == "Transform" else (go if componente == "GameObject" else go.obter(componente))
        for campo, valor in campos.items():
            if isinstance(valor, bool):
                self.r.marcar(campo, valor, componente)
            else:
                if isinstance(valor, tuple):
                    valor = ", ".join(f"{v:g}" for v in valor)
                self.r.preencher(campo, valor, componente)
            atual = getattr(alvo, campo)
            esperado = valor
            if isinstance(atual, tuple):
                atual = ", ".join(f"{v:g}" for v in atual)
            elif isinstance(atual, float):
                esperado = float(str(valor).replace(",", "."))
            elif isinstance(atual, int) and not isinstance(atual, bool):
                esperado = int(float(valor))
            assert atual == esperado or (isinstance(valor, bool) and bool(atual) == valor), \
                f"{componente}.{campo} = {atual!r}, esperado {valor!r}"

    def prefab(self, nome, tirar_da_cena=True):
        """Arrasta o objeto da Hierarchy para a pasta Prefabs (vira prefab) e tira da cena (Del)."""
        self.abrir_pasta("Prefabs")
        a = self.app.r_baixo
        self.r.arrastar(self.r.linha_hierarquia(nome), (a.centerx + 100, a.centery + 40))
        assert (self.app.projeto.raiz / "Assets/Prefabs" / f"{nome}.prefab").exists(), f"prefab {nome}"
        if tirar_da_cena:
            self.selecionar(nome)
            self.r.mover(*self.r.centro("scene"))
            self.r.tecla("delete")
            assert self.app.cena.encontrar(nome) is None

    def salvar_cena_como(self, nome):
        if self.app.caminho_cena is None:
            self.r.tecla("s", mods=("ctrl",))             # cena nova: Ctrl+S pergunta o nome
        else:
            self.r.menu("Arquivo", "Salvar cena como...")
        self.r.responder(nome)
        assert self.app.caminho_cena is not None and self.app.caminho_cena.stem == nome
        assert not self.app.modificado

    def apagar_asset(self, nome):
        """Seleciona o arquivo no Project, Del e confirma (vai para Library/Lixeira)."""
        self.r.clicar(*self.r.item_projeto(nome))
        self.r.tecla("delete")
        assert self.app.dialogo is not None
        self.r.tecla("return")

    def erros_no_console(self):
        return [l for l in self.r.console(800) if l.startswith("[erro]")]

    def fechar(self):
        self.r.fechar()
