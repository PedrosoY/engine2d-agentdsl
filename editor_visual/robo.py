"""Robô do editor: usa o editor com mouse e teclado simulados (eventos do SDL de verdade).

Serve para testes automáticos e para montar cenas "à mão" sem ninguém no computador:

    robo = RoboEditor("MeuJogo")             # janela escondida, 1600x900
    robo.clicar(*robo.centro("hier"))
    robo.arrastar(robo.item_projeto("nave.png"), robo.centro("scene"))
    robo.capturar("tela.png")

Cada ação posta os eventos no SDL e roda alguns quadros do editor, como se uma pessoa
estivesse usando: o editor não sabe que é um robô.
"""
from __future__ import annotations

from pathlib import Path

import pygame

from .app import EditorApp

MODS = {"ctrl": pygame.KMOD_LCTRL, "shift": pygame.KMOD_LSHIFT, "alt": pygame.KMOD_LALT}
TECLA_MOD = {"ctrl": "left ctrl", "shift": "left shift", "alt": "left alt"}


class RoboEditor:
    def __init__(self, projeto=None, tamanho=(1600, 900), visivel=False):
        self.app = EditorApp(str(projeto) if projeto else None, visivel=visivel, tamanho=tamanho)
        self.app.layout()
        self.mouse = (5, 5)
        self.quadros(3)

    # --- tempo ----------------------------------------------------------------------
    def quadros(self, n=1):
        for _ in range(n):
            self.app.passo()

    def esperar_clique_duplo(self):
        """O editor só conta clique duplo em menos de 0,4 s; isto garante dois cliques separados."""
        self.app.clique_duplo.ultimo = (None, 0.0)

    # --- mouse ---------------------------------------------------------------------------
    def mover(self, x, y, passos=1, segurando=()):
        x0, y0 = self.mouse
        for i in range(1, passos + 1):
            px, py = round(x0 + (x - x0) * i / passos), round(y0 + (y - y0) * i / passos)
            pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(px, py), rel=(0, 0),
                                                 buttons=tuple(int(b in segurando) for b in (1, 2, 3))))
            self.mouse = (px, py)
            self.quadros(1)

    def apertar(self, botao=1):
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=self.mouse, button=botao))
        self.quadros(1)

    def soltar(self, botao=1):
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=self.mouse, button=botao))
        self.quadros(2)

    def clicar(self, x, y, botao=1, mods=()):
        for m in mods:
            self._tecla_evento(pygame.KEYDOWN, TECLA_MOD[m])
        self.mover(x, y)
        self.apertar(botao)
        self.soltar(botao)
        for m in mods:
            self._tecla_evento(pygame.KEYUP, TECLA_MOD[m])
        self.quadros(1)

    def clique_duplo(self, x, y):
        self.esperar_clique_duplo()
        self.mover(x, y)
        self.apertar()
        self.soltar()
        self.apertar()
        self.soltar()

    def arrastar(self, de, para, botao=1, passos=8, mods=()):
        for m in mods:
            self._tecla_evento(pygame.KEYDOWN, TECLA_MOD[m])
        self.mover(*de)
        self.apertar(botao)
        self.mover(*para, passos=passos, segurando=(botao,))
        self.soltar(botao)
        for m in mods:
            self._tecla_evento(pygame.KEYUP, TECLA_MOD[m])

    def rolar(self, x, y, quanto):
        self.mover(x, y)
        pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=quanto, flipped=False))
        self.quadros(1)

    # --- teclado ----------------------------------------------------------------------------
    def _tecla_evento(self, tipo, nome, mods=0, unicode=""):
        pygame.event.post(pygame.event.Event(tipo, key=pygame.key.key_code(nome), mod=mods, unicode=unicode,
                                             scancode=0))

    def tecla(self, nome, mods=()):
        """Aperta e solta uma tecla (nomes do pygame: 'return', 'delete', 's'...), com Ctrl/Shift/Alt."""
        m = 0
        for x in mods:
            m |= MODS[x]
            self._tecla_evento(pygame.KEYDOWN, TECLA_MOD[x])
        self._tecla_evento(pygame.KEYDOWN, nome, m, nome if len(nome) == 1 and not mods else "")
        self.quadros(1)
        self._tecla_evento(pygame.KEYUP, nome, m)
        for x in mods:
            self._tecla_evento(pygame.KEYUP, TECLA_MOD[x])
        self.quadros(1)

    def digitar(self, texto):
        pygame.event.post(pygame.event.Event(pygame.TEXTINPUT, text=texto))
        self.quadros(1)

    # --- onde clicar ----------------------------------------------------------------------
    def centro(self, painel):
        r = getattr(self.app, "r_" + painel)
        return r.centerx, r.centery

    def mundo(self, x, y):
        """Ponto da tela onde aparece o ponto (x, y) do mundo na Scene."""
        px, py = self.app.mundo_para_tela(x, y)
        return round(px), round(py)

    def item_projeto(self, nome):
        """Centro do ícone de um arquivo/pasta na grade do Project (pasta aberta)."""
        self.app.aba_baixo = 0
        self.quadros(1)
        area = self.app.r_baixo
        grade_x, grade_y = area.x + 1 + 191, area.y + 23 + 22
        largura = area.right - 1 - grade_x
        self.app._cache_disco = None             # arquivos criados agora aparecem na hora
        _, itens = self.app._listar_disco(self.app.projeto.raiz)
        tam = 76
        cols = max(1, largura // (tam + 8))
        for i, p in enumerate(itens):
            if p.name == nome or p.stem == nome:
                cx = grade_x + 8 + (i % cols) * (tam + 8) + tam // 2
                cy = grade_y + 4 + (i // cols) * (tam + 22) - self.app.rolagem_proj + (tam + 18) // 2
                return cx, cy
        raise KeyError(f"'{nome}' não está na pasta {self.app.pasta_atual}")

    def pasta_projeto(self, nome):
        """Centro de uma pasta na árvore da esquerda do Project."""
        self.app.aba_baixo = 0
        self.quadros(1)
        area = self.app.r_baixo
        self.app._cache_disco = None
        pastas, _ = self.app._listar_disco(self.app.projeto.raiz)
        topo, fundo = area.y + 23, area.bottom - 1
        for i, (p, _) in enumerate(pastas):
            if p.name == nome:
                for _ in range(30):              # rola a árvore até a pasta aparecer
                    y = topo + 4 + i * 20 + 10 - self.app.rolagem_pastas
                    if topo + 10 <= y <= fundo - 10:
                        return area.x + 1 + 60, y
                    self.rolar(area.x + 60, (topo + fundo) // 2, 1 if y < topo + 10 else -1)
        raise KeyError(nome)

    def linha_hierarquia(self, nome):
        self.quadros(1)
        for r, go in self.app._linhas_hier:
            if go.nome == nome:
                return r.x + 60, r.centery
        raise KeyError(f"'{nome}' não aparece na Hierarchy")

    def campo_inspector(self, campo, componente=None, rolar=True):
        """Centro da caixa de valor de um campo do Inspector. Rola o Inspector até o campo aparecer.
        ``componente``: nome da classe (SpriteRenderer, Transform, GameObject para nome/tag)."""
        area = self.app.r_insp
        for _ in range(40):
            self.quadros(1)
            achado = None
            for r, alvo, nome, _tipo in self.app._campos_insp:
                if nome == campo and (componente is None or type(alvo).__name__ == componente):
                    achado = r
                    break
            if achado is None:
                if not rolar:
                    break
                # pode estar abaixo da área visível sem ter sido desenhado: rola um pouco para baixo
                antes = self.app.rolagem_insp
                self.rolar(area.centerx, area.centery, -2)
                if self.app.rolagem_insp == antes:
                    break
                continue
            if achado.top < area.top + 26:
                self.rolar(area.centerx, area.centery, 1)
            elif achado.bottom > area.bottom - 4:
                self.rolar(area.centerx, area.centery, -1)
            else:
                return achado.centerx, achado.centery
        raise KeyError(f"campo '{campo}' ({componente or 'qualquer'}) não está no Inspector")

    def tipo_campo(self, campo, componente=None):
        self.campo_inspector(campo, componente)
        for _, alvo, nome, tipo in self.app._campos_insp:
            if nome == campo and (componente is None or type(alvo).__name__ == componente):
                return tipo
        return None

    def escolher(self, campo, valor, componente=None):
        """Campo de lista (tag, camada de desenho): clica na caixa e escolhe o item do menu."""
        self.clicar(*self.campo_inspector(campo, componente))
        self.clicar(*self.item_popup(valor if valor else "(nenhuma)"))

    def preencher(self, campo, valor, componente=None):
        """Clica no campo do Inspector, digita o valor e confirma com Enter (como uma pessoa).
        Campos de lista (tag, camada de desenho) são escolhidos no menu."""
        tipo = self.tipo_campo(campo, componente) or ""
        if tipo in ("escolha", "camada_desenho") or tipo.startswith("escolha:"):
            self.escolher(campo, valor, componente)
            return
        self.clicar(*self.campo_inspector(campo, componente))
        assert self.app.campo is not None, f"o campo '{campo}' não entrou em edição"
        self.tecla("backspace")
        self.digitar(str(valor))
        self.tecla("return")

    def marcar(self, campo, valor, componente=None):
        """Liga/desliga uma caixinha (bool) do Inspector."""
        x, y = self.campo_inspector(campo, componente)
        for r, alvo, nome, _ in self.app._campos_insp:
            if nome == campo and (componente is None or type(alvo).__name__ == componente):
                atual = getattr(alvo, campo, None)
                if atual is None or bool(atual) != bool(valor):    # caixinha sem campo (ex.: paleta): clica
                    self.clicar(r.x + 8, r.centery)
                return

    def adicionar_componente(self, nome):
        """Botão "Adicionar Componente" do Inspector → escolhe ``nome`` no menu."""
        area = self.app.r_insp
        for _ in range(40):
            self.quadros(1)
            r = getattr(self.app, "r_adicionar_componente", None)
            if r is not None and area.top + 26 <= r.top and r.bottom <= area.bottom - 4:
                break
            self.rolar(area.centerx, area.centery, -2 if r is None or r.bottom > area.bottom else 1)
        self.clicar(*r.center)
        self.clicar(*self.item_popup(nome))

    def item_popup(self, rotulo):
        """Centro de um item do menu aberto (comparando sem os espaços do começo)."""
        p = self.app.popup
        if p is None:
            raise RuntimeError("nenhum menu aberto")
        y = p.rect.y + 3
        for it in p.itens:
            if it is None:
                y += 8
                continue
            if it[0].strip() == rotulo:
                return p.rect.x + 40, y + 11
            y += 22
        raise KeyError(f"'{rotulo}' não está no menu: {[i[0] for i in p.itens if i]}")

    def menu(self, *caminho):
        """Abre um menu do topo e escolhe um item: menu("GameObject", "Sprite")."""
        x = 6
        for nome in self.app._menus():
            w = self.app.ui.fonte(13).size(nome)[0] + 18
            if nome == caminho[0]:
                self.clicar(x + w // 2, 12)
                break
            x += w
        for rotulo in caminho[1:]:
            self.clicar(*self.item_popup(rotulo))

    def responder(self, texto):
        """Preenche o diálogo de texto aberto e aperta Enter."""
        assert self.app.dialogo is not None, "nenhum diálogo aberto"
        self.tecla("a", mods=("ctrl",))
        self.tecla("backspace")
        self.digitar(texto)
        self.tecla("return")

    def capturar(self, caminho):
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.app.motor.capturar_tela(str(caminho))
        self.quadros(1)
        return Path(caminho)

    def console(self, ultimas=10):
        return [f"[{tipo}] {texto}" for _, texto, tipo in self.app.console[-ultimas:]]

    def fechar(self):
        self.app.parar() if self.app.processo else None
        if self.app.projeto is not None:
            self.app.projeto.descarregar()
        self.app.motor.encerrar()
