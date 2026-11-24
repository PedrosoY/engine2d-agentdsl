"""Editor da Engine2D.

Layout:
  ┌ menu: Arquivo  Editar  GameObject  Assets  Ajuda ─────────────────────────────┐
  │ ferramentas: Mover(W) Girar(E) Escalar(R)        ► Play         Cena: X *     │
  ├ Hierarchy ┬──────────────── Scene ─────────────────────────┬ Inspector ─────────┤
  │           │                                                │                    │
  ├ Project | Console ─────────────────────────────────────────┤                    │
  └────────────────────────────────────────────────────────────┴────────────────────┘
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pygame

from engine2d.cena import objeto_de_dict, objeto_para_dict
from engine2d.objeto import REGISTRO_COMPONENTES

from .console import ConsoleMixin
from .hierarquia import HierarquiaMixin
from .inspector import InspectorMixin
from .pincel_mapa import PincelMapaMixin
from .projeto_painel import ProjetoMixin
from .scene_view import SceneMixin
from .widgets import COR, Arrasto, Campo, CliqueDuplo, Popup, botao

RAIZ_ENGINE = Path(__file__).resolve().parent.parent
RECENTES = Path.home() / ".engine2d_projetos_recentes.json"


class EditorApp(HierarquiaMixin, SceneMixin, InspectorMixin, PincelMapaMixin, ProjetoMixin, ConsoleMixin):
    def __init__(self, raiz_projeto=None, visivel=True, tamanho=None):
        import agentdsl.componente  # noqa: F401 (registra os componentes da DSL)
        from engine2d import Motor
        pygame.init()
        if tamanho:
            w, h = tamanho
        else:
            info = pygame.display.Info()
            w = max(1000, min(1680, info.current_w - 60))
            h = max(640, min(960, info.current_h - 110))
        # Abre maximizado (padrão) e pode ser redimensionado arrastando a borda.
        maximizar = os.environ.get("ENGINE2D_EDITOR_JANELA") != "normal" and visivel and not tamanho
        self.motor = Motor(w, h, "Engine2D Editor", vsync=visivel, editor=False, redimensionavel=True,
                           maximizada=maximizar, visivel=visivel)
        self.ui = self.motor.ui
        self.W, self.H = self.motor.largura, self.motor.altura
        self.projeto = None
        self.cena = None
        self.caminho_cena: Path | None = None
        self.modificado = False
        self.selecionado = None
        self.asset_selecionado: Path | None = None
        self.popup: Popup | None = None
        self.campo: Campo | None = None
        self.dialogo = None
        self.arrasto: Arrasto | None = None
        self.clique_duplo = CliqueDuplo()
        self.desfazer_pilha: list = []
        self.refazer_pilha: list = []
        self.console: list[tuple[str, str]] = []
        self.aba_baixo = 0
        self.processo = None
        self.fila_saida: queue.Queue = queue.Queue()
        self._ultimo_check_scripts = 0.0
        self.rodando = True
        self.alvo_mouse = None
        self._init_hierarquia()
        self._init_scene()
        self._init_inspector()
        self._init_projeto()
        self._init_pincel()
        self.layout()
        if raiz_projeto:
            self.abrir_projeto(raiz_projeto)

    # =========================================================================
    # Layout
    # =========================================================================
    def layout(self):
        """Calcula os retângulos dos painéis. As larguras/alturas podem ser mudadas arrastando
        as bordas entre os painéis; o padrão é proporcional ao tamanho da janela."""
        W, H = self.W, self.H
        topo = 24 + 34
        if getattr(self, "tam_paineis", None) is None:
            self.tam_paineis = {"hier": int(W * 0.18), "insp": int(W * 0.24), "baixo": int(H * 0.30)}
        tp = self.tam_paineis
        tp["hier"] = max(150, min(tp["hier"], W // 3))
        tp["insp"] = max(240, min(tp["insp"], W // 2.5))
        tp["baixo"] = max(120, min(tp["baixo"], int(H * 0.6)))
        lw, rw, bh = tp["hier"], int(tp["insp"]), tp["baixo"]
        self.r_menu = pygame.Rect(0, 0, W, 24)
        self.r_ferr = pygame.Rect(0, 24, W, 34)
        self.r_hier = pygame.Rect(0, topo, lw, H - topo - bh)
        self.r_scene = pygame.Rect(lw, topo, W - lw - rw, H - topo - bh)
        self.r_insp = pygame.Rect(W - rw, topo, rw, H - topo)
        self.r_baixo = pygame.Rect(0, H - bh, W - rw, bh)

    def _divisorias(self):
        """Bordas arrastáveis entre os painéis (Hierarchy | Scene | Inspector e Scene / Project)."""
        ent = self.motor.entrada
        mx, my = ent.mouse_tela
        d = getattr(self, "_divisoria", None)
        if d is None:
            sob = None
            if abs(mx - self.r_hier.right) <= 4 and self.r_hier.top < my < self.r_hier.bottom:
                sob = "hier"
            elif abs(mx - self.r_insp.left) <= 4 and self.r_insp.top < my:
                sob = "insp"
            elif abs(my - self.r_baixo.top) <= 4 and mx < self.r_insp.left:
                sob = "baixo"
            if sob:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZENS if sob == "baixo" else pygame.SYSTEM_CURSOR_SIZEWE)
                self.alvo_mouse = "divisoria"        # os painéis não recebem esse clique
                if ent.clicou(1):
                    ent.consumir_clique()
                    self._divisoria = sob
            return
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZENS if d == "baixo" else pygame.SYSTEM_CURSOR_SIZEWE)
        self.alvo_mouse = "divisoria"
        if not ent.mouse_pressionado(1):
            self._divisoria = None
            return
        if d == "hier":
            self.tam_paineis["hier"] = mx
        elif d == "insp":
            self.tam_paineis["insp"] = self.W - mx
        else:
            self.tam_paineis["baixo"] = self.H - my
        self.layout()

    def _alvo(self):
        mx, my = self.motor.entrada.mouse_tela
        if self.dialogo:
            return "dialogo"
        if self.popup and self.popup.rect.collidepoint(mx, my):
            return "popup"
        for nome in ("menu", "ferr", "hier", "scene", "insp", "baixo"):
            if getattr(self, "r_" + nome).collidepoint(mx, my):
                return nome
        return None

    def livre(self, painel):
        """O painel pode reagir ao mouse? (sem popup/diálogo por cima, mouse sobre ele)."""
        return self.alvo_mouse == painel and (self.arrasto is None or not self.arrasto.ativo)

    # =========================================================================
    # Projeto e cenas
    # =========================================================================
    def abrir_projeto(self, raiz):
        from engine2d.projeto import Projeto
        raiz = Path(raiz).resolve()
        if not (raiz / "projeto.json").exists():
            self.log(f"'{raiz}' não é um projeto (falta projeto.json)", "erro")
            return
        if self.projeto is not None:
            self.projeto.descarregar()
        self.projeto = Projeto(raiz)
        os.chdir(raiz)
        self.motor.texturas.pasta_base = raiz
        self.motor.configurar_projeto(self.projeto.configuracoes())
        self.ui._imagens.clear()
        self.motor.texturas._cache.clear()
        pygame.display.set_caption(f"Engine2D Editor — {self.projeto.nome}")
        self.pasta_atual = raiz / "Assets"
        self.recarregar_scripts(forcar=True)
        self.log(f"Projeto aberto: {raiz}")
        cena = raiz / self.projeto.cena_inicial
        if cena.exists():
            self.abrir_cena(cena)
        else:
            self.nova_cena()
        self._lembrar_recente(raiz)

    def _lembrar_recente(self, raiz):
        if os.environ.get("ENGINE2D_SEM_RECENTES") == "1":   # testes não poluem a lista
            return
        try:
            lista = json.loads(RECENTES.read_text(encoding="utf-8")) if RECENTES.exists() else []
        except Exception:
            lista = []
        lista = [str(raiz)] + [p for p in lista if p != str(raiz)]
        try:
            RECENTES.write_text(json.dumps(lista[:8], indent=1), encoding="utf-8")
        except OSError:
            pass

    def _nova_cena_vazia(self, nome):
        from engine2d import Cena
        c = Cena(nome, modo_edicao=True)
        c.motor = self.motor
        return c

    def abrir_cena(self, caminho):
        if not self._pode_descartar(lambda: self.abrir_cena(caminho)):
            return
        caminho = Path(caminho)
        cena = self._nova_cena_vazia(caminho.stem)
        try:
            cena.carregar(caminho)
        except Exception as e:
            self.log(f"Erro ao abrir {caminho.name}: {e}", "erro")
            return
        self.cena = cena
        self.caminho_cena = caminho
        self.modificado = False
        self.selecionado = None
        self.desfazer_pilha.clear()
        self.refazer_pilha.clear()
        self._enquadrar_camera_inicial()
        self.log(f"Cena aberta: {self.projeto.relativo(caminho)}")

    def nova_cena(self):
        if not self._pode_descartar(self.nova_cena):
            return
        from engine2d import CameraPrincipal
        self.cena = self._nova_cena_vazia("Nova cena")
        self.cena.criar("Câmera", self.projeto.largura / 2 if self.projeto else 640,
                        self.projeto.altura / 2 if self.projeto else 360, componentes=[CameraPrincipal()])
        self.caminho_cena = None
        self.modificado = False
        self.selecionado = None
        self.desfazer_pilha.clear()
        self._enquadrar_camera_inicial()

    def salvar_cena(self, como=False):
        if self.projeto is None or self.cena is None:
            return
        if self.caminho_cena is None or como:
            nome = "Nova cena" if self.caminho_cena is None else self.caminho_cena.stem + " cópia"

            def ok(texto):
                arq = self.projeto.raiz / "Assets" / "Cenas" / (texto.strip() + ".cena")
                arq.parent.mkdir(parents=True, exist_ok=True)
                self.caminho_cena = arq
                self.cena.nome = arq.stem
                self.salvar_cena()
            self.pedir_texto("Salvar cena como (em Assets/Cenas)", nome, ok)
            return
        self.cena.salvar(self.caminho_cena)
        self.modificado = False
        self.log(f"Cena salva: {self.projeto.relativo(self.caminho_cena)}")

    def _pode_descartar(self, continuar) -> bool:
        if not self.modificado or self.cena is None:
            return True

        def descartar():
            self.modificado = False
            continuar()
        self.confirmar("A cena atual tem alterações não salvas. Descartar?", descartar)
        return False

    # =========================================================================
    # Desfazer / refazer (fotografias da cena inteira)
    # =========================================================================
    def marcar(self):
        """Chame ANTES de mudar a cena: guarda o estado para o Ctrl+Z."""
        if self.cena is None:
            return
        self.desfazer_pilha.append((self.cena.para_dict(), self._caminho_selecao()))
        del self.desfazer_pilha[:-60]
        self.refazer_pilha.clear()
        self.modificado = True

    def _caminho_selecao(self):
        go, partes = self.selecionado, []
        while go is not None:
            partes.append(go.nome)
            go = go.pai
        return list(reversed(partes))

    def _selecionar_por_caminho(self, partes):
        self.selecionado = None
        if not partes:
            return
        candidatos = self.cena.raizes()
        go = None
        for nome in partes:
            go = next((g for g in candidatos if g.nome == nome), None)
            if go is None:
                return
            candidatos = go.filhos
        self.selecionado = go

    def desfazer(self, refazer=False):
        de, para = (self.refazer_pilha, self.desfazer_pilha) if refazer else (self.desfazer_pilha, self.refazer_pilha)
        if not de:
            return
        foto = de.pop()
        if foto[0] == "mapa":                     # pintura no MapaTiles (o arquivo .mapa volta junto)
            self.desfazer_mapa(foto, para)
            return
        para.append((self.cena.para_dict(), self._caminho_selecao()))
        dados, sel = foto
        self.cena.carregar_dict(dados)
        self.cena.iniciar_pendentes()
        self._selecionar_por_caminho(sel)
        self.modificado = True

    # =========================================================================
    # Operações com objetos
    # =========================================================================
    def criar_objeto(self, tipo="vazio", pai=None, x=None, y=None, imagem=None):
        from engine2d import CameraPrincipal, Colisor, SpriteRenderer
        if self.cena is None:
            return None
        self.marcar()
        if x is None:
            x, y = self.cam.x, self.cam.y
        if pai is not None:
            x, y = 0, 0
        nomes = {"vazio": "GameObject", "sprite": "Sprite", "camera": "Câmera", "texto": "Texto"}
        comps = []
        if tipo == "sprite":
            comps = [SpriteRenderer(imagem=imagem or self._imagem_padrao())]
            if imagem and not imagem.startswith("embutido:"):
                nomes["sprite"] = Path(imagem).stem
        elif tipo == "camera":
            comps = [CameraPrincipal()]
        elif tipo == "texto":
            comps = [REGISTRO_COMPONENTES["TextoUI"]()]
        elif tipo == "fisica":
            comps = [SpriteRenderer(imagem=imagem or self._imagem_padrao()),
                     REGISTRO_COMPONENTES["CorpoRigido"](), Colisor(raio=20)]
        go = self.cena.criar(self._nome_unico(nomes.get(tipo, "GameObject")), x, y, componentes=comps, pai=pai)
        self.cena.iniciar_pendentes()
        self.selecionado = go
        return go

    FORMAS_2D = [("Quadrado", "quadrado"), ("Círculo", "circulo"), ("Triângulo", "triangulo"),
                 ("Cápsula", "capsula"), ("Losango", "losango"), ("Hexágono", "hexagono"),
                 ("Hexágono (ponta)", "hexagono_ponta"), ("Quadrado arredondado", "quadrado_arredondado")]

    def _itens_formas(self, pai=None):
        """Sprites 2D padrão (brancos, para tingir no campo cor)."""
        return [(f"2D: {rot}", (lambda f=forma, r=rot: self.criar_forma(f, r, pai)), "") for rot, forma in self.FORMAS_2D]

    def criar_forma(self, forma, rotulo, pai=None):
        go = self.criar_objeto("sprite", pai=pai, imagem=f"embutido:{forma}")
        if go is not None:
            go.nome = self._nome_unico(rotulo)
        return go

    def criar_mapa(self):
        """Objeto com MapaTiles vazio: arraste imagens para a paleta do Inspector e pinte na Scene."""
        from engine2d import MapaTiles
        go = self.criar_objeto("vazio")
        if go is None:
            return None
        go.nome = self._nome_unico("Mapa")
        go.adicionar(MapaTiles())
        self.cena.iniciar_pendentes()
        self.log("Mapa criado: arraste imagens do Project para a Paleta (no Inspector) e pinte na Scene")
        return go

    def abrir_configuracoes(self):
        """Mostra as Configurações do projeto no Inspector."""
        self.selecionado = None
        self.asset_selecionado = "configuracoes"

    def _imagem_padrao(self):
        return "embutido:quadrado"

    def _nome_unico(self, base):
        nomes = {g.nome for g in self.cena.objetos}
        if base not in nomes:
            return base
        k = 1
        while f"{base} ({k})" in nomes:
            k += 1
        return f"{base} ({k})"

    def duplicar(self):
        go = self.selecionado
        if go is None:
            return
        self.marcar()
        novo = objeto_de_dict(objeto_para_dict(go))
        novo.nome = self._nome_unico(go.nome)
        novo.transform.x += 20
        novo.transform.y -= 20
        if go.pai:
            novo.transform.definir_pai(go.pai.transform)
        self.cena.adicionar(novo)
        self.cena.iniciar_pendentes()
        self.selecionado = novo

    def excluir(self):
        if self.selecionado is None:
            return
        self.marcar()
        self.cena._destruir_agora(self.selecionado)
        self.selecionado = None

    def instanciar_prefab(self, arq: Path, x, y):
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
        except Exception as e:
            self.log(f"Prefab inválido {arq.name}: {e}", "erro")
            return
        self.marcar()
        go = self.cena.instanciar(dados, x, y)
        self.cena.iniciar_pendentes()
        self.selecionado = go

    def salvar_prefab(self, go, pasta: Path):
        arq = pasta / f"{go.nome}.prefab"
        dados = objeto_para_dict(go)
        dados["transform"]["x"] = dados["transform"]["y"] = 0
        arq.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        self.log(f"Prefab criado: {self.projeto.relativo(arq)} (arraste para a cena para usar)")

    # =========================================================================
    # Scripts: carregar/recarregar e abrir no editor de código
    # =========================================================================
    def recarregar_scripts(self, forcar=False):
        if self.projeto is None:
            return
        mudaram = self.projeto.carregar_scripts()
        if not mudaram and not forcar:
            return
        for info in self.projeto.scripts.values():
            if info["erro"] and str(info.get("logado")) != str(info["mtime"]):
                self.log("Erro no script " + info["erro"], "erro")
                info["logado"] = info["mtime"]
        if mudaram and not forcar:
            self.log(f"Scripts recarregados ({len(mudaram)} arquivo(s))")
        if self.cena is not None:
            self._trocar_componentes_recarregados()

    def _trocar_componentes_recarregados(self):
        """Depois de recarregar um script, troca as instâncias antigas pela classe nova (mantendo os valores)."""
        from engine2d.objeto import ComponenteAusente
        for go in self.cena.objetos:
            for i, comp in enumerate(list(go.componentes)):
                nome = comp.tipo_original if isinstance(comp, ComponenteAusente) else type(comp).__name__
                cls = REGISTRO_COMPONENTES.get(nome)
                if cls is None:
                    if not isinstance(comp, ComponenteAusente):
                        dados = comp.para_dict()
                        novo = ComponenteAusente(nome, dados["campos"])
                        novo.gameobject = go
                        go.componentes[i] = novo
                    continue
                if type(comp) is cls:
                    continue
                dados = comp.para_dict()["campos"]
                validos = cls._todos_campos()
                try:
                    novo = cls(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in dados.items()
                                  if k in validos})
                except Exception as e:
                    self.log(f"Não consegui recriar {nome}: {e}", "erro")
                    continue
                novo.gameobject = go
                novo.habilitado = comp.habilitado
                go.componentes[i] = novo

    def abrir_arquivo_externo(self, arq: Path):
        """Abre um script no VS Code (se instalado) ou no programa padrão do Windows."""
        code = shutil.which("code")
        try:
            if code:
                subprocess.Popen([code, str(self.projeto.raiz), str(arq)], shell=False)
            elif hasattr(os, "startfile"):
                os.startfile(str(arq))
            else:
                subprocess.Popen(["xdg-open", str(arq)])
            self.log(f"Abrindo {arq.name} no editor de código")
        except Exception as e:
            self.log(f"Não consegui abrir {arq.name}: {e}", "erro")

    # =========================================================================
    # Play: roda a cena atual numa janela separada (rodar.py)
    # =========================================================================
    def play(self):
        if self.processo is not None:
            self.parar()
            return
        if self.projeto is None or self.cena is None:
            return
        biblioteca = self.projeto.raiz / "Library"
        biblioteca.mkdir(exist_ok=True)
        tmp = biblioteca / "play.cena"
        self.cena.salvar(tmp)
        self.aba_baixo = 1
        self.log("► Play: iniciando a cena numa janela...", "play")
        cmd = [sys.executable, "-u", str(RAIZ_ENGINE / "rodar.py"), str(self.projeto.raiz), "--cena", str(tmp)]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYGAME_HIDE_SUPPORT_PROMPT="1")
        self.processo = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=self.projeto.raiz,
                                         text=True, encoding="utf-8", errors="replace", env=env)
        threading.Thread(target=self._ler_saida, args=(self.processo,), daemon=True).start()

    def _ler_saida(self, proc):
        for linha in proc.stdout:
            self.fila_saida.put(linha.rstrip("\n"))
        self.fila_saida.put(None)

    def parar(self):
        if self.processo is not None and self.processo.poll() is None:
            self.processo.terminate()
        self.log("■ Play encerrado", "play")
        self.processo = None

    def _consumir_saida(self):
        while True:
            try:
                linha = self.fila_saida.get_nowait()
            except queue.Empty:
                break
            if linha is None:
                if self.processo is not None:
                    codigo = self.processo.poll()
                    self.log(f"■ Jogo fechado (código {codigo})", "play" if codigo == 0 else "erro")
                    self.processo = None
                continue
            tipo = "erro" if ("Error" in linha or "Traceback" in linha or "ERRO" in linha
                              or linha.startswith("  File")) else "info"
            self.log(linha, tipo)

    # =========================================================================
    # Diálogos simples
    # =========================================================================
    def pedir_texto(self, titulo, inicial, ao_ok):
        self.dialogo = {"tipo": "texto", "titulo": titulo, "ao_ok": ao_ok}
        self.campo = Campo("dialogo", inicial, None)

    def confirmar(self, texto, ao_ok):
        self.dialogo = {"tipo": "confirmar", "titulo": texto, "ao_ok": ao_ok}

    def _desenhar_dialogo(self, ui):
        d = self.dialogo
        ui.retangulo((0, 0, self.W, self.H), (0, 0, 0, 120), raio=0)
        r = pygame.Rect(self.W // 2 - 230, self.H // 2 - 70, 460, 140)
        pygame.draw.rect(ui.surface, COR["fundo"], r, border_radius=6)
        pygame.draw.rect(ui.surface, COR["borda"], r, 1, border_radius=6)
        ui.texto(r.x + 16, r.y + 14, d["titulo"], 14, sombra=False)
        ent = self.motor.entrada
        if d["tipo"] == "texto":
            self.desenhar_campo_texto(ui, (r.x + 16, r.y + 48, r.w - 32, 24), "dialogo", "", None, livre=True)
        ok = botao(ui, (r.right - 200, r.bottom - 40, 88, 26), "OK", destacado=True)
        cancelar = botao(ui, (r.right - 104, r.bottom - 40, 88, 26), "Cancelar")
        if ent.tecla_baixou("return") or ent.tecla_baixou("enter"):
            ok = True
        if ent.tecla_baixou("escape"):
            cancelar = True
        if ok:
            texto = self.campo.texto if (self.campo and d["tipo"] == "texto") else None
            self.dialogo = None
            self.campo = None
            if d["tipo"] == "texto":
                if texto and texto.strip():
                    d["ao_ok"](texto)
            else:
                d["ao_ok"]()
        elif cancelar:
            self.dialogo = None
            self.campo = None

    # =========================================================================
    # Campo de texto (usado no Inspector, renomear, diálogos)
    # =========================================================================
    def desenhar_campo_texto(self, ui, rect, chave, valor, ao_confirmar, livre=True, numerico=False, cor=None):
        r = pygame.Rect(rect)
        ent = self.motor.entrada
        editando = self.campo is not None and self.campo.chave == chave
        pygame.draw.rect(ui.surface, COR["campo_ativo"] if editando else COR["campo"], r, border_radius=3)
        pygame.draw.rect(ui.surface, COR["destaque"] if editando else COR["borda"], r, 1, border_radius=3)
        clip_antes = ui.surface.get_clip()
        ui.surface.set_clip(r.inflate(-2, -2).clip(clip_antes))      # texto comprido não vaza da caixa
        if editando:
            txt = self.campo.texto
            w = ui.fonte(13).size(txt)[0]
            dx = min(0, r.w - 14 - w)                                   # editando: mostra o fim do texto
            if self.campo.selecionar_tudo and txt:
                pygame.draw.rect(ui.surface, COR["selecao"], (r.x + 4, r.y + 3, min(w + 2, r.w - 8), r.h - 6))
            pisca = "|" if int(time.time() * 2) % 2 == 0 else ""
            ui.texto(r.x + 5 + dx, r.centery, txt + pisca, 13, ancora="midleft", sombra=False)
        else:
            ui.texto(r.x + 5, r.centery, str(valor), 13, ancora="midleft", sombra=False, cor=cor or COR["texto"])
        ui.surface.set_clip(clip_antes)
        if not editando and livre and r.collidepoint(ent.mouse_tela) and ent.clicou(1):
            ent.consumir_clique()
            self.campo = Campo(chave, str(valor), ao_confirmar, numerico)
        return r

    def _teclado_campo(self):
        ent = self.motor.entrada
        c = self.campo
        if c is None:
            return
        if ent.tecla_baixou("escape") and c.chave != "dialogo":
            self.campo = None
            ent._baixou.discard("escape")
            return
        if (ent.tecla_baixou("return") or ent.tecla_baixou("enter")) and c.chave != "dialogo":
            self._confirmar_campo()
            return
        if ent.tecla_baixou("backspace"):
            c.texto = "" if c.selecionar_tudo else c.texto[:-1]
            c.selecionar_tudo = False
        if ent.texto_digitado:
            c.texto = ent.texto_digitado if c.selecionar_tudo else c.texto + ent.texto_digitado
            c.selecionar_tudo = False
        if (ent.tecla("left ctrl") or ent.tecla("right ctrl")) and ent.tecla_baixou("v"):
            try:
                cola = pygame.scrap.get_text() if hasattr(pygame.scrap, "get_text") else ""
            except Exception:
                cola = ""
            if cola:
                c.texto = cola if c.selecionar_tudo else c.texto + cola
                c.selecionar_tudo = False

    def _confirmar_campo(self):
        c, self.campo = self.campo, None
        if c is not None and c.ao_confirmar is not None:
            c.ao_confirmar(c.texto)

    # =========================================================================
    # Menus
    # =========================================================================
    def _menus(self):
        return {
            "Arquivo": [("Novo projeto...", self.menu_novo_projeto, ""), ("Abrir projeto...", self.menu_abrir_projeto, ""),
                        None, ("Nova cena", self.nova_cena, ""), ("Salvar cena", self.salvar_cena, "Ctrl+S"),
                        ("Salvar cena como...", lambda: self.salvar_cena(como=True), ""),
                        ("Definir como cena inicial", self.definir_cena_inicial, ""),
                        None, ("Sair", self.sair, "")],
            "Editar": [("Desfazer", self.desfazer, "Ctrl+Z"), ("Refazer", lambda: self.desfazer(True), "Ctrl+Y"),
                       None, ("Duplicar", self.duplicar, "Ctrl+D"), ("Excluir", self.excluir, "Del"),
                       ("Renomear", self.renomear_selecionado, "F2"), ("Focar seleção", self.focar, "F"),
                       None, ("Configurações do projeto...", self.abrir_configuracoes, "")],
            "GameObject": [("Criar vazio", lambda: self.criar_objeto("vazio"), "Ctrl+Shift+N"),
                           ("Sprite", lambda: self.criar_objeto("sprite"), ""),
                           ("Sprite com física", lambda: self.criar_objeto("fisica"), ""),
                           ("Câmera", lambda: self.criar_objeto("camera"), ""),
                           ("Texto (UI)", lambda: self.criar_objeto("texto"), ""),
                           ("Mapa de tiles", self.criar_mapa, ""),
                           None] + self._itens_formas() +
                          [None, ("Criar filho vazio", lambda: self.criar_objeto("vazio", pai=self.selecionado), "")],
            "Assets": [("Criar script...", lambda: self.menu_criar_script(self.pasta_scripts()), ""),
                       ("Criar agente DSL (.agt)...", lambda: self.menu_criar_agente(self.pasta_atual), ""),
                       ("Criar pasta...", lambda: self.menu_criar_pasta(self.pasta_atual), ""),
                       None, ("Importar imagens...", self.menu_importar, ""),
                       ("Mostrar no Explorer", lambda: self.mostrar_no_explorer(self.pasta_atual), ""),
                       ("Recarregar scripts", lambda: self.recarregar_scripts(forcar=True), "")],
            "Ajuda": [("Como criar um script", self.ajuda_script, ""), ("Atalhos do editor", self.ajuda_atalhos, ""),
                      ("Como usar a AgentDSL", self.ajuda_dsl, "")],
        }

    def _desenhar_menu(self, ui):
        pygame.draw.rect(ui.surface, COR["barra"], self.r_menu)
        x = 6
        ent = self.motor.entrada
        for nome, itens in self._menus().items():
            w = ui.fonte(13).size(nome)[0] + 18
            r = pygame.Rect(x, 0, w, 24)
            aberto = self.popup is not None and self.popup.titulo == nome
            if aberto or (self.livre("menu") and r.collidepoint(ent.mouse_tela)):
                pygame.draw.rect(ui.surface, COR["hover"], r)
            ui.texto(r.centerx, 12, nome, 13, ancora="center", sombra=False)
            if self.livre("menu") and r.collidepoint(ent.mouse_tela) and ent.clicou(1):
                ent.consumir_clique()
                self.abrir_popup(x, 24, itens, titulo=nome, mostrar_titulo=False)
            x += w

    def abrir_popup(self, x, y, itens, titulo=None, mostrar_titulo=False, largura=250):
        self.motor.entrada.consumir_clique()   # o clique que abriu o menu não escolhe um item dele
        self.popup = Popup(x, y, itens, largura=largura, titulo=titulo)
        self.popup.mostrar_titulo = mostrar_titulo
        if not mostrar_titulo:
            self.popup.rect.h -= 0
        self.popup.ajustar(self.W, self.H)

    def _desenhar_popup(self, ui):
        p = self.popup
        ent = self.motor.entrada
        h = sum(8 if it is None else 22 for it in p.itens) + 6
        p.rect.h = h
        p.ajustar(self.W, self.H)
        sombra = p.rect.move(3, 3)
        ui.retangulo(sombra, (0, 0, 0, 90), raio=4)
        pygame.draw.rect(ui.surface, COR["fundo2"], p.rect, border_radius=4)
        pygame.draw.rect(ui.surface, COR["borda"], p.rect, 1, border_radius=4)
        y = p.rect.y + 3
        for it in p.itens:
            if it is None:
                pygame.draw.line(ui.surface, COR["borda"], (p.rect.x + 6, y + 4), (p.rect.right - 6, y + 4))
                y += 8
                continue
            rotulo, acao, atalho = it
            r = pygame.Rect(p.rect.x + 2, y, p.rect.w - 4, 22)
            hover = r.collidepoint(ent.mouse_tela) and acao is not None
            if hover:
                pygame.draw.rect(ui.surface, COR["selecao"], r, border_radius=3)
            ui.texto(r.x + 12, r.centery, rotulo, 13, ancora="midleft", sombra=False,
                     cor=COR["texto"] if acao else COR["texto2"])
            if atalho:
                ui.texto(r.right - 10, r.centery, atalho, 12, ancora="midright", sombra=False, cor=COR["texto2"])
            if hover and ent.clicou(1):
                ent.consumir_clique()
                self.popup = None
                acao()
                return
            y += 22

    # --- ações dos menus --------------------------------------------------------------
    def _escolher_pasta(self, titulo):
        try:
            import tkinter
            from tkinter import filedialog
            raiz = tkinter.Tk()
            raiz.withdraw()
            raiz.attributes("-topmost", True)
            pasta = filedialog.askdirectory(title=titulo)
            raiz.destroy()
            return pasta or None
        except Exception as e:
            self.log(f"Não consegui abrir a janela de pastas: {e}", "erro")
            return None

    def menu_abrir_projeto(self):
        pasta = self._escolher_pasta("Abrir projeto (pasta com projeto.json)")
        if pasta:
            self.abrir_projeto(pasta)

    def menu_novo_projeto(self):
        pasta = self._escolher_pasta("Escolha onde criar o projeto")
        if not pasta:
            return

        def ok(nome):
            from engine2d.projeto import Projeto
            raiz = Path(pasta) / nome.strip()
            Projeto.criar(raiz, nome.strip())
            self.abrir_projeto(raiz)
        self.pedir_texto("Nome do novo projeto", "MeuJogo", ok)

    def definir_cena_inicial(self):
        if self.caminho_cena and self.projeto:
            self.projeto.cena_inicial = self.projeto.relativo(self.caminho_cena)
            self.projeto.salvar_config()
            self.log(f"Cena inicial: {self.projeto.cena_inicial}")

    def pasta_scripts(self):
        p = self.projeto.raiz / "Assets" / "Scripts"
        return self.pasta_atual if "Scripts" in self.pasta_atual.parts else p

    def menu_criar_script(self, pasta):
        if self.projeto is None:
            return

        def ok(nome):
            arq = self.projeto.criar_script(pasta, nome)
            self.recarregar_scripts()
            self.pasta_atual = pasta
            self.asset_selecionado = arq
            self.log(f"Script criado: {self.projeto.relativo(arq)} — clique duas vezes para editar")
        self.pedir_texto("Nome do script (ex.: Jogador, Inimigo)", "NovoScript", ok)

    def menu_criar_agente(self, pasta):
        def ok(nome):
            arq = self.projeto.criar_agente(pasta, nome)
            self.asset_selecionado = arq
            self.log(f"Agente criado: {self.projeto.relativo(arq)}")
        self.pedir_texto("Nome do modelo de agente (ex.: inimigo)", "novo_agente", ok)

    def menu_criar_pasta(self, pasta):
        def ok(nome):
            (pasta / nome.strip()).mkdir(exist_ok=True)
        self.pedir_texto("Nome da pasta", "Nova pasta", ok)

    def menu_importar(self):
        try:
            import tkinter
            from tkinter import filedialog
            raiz = tkinter.Tk()
            raiz.withdraw()
            raiz.attributes("-topmost", True)
            arqs = filedialog.askopenfilenames(title="Importar imagens", filetypes=[("Imagens", "*.png *.jpg")])
            raiz.destroy()
        except Exception as e:
            self.log(f"Erro: {e}", "erro")
            return
        for a in arqs:
            shutil.copy(a, self.pasta_atual / Path(a).name)
        if arqs:
            self.log(f"{len(arqs)} imagem(ns) importada(s) para {self.projeto.relativo(self.pasta_atual)}")

    def mostrar_no_explorer(self, pasta):
        try:
            os.startfile(str(pasta))
        except Exception as e:
            self.log(str(e), "erro")

    def renomear_selecionado(self):
        go = self.selecionado
        if go is None:
            return

        def ok(nome):
            self.marcar()
            go.nome = nome.strip()
        self.pedir_texto("Renomear objeto", go.nome, ok)

    def sair(self):
        if self._pode_descartar(self.sair):
            self.rodando = False

    def ajuda_script(self):
        self.aba_baixo = 1
        for l in ["COMO CRIAR UM SCRIPT:",
                  "1. No painel Project, botão direito em Scripts → Criar → Script (ou menu Assets).",
                  "2. Dê um nome (ex.: Jogador). Clique duas vezes no arquivo para editar no VS Code.",
                  "3. Escreva o código em iniciar() (roda uma vez) e atualizar(dt) (roda todo quadro).",
                  "4. Salve. O editor recarrega o script sozinho.",
                  "5. Selecione um objeto → Inspector → Adicionar Componente → Scripts → Jogador.",
                  "6. Variáveis em CAMPOS aparecem no Inspector para editar.",
                  "7. Aperte ► Play para testar. print() aparece aqui no Console."]:
            self.log(l, "ajuda")

    def ajuda_atalhos(self):
        self.aba_baixo = 1
        for l in ["ATALHOS: Ctrl+S salvar · Ctrl+Z/Ctrl+Y desfazer/refazer · Ctrl+D duplicar · Del excluir · F2 renomear",
                  "W mover · E girar · R escalar · F focar · botão do meio ou direito arrasta a cena · roda = zoom",
                  "Ctrl+P Play/Parar · Ctrl ao arrastar = encaixar na grade (32 px)",
                  "Arraste imagens/prefabs do Project para a Scene; arraste um objeto da Hierarchy para o Project = prefab"]:
            self.log(l, "ajuda")

    def ajuda_dsl(self):
        self.aba_baixo = 1
        for l in ["AGENTDSL NO PROJETO:",
                  "1. Crie um .agt (Assets → Criar agente DSL) com 'modelo nome { crenças e planos }'.",
                  "2. Crie um objeto vazio com o componente ServicoAgentes (campo arquivo = Assets/Agentes/x.agt).",
                  "3. Nos objetos controlados, adicione ComportamentoAgente com modelo = nome do modelo.",
                  "4. Para 'invocar(modelo, n)', crie um prefab com o mesmo nome em Assets/Prefabs.",
                  "5. Ações novas: num script, @acao_dsl('nome', 'num') sobre uma função (veja os exemplos)."]:
            self.log(l, "ajuda")

    # =========================================================================
    # Barra de ferramentas
    # =========================================================================
    def _desenhar_ferramentas(self, ui):
        pygame.draw.rect(ui.surface, COR["cabecalho"], self.r_ferr)
        livre = self.livre("ferr")
        x = 8
        for chave, rotulo in (("mover", "Mover (W)"), ("girar", "Girar (E)"), ("escalar", "Escalar (R)")):
            if botao(ui, (x, 29, 88, 24), rotulo, livre, destacado=self.ferramenta == chave):
                self.ferramenta = chave
            x += 92
        cx = self.W // 2
        rodando = self.processo is not None
        if botao(ui, (cx - 50, 28, 100, 26), "■  Parar" if rodando else "►  Play", livre,
                 cor=COR["play"] if rodando else None, tamanho=14):
            self.play()
        nome = (self.caminho_cena.stem if self.caminho_cena else "Nova cena (não salva)") + (" *" if self.modificado else "")
        ui.texto(self.W - 12, 41, f"Cena: {nome}", 13, ancora="midright", sombra=False,
                 cor=COR["amarelo"] if self.modificado else COR["texto"])
        if self.projeto:
            ui.texto(cx + 70, 41, f"Projeto: {self.projeto.nome}", 13, ancora="midleft", sombra=False,
                     cor=COR["texto2"])

    # =========================================================================
    # Atalhos de teclado
    # =========================================================================
    def _atalhos(self):
        ent = self.motor.entrada
        ctrl = ent.tecla("left ctrl") or ent.tecla("right ctrl")
        if ctrl and ent.tecla_baixou("s"):
            self.salvar_cena()
        elif ctrl and ent.tecla_baixou("z"):
            self.desfazer()
        elif ctrl and ent.tecla_baixou("y"):
            self.desfazer(refazer=True)
        elif ctrl and ent.tecla_baixou("d"):
            self.duplicar()
        elif ctrl and ent.tecla_baixou("p"):
            self.play()
        elif ctrl and (ent.tecla("left shift") or ent.tecla("right shift")) and ent.tecla_baixou("n"):
            self.criar_objeto("vazio")
        elif ent.tecla_baixou("delete"):
            if self.selecionado is not None and self.alvo_mouse != "baixo":
                self.excluir()
            elif isinstance(self.asset_selecionado, Path):
                self.excluir_asset(self.asset_selecionado)
        elif ent.tecla_baixou("f2"):
            self.renomear_selecionado()
        elif ent.tecla_baixou("escape"):
            self.popup = None
            self.pincel = None                    # sai do modo de pintar o mapa
        elif not ctrl and self.alvo_mouse in ("scene", "hier"):
            if ent.tecla_baixou("w"):
                self.ferramenta = "mover"
            elif ent.tecla_baixou("e"):
                self.ferramenta = "girar"
            elif ent.tecla_baixou("r"):
                self.ferramenta = "escalar"
            elif ent.tecla_baixou("f"):
                self.focar()

    # =========================================================================
    # Loop
    # =========================================================================
    def executar(self, max_quadros=None):
        self.layout()
        quadro = 0
        while self.rodando:
            self.passo()
            quadro += 1
            if max_quadros and quadro >= max_quadros:
                break
        self.parar() if self.processo else None
        self.motor.encerrar()

    def passo(self):
        """Um quadro do editor: lê os eventos da janela e redesenha tudo."""
        self.motor.entrada.novo_quadro()
        for ev in pygame.event.get():
            if self.motor.tratar_evento_janela(ev):
                self.W, self.H = self.motor.largura, self.motor.altura
                self.layout()
            elif ev.type == pygame.QUIT:
                self.sair()
                if self.dialogo is None:
                    self.rodando = False
            elif ev.type == pygame.DROPFILE and self.projeto:   # arquivos arrastados do Windows
                self.importar_arquivo(Path(ev.file), self._mouse_no_drop())
            self.motor.entrada.processar(ev)
        try:
            self.quadro()
        except Exception:
            import traceback
            self.log("Erro interno do editor: " + traceback.format_exc().strip().splitlines()[-1], "erro")
            traceback.print_exc()
            self.popup = None
            self.campo = None
            self.arrasto = None

    def _mouse_no_drop(self):
        """Onde o arquivo foi solto. Enquanto o Windows arrasta um arquivo a janela não recebe
        MOUSEMOTION, então pergunta ao sistema a posição do cursor."""
        try:
            import ctypes
            from ctypes import wintypes
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            ctypes.windll.user32.ScreenToClient(pygame.display.get_wm_info()["window"], ctypes.byref(pt))
            if 0 <= pt.x < self.W and 0 <= pt.y < self.H:
                return pt.x, pt.y
        except Exception:
            pass
        return self.motor.entrada.mouse_tela

    def importar_arquivo(self, origem: Path, onde=None):
        """Copia um arquivo de fora do projeto para a pasta aberta no Project. Solto sobre a Scene, um
        campo do Inspector ou um objeto da Hierarchy, ele já é usado ali (como se viesse do Project)."""
        destino = self.pasta_atual / origem.name
        if origem.suffix.lower() in (".png", ".jpg", ".jpeg") and self.pasta_atual == self.projeto.raiz / "Assets":
            destino = self.projeto.raiz / "Assets" / "Sprites" / origem.name
            destino.parent.mkdir(parents=True, exist_ok=True)
        try:
            if origem.resolve() != destino.resolve():
                shutil.copy(origem, destino)
            self.log(f"Importado: {self.projeto.relativo(destino)}")
        except Exception as e:
            self.log(f"Erro ao importar: {e}", "erro")
            return None
        self._cache_disco = None
        if onde is not None:
            from .widgets import Arrasto
            a = Arrasto("asset", destino, destino.name, onde)
            a.ativo = True
            self.layout()
            self._soltar(a, *onde)
        return destino

    def quadro(self):
        ent = self.motor.entrada
        ui = self.ui
        self.alvo_mouse = self._alvo()
        if self._scrub is None:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
        if self.projeto is not None and self.popup is None and self.dialogo is None:
            self._divisorias()
        if time.time() - self._ultimo_check_scripts > 1.0:
            self._ultimo_check_scripts = time.time()
            self.recarregar_scripts()
        self._consumir_saida()
        # clique fora do popup fecha o popup (e não vale para o painel de baixo)
        if self.popup and ent.clicou(1) and self.alvo_mouse != "popup":
            self.popup = None
            ent.consumir_clique()
        if ent.clicou(3) and self.popup and self.alvo_mouse != "popup":
            self.popup = None
        if self.campo is not None:
            self._teclado_campo()
            if self.campo is not None and self.campo.chave != "dialogo" and ent.clicou(1):
                self._confirmar_campo()
        elif self.dialogo is None:
            self._atalhos()

        ui.limpar()
        if self.projeto is None:
            self._desenhar_hub(ui)
        else:
            self.cena.sincronizar_render()
            self._desenhar_scene(ui)          # sobreposições da cena (grade, gizmos)
            self._desenhar_hierarquia(ui)
            self._desenhar_inspector(ui)
            self._desenhar_baixo(ui)
            self._desenhar_ferramentas(ui)
            self._desenhar_menu(ui)
            self._atualizar_arrasto(ui)
        if self.popup:
            self._desenhar_popup(ui)
        if self.dialogo:
            self._desenhar_dialogo(ui)
        ui.enviar()
        r = self.motor.renderizador
        r.cor_fundo = (0.19, 0.19, 0.2, 1.0)
        r.limpar()
        if self.projeto is not None:
            sv = self.r_scene
            self.cam.largura, self.cam.altura = sv.w, sv.h
            luzes = self.cena.iluminacao() if self.ver_luzes else None
            if luzes is not None:
                # no editor sem luz global a cena ficaria preta: um mínimo de ambiente para enxergar
                luzes["ambiente"] = tuple(max(c, 0.12) for c in luzes["ambiente"])
            r.desenhar(self.cena.lista, self.cam, extras_tela=[ui.sprite],
                       viewport=(sv.x, self.H - sv.bottom, sv.w, sv.h), luzes=luzes)
        else:
            from engine2d import ListaRenderizacao
            r.desenhar(ListaRenderizacao(), self.cam, extras_tela=[ui.sprite])
        if self.motor._capturas:
            self.motor._salvar_captura(self.motor._capturas.pop(0))
        pygame.display.flip()

    # =========================================================================
    # Arrastar e soltar entre painéis
    # =========================================================================
    def iniciar_arrasto(self, tipo, valor, rotulo, ao_clicar=None):
        self.arrasto = Arrasto(tipo, valor, rotulo, self.motor.entrada.mouse_tela)
        self.arrasto.ao_clicar = ao_clicar

    def _atualizar_arrasto(self, ui):
        a = self.arrasto
        if a is None:
            return
        ent = self.motor.entrada
        mx, my = ent.mouse_tela
        if not a.ativo and (abs(mx - a.inicio[0]) + abs(my - a.inicio[1])) > 6:
            a.ativo = True
        if a.ativo:
            r = ui.texto(mx + 14, my + 8, a.rotulo, 13, sombra=False)
            ui.retangulo(r.inflate(10, 6), (30, 30, 30, 200), raio=3)
            ui.texto(mx + 14, my + 8, a.rotulo, 13, sombra=False)
        if not ent.mouse_pressionado(1):
            if a.ativo:
                self._soltar(a, mx, my)
            elif getattr(a, "ao_clicar", None):
                a.ao_clicar()
            self.arrasto = None

    def _soltar(self, a, mx, my):
        alvo = None
        for nome in ("hier", "scene", "insp", "baixo"):
            if getattr(self, "r_" + nome).collidepoint(mx, my):
                alvo = nome
        if alvo == "scene":
            wx, wy = self.tela_para_mundo(mx, my)
            if a.tipo == "asset":
                arq: Path = a.valor
                ext = arq.suffix.lower()
                if ext in (".py", ".agt"):            # script solto em cima de um objeto da cena
                    go = self._escolher(wx, wy)
                    if go is not None:
                        self.selecionado = go
                        self.usar_asset_no_objeto(arq, go)
                    else:
                        self.log("Solte o script em cima de um objeto (na Scene, Hierarchy ou Inspector)", "aviso")
                elif ext in (".png", ".jpg", ".jpeg"):
                    self.criar_objeto("sprite", x=wx, y=wy, imagem=self.projeto.relativo(arq))
                elif ext == ".prefab":
                    self.instanciar_prefab(arq, wx, wy)
        elif alvo == "hier":
            self.soltar_na_hierarquia(a, mx, my)
        elif alvo == "insp":
            self.soltar_no_inspector(a, mx, my)
        elif alvo == "baixo" and a.tipo == "objeto" and self.aba_baixo == 0:
            self.salvar_prefab(a.valor, self.pasta_atual)

    # =========================================================================
    # Tela inicial (sem projeto aberto)
    # =========================================================================
    def _desenhar_hub(self, ui):
        ui.retangulo((0, 0, self.W, self.H), COR["fundo2"], raio=0)
        ui.texto(60, 50, "Engine2D Hub", 30, negrito=True, sombra=False)
        ui.texto(60, 92, "Abra um projeto ou crie um novo.", 15, sombra=False, cor=COR["texto2"])
        if botao(ui, (60, 130, 170, 34), "Novo projeto...", destacado=True):
            self.menu_novo_projeto()
        if botao(ui, (240, 130, 170, 34), "Abrir projeto..."):
            self.menu_abrir_projeto()
        ui.texto(60, 186, "Projetos prontos para abrir", 16, negrito=True, sombra=False)
        prontos = [("ProjetoExemplo", "Coletor de Moedas", "exemplo simples: scripts comentados + DSL"),
                   ("ProjetoArena", "Arena dos Sobreviventes", "estilo Vampire Survivors"),
                   ("ProjetoTorres", "Defesa da Base", "tower defense estilo Bloons"),
                   ("ProjetoSorveteria", "Fábrica de Sorvete", "jogo de programação com a DSL"),
                   ("ProjetoNavinha", "Navinha", "shoot 'em up montado no editor"),
                   ("ProjetoPlataforma", "Pulo Verde", "plataforma estilo Mario, física + DSL")]
        prontos = [p for p in prontos if (RAIZ_ENGINE / p[0]).exists()]
        colunas = max(1, (self.W - 80) // 250)
        for i, (pasta, titulo, sub) in enumerate(prontos):
            r = pygame.Rect(60 + (i % colunas) * 250, 214 + (i // colunas) * 74, 240, 64)
            hover = r.collidepoint(self.motor.entrada.mouse_tela)
            pygame.draw.rect(ui.surface, COR["selecao"] if hover else COR["fundo"], r, border_radius=4)
            ui.texto(r.x + 12, r.y + 12, titulo, 15, negrito=True, sombra=False)
            ui.texto(r.x + 12, r.y + 36, sub, 12, sombra=False, cor=COR["texto2"])
            if hover and self.motor.entrada.clicou(1):
                self.abrir_projeto(RAIZ_ENGINE / pasta)
                return
        y = 214 + ((len(prontos) + colunas - 1) // colunas) * 74 + 12
        ui.texto(60, y, "Projetos recentes", 16, negrito=True, sombra=False)
        try:
            recentes = json.loads(RECENTES.read_text(encoding="utf-8")) if RECENTES.exists() else []
        except Exception:
            recentes = []
        y += 30
        for p in recentes:
            if not (Path(p) / "projeto.json").exists():
                continue
            r = pygame.Rect(60, y, 700, 44)
            hover = r.collidepoint(self.motor.entrada.mouse_tela)
            pygame.draw.rect(ui.surface, COR["hover"] if hover else COR["fundo"], r, border_radius=4)
            ui.texto(r.x + 14, r.y + 6, Path(p).name, 15, negrito=True, sombra=False)
            ui.texto(r.x + 14, r.y + 25, p, 12, sombra=False, cor=COR["texto2"])
            if hover and self.motor.entrada.clicou(1):
                self.abrir_projeto(p)
                return
            y += 50


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    sys.path.insert(0, str(RAIZ_ENGINE))
    app = EditorApp(argv[0] if argv else None)
    app.executar()
