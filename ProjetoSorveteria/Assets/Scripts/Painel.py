"""Gerencia as janelas flutuantes, compila o programa e desenha as telas: início, Árvore (T), Comandos (F1),
menu e "Novo!".

Cada janela de código vira um bloco do programa da DSL:
    janela "Todos os robôs"  ->  modelo todos { <texto da janela> }
    janela de um robô        ->  modelo janela7 { ... }      (só aquele robô segue)
    janela do gerente        ->  agente gerente { ... }
Os erros do compilador voltam para a linha certa da janela certa.
"""
import re

import pygame

from agentdsl import analisar
from agentdsl.erros import Diagnostico, Posicao
from Desbloqueios import ACOES_BASE, ACOES_DESBLOQUEIO, ARVORE, COMANDOS, PERCEPCOES_GERENTE, verificar
from engine2d import Componente
from engine2d.ui import CORES
from Erros import amigavel
from engine2d.projeto import ACOES_DSL, PERCEPCOES_DSL
from Itens import CALDAS, COBERTURAS, MASSAS, PERCEPCOES_ROBO, PONTOS, TAMANHOS, TIPOS
from Janelas import (BARRA, CURSORES, Arrastar, JanelaCodigo, JanelaInfo, JanelaSaida, borda, botao,
                     desenhar_moldura, manter_na_tela, na_barra)

MAPA = (0, 0, 1280, 720)
TOPO = 44
LINHA_PLANO = re.compile(r"plano linha (\d+)")
COR_TIPO = {"erro": (255, 120, 120), "falha": (240, 170, 110), "print": (150, 210, 255),
            "compra": (255, 220, 90), "info": (190, 195, 210)}
TEXTO_INICIAL = ("// Programa dos robôs. Aperte o triângulo verde (ou Ctrl+Enter):\n"
                 "// o robô começa pelo PRIMEIRO objetivo (+!) desta janela.\n"
                 "+!comecar <- dancar.\n")


def quebrar(texto, largura):
    linhas, atual = [], ""
    for palavra in texto.split():
        if atual and len(atual) + 1 + len(palavra) > largura:
            linhas.append(atual)
            atual = palavra
        else:
            atual = f"{atual} {palavra}".strip()
    return linhas + ([atual] if atual else [])


class Painel(Componente):
    def iniciar(self):
        self.cena.servicos["painel"] = self
        self.srv = self.cena.servicos["agentes"]
        self.fab = self.cena.servicos["sorveteria"]
        self.tela = "inicio"            # None | inicio | arvore | comandos | menu | novidade
        self.novidade = None
        self.confirmar = False
        self.robo_destacado = None
        self.arrastar = Arrastar()
        self.mapa_linhas = []           # [(janela, primeira linha no programa, nº de linhas)]
        self._ultimo_log = {}
        self.rolagem_cmd = 0
        self._ultima_ok = False
        self._avisos = []
        self._religar = []
        log_original = self.srv._log

        def log(linha, tipo):
            if tipo in ("print", "erro"):
                self.fab.registrar(linha, tipo)
            log_original(linha, tipo)
        self.srv._log = log
        if self.srv.sis is not None:
            self.srv.sis.ao_registrar = log
        self.janelas = []
        self._criar_janelas((self.fab.dados_salvos or {}).get("janelas"))
        pygame.key.set_repeat(380, 35)
        self.motor.sair_com_esc = False
        self.motor.pausado = True       # até apertar "Começar"
        self.compilar()                 # deixa o programa das janelas valendo (sem ligar os robôs)

    # --- janelas ---------------------------------------------------------------------------------
    def _criar_janelas(self, salvas):
        W, H = self.motor.largura, self.motor.altura
        self.janelas = []
        if salvas:
            for d in salvas:
                if d["tipo"] == "codigo":
                    j = JanelaCodigo(d["rect"], d.get("alvo", "todos"), d.get("texto", ""))
                elif d["tipo"] == "info":
                    j = JanelaInfo(d["rect"])
                else:
                    j = JanelaSaida(d["rect"])
                j.minimizada, j.fechada = d.get("minimizada", False), d.get("fechada", False)
                self.janelas.append(j)
        if not any(j.tipo == "codigo" and j.alvo == "todos" for j in self.janelas):
            self.janelas.append(JanelaCodigo((480, H - 345, 590, 330), "todos", TEXTO_INICIAL))
        if not any(j.tipo == "info" for j in self.janelas):
            self.janelas.insert(0, JanelaInfo((12, H - 315, 458, 300)))
        if not any(j.tipo == "saida" for j in self.janelas):
            s = JanelaSaida((12, H - 480, 458, 160))
            s.fechada = True
            self.janelas.insert(0, s)

    def estado_janelas(self):
        return [j.estado() for j in self.janelas]

    def recomecar(self):
        self._criar_janelas(None)
        self.tela = None
        self.compilar()

    def codigos(self):
        return [j for j in self.janelas if j.tipo == "codigo"]

    def nova_janela(self):
        abertas = [j for j in self.codigos() if not j.fechada]
        n = len(abertas)
        livres = [g.nome for g in self.fab.robos() if not any(j.alvo == g.nome for j in abertas)]
        if not any(j.alvo == "todos" for j in abertas):
            alvo, texto = "todos", TEXTO_INICIAL
        else:
            alvo = livres[-1] if livres else "todos"
            texto = f"// programa só do {alvo}\n+!comecar <- dancar.\n" if alvo != "todos" else TEXTO_INICIAL
        j = JanelaCodigo((max(20, 520 - 40 * n), max(TOPO + 10, self.motor.altura - 400 - 30 * n), 520, 320),
                         alvo, texto)
        self.janelas.append(j)
        self.compilar()

    def mostrar_janela(self, tipo):
        for j in self.janelas:
            if j.tipo == tipo:
                j.fechada = False
                j.minimizada = False
                self.janelas.remove(j)
                self.janelas.append(j)
                return

    def modelo_do_robo(self, nome):
        for j in self.codigos():
            if j.alvo == nome and not j.fechada:
                return j.modelo
        return "todos"

    def janela_do_robo(self, nome):
        modelo = self.modelo_do_robo(nome)
        return next((j for j in self.codigos() if not j.fechada and j.modelo == modelo), None)

    @staticmethod
    def primeiro_objetivo(jan):
        """O nome do primeiro +!objetivo (sem valores) da janela: é por ele que o Executar começa."""
        if jan is None:
            return None
        prog, erros = analisar("modelo x {\n" + jan.editor.texto + "\n}")
        if erros or not prog.agentes:
            return None
        for p in prog.agentes[0].planos:
            if p.evento.objetivo and p.evento.op == "+" and not p.evento.literal.args:
                return p.evento.literal.nome
        return None

    def primeiro_objetivo_do_robo(self, nome):
        return self.primeiro_objetivo(self.janela_do_robo(nome))

    def robos_da_janela(self, jan):
        if jan.alvo == "todos":
            return [g.nome for g in self.fab.robos() if self.modelo_do_robo(g.nome) == "todos"]
        if jan.alvo == "gerente":
            return []
        return [jan.alvo]

    def alvos_possiveis(self, jan):
        usados = {j.alvo for j in self.codigos() if j is not jan and not j.fechada}
        alvos = [] if "todos" in usados else ["todos"]
        alvos += [g.nome for g in self.fab.robos() if g.nome not in usados]
        if self.fab.tem("gerencia") and "gerente" not in usados:
            alvos.append("gerente")
        return alvos or [jan.alvo]

    # --- compilar: junta as janelas num programa só ---------------------------------------------------
    def montar(self):
        linhas, self.mapa_linhas = [], []
        for j in self.codigos():
            if j.fechada:
                continue
            linhas.append("agente gerente {" if j.alvo == "gerente" else f"modelo {j.modelo} {{")
            inicio = len(linhas) + 1
            linhas += j.editor.linhas
            linhas.append("}")
            self.mapa_linhas.append((j, inicio, len(j.editor.linhas)))
        if not any(j.alvo == "todos" and not j.fechada for j in self.codigos()):
            linhas += ["modelo todos {", "}"]      # sem a janela "Todos os robôs": eles ficam sem programa
        return "\n".join(linhas)

    def _local(self, linha_prog):
        for j, inicio, n in self.mapa_linhas:
            if inicio - 1 <= linha_prog <= inicio + n:
                return j, max(1, min(n, linha_prog - inicio + 1))
        return (self.mapa_linhas[-1][0], self.mapa_linhas[-1][2]) if self.mapa_linhas else (None, 1)

    def compilar(self):
        """Compila todas as janelas. Devolve True se não houver erros (o programa novo passa a valer)."""
        texto = self.montar()
        for j in self.codigos():
            j.erros = []
            j.editor.marcas = {}
        prog, diags = analisar(texto)
        if not diags:
            diags = verificar(prog, self.fab.tem, PERCEPCOES_ROBO)
        ok = False
        if not diags and texto == self.srv.fonte and self._ultima_ok:
            ok, diags = True, list(self._avisos)        # nada mudou: não recria os agentes
        elif not diags:
            # recompilar recria os agentes: quem estava trabalhando recebe +ligado de novo depois
            ligados = [g.nome for g in self.fab.robos() if getattr(g.obter("Robo"), "ocupado", False)]
            ok, diags = self.srv.recompilar(texto)
            diags = list(diags)
            self._avisos = diags if ok else []
            self._religar = ligados if ok else []
        self._ultima_ok = ok
        erros = 0
        for d in diags:
            grave = d.gravidade == "erro" or d.mensagem.startswith("alvo '")
            if d.pos is None:
                j, lin, col = (self.mapa_linhas[0][0] if self.mapa_linhas else None), 1, 1
            else:
                j, lin = self._local(d.pos.linha)
                col = d.pos.coluna
            if j is None:
                continue
            local = Diagnostico(d.fase, d.mensagem, Posicao(lin, col), "erro" if grave else "aviso")
            msg, dica = amigavel(local, j.editor.linhas)
            j.erros.append((local, msg, dica))
            if j.editor.marcas.get(lin - 1) != "erro":
                j.editor.marcas[lin - 1] = local.gravidade
            erros += grave
        if ok and not erros:
            for g in self.fab.robos():         # cada robô segue o modelo da sua janela
                comp = g.obter("ComportamentoAgente")
                desejado = self.modelo_do_robo(g.nome)
                if comp is not None and comp._iniciado and comp.modelo != desejado:
                    self.srv.trocar_modelo(comp, desejado)
            return True
        return False

    def executar(self, jan):
        ok = self.compilar()
        if not ok:
            com_erro = [j for j in self.codigos() if any(e[0].gravidade == "erro" for e in j.erros)]
            for j in self.codigos():
                if j in com_erro:
                    n = sum(e[0].gravidade == "erro" for e in j.erros)
                    j.status = (f"{n} erro{'s' if n > 1 else ''}: os robôs não entenderam (veja abaixo)",
                                COR_TIPO["erro"])
                elif j is jan:
                    j.status = (f"erro na janela '{com_erro[0].nome_alvo}'" if com_erro else "erro",
                                COR_TIPO["erro"])
            return False
        nomes = self.robos_da_janela(jan)
        outros = [n for n in self._religar if n not in nomes]
        self._religar = []
        objetivos = {n: self.primeiro_objetivo_do_robo(n) for n in nomes + outros}
        self.fab.ligar(nomes + outros, objetivos)
        primeiro = self.primeiro_objetivo(jan)
        if jan.alvo == "gerente":
            gerente = self.srv.sis.agentes.get("gerente")
            if gerente is not None and primeiro:
                gerente.objetivo(primeiro, ())
            jan.status = ("Gerente trabalhando!", CORES["verde"])
        elif not nomes:
            jan.status = ("Nenhum robô segue esta janela.", CORES["destaque"])
        elif primeiro:
            jan.status = (f"Executando! Começou por !{primeiro}", CORES["verde"])
        else:
            jan.status = ("Sem objetivo para começar: escreva um +!objetivo (ex.: +!comecar <- dancar.)",
                          CORES["destaque"])
        self.fab.salvar_agora()
        return True

    def parar(self, jan):
        self.fab.parar(self.robos_da_janela(jan) if jan.alvo != "gerente" else [])
        jan.status = ("Parado.", (190, 195, 210))

    def ao_comprar(self, chave, mostrar=True):
        if mostrar:
            self.novidade = chave
            self.tela = "novidade"

    # --- câmera e linha executada -----------------------------------------------------------------------
    def atualizar_tardio(self, dt):
        cam = self.motor.camera
        w, h = cam.largura, cam.altura
        mx, my, mw, mh = MAPA
        zoom = min(w / mw, (h - TOPO) / mh)
        cam.zoom = zoom
        cam.x = mx + mw / 2
        cam.y = my + mh / 2 - (h / 2 - (TOPO + (h - TOPO) / 2)) / zoom
        go = self.cena.encontrar("Câmera")
        comp = go.obter("CameraPrincipal") if go else None
        if comp:
            go.transform.x, go.transform.y, comp.zoom = cam.x, cam.y, zoom
        self._seguir_execucao()

    def _seguir_execucao(self):
        for ag in self.srv.sis.todos() if self.srv.sis else []:
            if not ag.log:
                continue
            chave = (len(ag.log), ag.log[-1])
            if self._ultimo_log.get(id(ag)) != chave:
                self._ultimo_log[id(ag)] = chave
                m = LINHA_PLANO.search(ag.log[-1])
                if m:
                    j, lin = self._local(int(m.group(1)))
                    if j is not None:
                        j.editor.destacar(lin - 1)

    # --- desenho ---------------------------------------------------------------------------------------
    def desenhar_ui(self, ui):
        ent = self.motor.entrada
        foco = any(j.tipo == "codigo" and j.editor.focado for j in self.janelas)
        if self.tela != "inicio":
            if ent.tecla_baixou("f1") or (ent.tecla_baixou("tab") and not foco):
                self.alternar("comandos")
            elif ent.tecla_baixou("t") and not foco and self.tela != "novidade":
                self.alternar("arvore")
            elif ent.tecla_baixou("escape") and self.tela == "menu":
                self.sair()
            elif ent.tecla_baixou("escape") and self.tela:
                self.tela = None
                ent._baixou.discard("escape")
            elif ent.tecla_baixou("escape") and not foco:
                self.tela = "menu"            # com o editor focado, o Esc é dele (lista, seleção, busca)
                self.confirmar = False
        ui.depois(self._desenhar_janelas)
        telas = {"inicio": self._tela_inicio, "arvore": self._tela_arvore, "comandos": self._tela_comandos,
                 "menu": self._tela_menu, "novidade": self._tela_novidade}
        if self.tela in telas:
            ui.sobrepor(telas[self.tela])

    def alternar(self, nome):
        self.tela = None if self.tela == nome else nome
        self.confirmar = False
        if self.tela:
            for j in self.codigos():
                j.editor.focado = False

    def _desenhar_janelas(self, ui):
        if self.tela == "inicio":
            return
        ent = self.motor.entrada
        W, H = ui.largura, ui.altura
        bloqueado = ui._modal_ativo or self.tela is not None
        visiveis = [j for j in self.janelas if not j.fechada]
        for j in visiveis:
            manter_na_tela(j, W, H, TOPO)
        self.arrastar.atualizar(ent.mouse_tela, ent.mouse_pressionado(1), W, H, TOPO)
        # a janela de cima que está sob o mouse recebe o mouse (a borda conta um pouco para fora)
        topo = None
        if not bloqueado:
            for j in reversed(visiveis):
                if j.area_visivel.inflate(10, 10).collidepoint(ent.mouse_tela):
                    topo = j
                    break
        lado = borda(topo, ent.mouse_tela) if topo is not None and self.arrastar.janela is None else ""
        if topo is not None and ent.clicou(1) and self.arrastar.janela is None:
            if topo is not visiveis[-1]:
                self.janelas.remove(topo)
                self.janelas.append(topo)
            if lado:
                ent.consumir_clique()
                self.arrastar.comecar(topo, lado, ent.mouse_tela)
            elif na_barra(topo, ent.mouse_tela) and not self._sobre_botao_barra(topo, ent.mouse_tela):
                self.arrastar.comecar(topo, "mover", ent.mouse_tela)
        self.robo_destacado = None
        visiveis = [j for j in self.janelas if not j.fechada]
        for j in visiveis:
            aqui = j is topo and self.arrastar.janela is None and not lado
            ui.bloquear(j.area_visivel)
            acao = desenhar_moldura(ui, j, j is visiveis[-1], ent, aqui)
            if acao == "fechar":
                j.fechada = True
                if j.tipo == "codigo":
                    j.editor.focado = False
                    self.fab.parar(self.robos_da_janela(j) if j.alvo != "gerente" else [])
                    self.janelas.remove(j)       # "+ Janela de código" cria outra
                    self.compilar()
                continue
            if acao == "minimizar":
                j.minimizada = not j.minimizada
            if j.tipo == "codigo":
                self._janela_codigo(ui, j, ent, aqui)
            elif j.tipo == "info":
                self._janela_info(ui, j, ent, aqui)
            else:
                self._janela_saida(ui, j, ent, aqui)

        self._atualizar_cursor(lado)

    def _atualizar_cursor(self, lado):
        modo = self.arrastar.modo if self.arrastar.janela is not None else lado
        if modo:
            nome = CURSORES.get(modo, "SYSTEM_CURSOR_ARROW")
        elif any(j.editor.mouse_sobre for j in self.codigos() if not j.fechada and not j.minimizada):
            nome = "SYSTEM_CURSOR_IBEAM"
        else:
            nome = "SYSTEM_CURSOR_ARROW"
        if nome != getattr(self, "_cursor", None):
            self._cursor = nome
            try:
                pygame.mouse.set_cursor(getattr(pygame, nome))
            except Exception:
                pass

    def _sobre_botao_barra(self, j, mouse):
        """Os botões da barra (executar, parar e o seletor de robô) não arrastam a janela."""
        return j.tipo == "codigo" and mouse[0] < j.rect.x + 230

    # --- janela de código --------------------------------------------------------------------------------
    # --- autocompletar ---------------------------------------------------------------------------------
    def _vocabulario(self, editor):
        """Tudo o que pode ser sugerido agora: (inserir, rótulo, descrição)."""
        fab = self.fab
        voc = []
        for nome, (sig, _) in sorted(ACOES_DSL.items()):
            chave = ACOES_DESBLOQUEIO.get(nome)
            if nome not in ACOES_BASE and chave is None:
                continue
            if chave and not fab.tem(chave):
                continue
            args = ", ".join({"atomo": "x", "num": "n", "texto": '"..."'}.get(t, t) for t in sig.tipos)
            voc.append((nome + ("(" if sig.tipos else ""), f"{nome}({args})" if sig.tipos else nome,
                        sig.descricao[:48]))
        voc.append(('imprimir(', 'imprimir("texto")', "escreve na janela Saída"))
        if fab.tem("relogio"):
            voc.append(("temporizador(", "temporizador(seg, crenca)", "cria +crenca depois de seg segundos"))
        voc += [("ligado", "ligado", "evento: você apertou Executar"),
                ("terminou", "terminou", "evento: o robô acabou os comandos")]
        if fab.tem("sentidos"):
            for (nome, n), tipos in sorted(PERCEPCOES_DSL.items()):
                if nome in PERCEPCOES_ROBO and nome not in ("ligado", "terminou"):
                    voc.append((nome + ("(" if n else ""), nome + ("(" + ", ".join("X" * 1 for _ in range(n)) + ")"
                                                                if n else ""), "percepção"))
        if fab.tem("gerencia"):
            voc += [(p + "(", p + "(...)", "percepção do gerente") for p in sorted(PERCEPCOES_GERENTE)]
        if fab.tem("operadores"):
            voc.append(("nao ", "nao", "negação: nao livre"))
        opcoes = [(TAMANHOS, "tamanho", "tamanho"), (TIPOS, "tipo", "tipo de sorvete"),
                  (MASSAS, "massa", "massa"), (CALDAS, "calda", "calda"), (COBERTURAS, "cobertura", "cobertura")]
        vistos = set()
        for lista, cat, desc in opcoes:
            for op in lista:
                if op in fab.liberadas(cat) and (op, desc) not in vistos:
                    vistos.add((op, desc))
                    voc.append((op, op, desc))
        voc += [(p, p, "ponto da batedeira") for p in PONTOS if p != "medio"]
        for nome in ("armazem", "maquina", "massas", "batedeira", "caldas", "coberturas", "balcao",
                     "bancada1", "bancada2", "bancada3"):
            if fab.tem_estacao(nome):
                voc.append((nome, nome, "estação"))
        voc += [(g.nome, g.nome, "robô") for g in fab.robos()]
        for obj in sorted(set(re.findall(r"[+-]!([a-z][A-Za-z0-9_]*)", editor.texto))):
            voc.append((obj, obj, "objetivo desta janela"))
        return voc

    def _sugestoes(self, prefixo, editor):
        voc = self._vocabulario(editor)
        comeca = [v for v in voc if v[1].startswith(prefixo)]
        contem = [v for v in voc if prefixo in v[1] and v not in comeca and len(prefixo) >= 3]
        unicos, vistos = [], set()
        for v in comeca + contem:
            if v[0] not in vistos:
                vistos.add(v[0])
                unicos.append(v)
        return unicos

    def _janela_codigo(self, ui, j, ent, aqui):
        j.editor.fonte_sugestoes = self._sugestoes
        r = j.rect
        if botao(ui, (r.x + 4, r.y + 4, 30, 18), "", aqui, ent, cor=(46, 110, 60), dica="executar (Ctrl+Enter)"):
            self.executar(j)
        tx, ty = r.x + 15, r.y + 13
        pygame.draw.polygon(ui.surface, (170, 245, 175), [(tx, ty - 5), (tx, ty + 5), (tx + 9, ty)])
        if botao(ui, (r.x + 38, r.y + 4, 30, 18), "", aqui, ent, cor=(110, 50, 55), dica="parar"):
            self.parar(j)
        pygame.draw.rect(ui.surface, (245, 190, 190), (r.x + 48, r.y + 8, 10, 10))
        rodando = any(g.obter("Robo") and g.obter("Robo").ocupado for g in self.fab.robos()
                      if g.nome in self.robos_da_janela(j))
        alvos = self.alvos_possiveis(j)
        rot = f"{j.nome_alvo}  ▼" if len(alvos) > 1 else j.nome_alvo
        if botao(ui, (r.x + 76, r.y + 4, 150, 18), rot, aqui, ent, dica="quem esta janela controla (clique para trocar)"):
            if len(alvos) > 1:
                i = alvos.index(j.alvo) if j.alvo in alvos else -1
                j.alvo = alvos[(i + 1) % len(alvos)]
                self.compilar()
        if aqui and pygame.Rect(r.x + 76, r.y + 4, 150, 18).collidepoint(ent.mouse_tela) and j.alvo.startswith("robo"):
            g = self.fab.robo_por_nome(j.alvo)
            self.robo_destacado = g.obter("Robo") if g else None
        if rodando:
            ui.texto(r.x + 234, r.y + 13, "rodando", 11, ancora="midleft", cor=(140, 230, 150), sombra=False)
        if j.minimizada:
            return
        corpo = j.corpo()
        alto_msg = 22 + 32 * min(3, len(j.erros)) if j.erros else 24
        caixa = pygame.Rect(corpo.x, corpo.y, corpo.w, corpo.h - alto_msg)
        if aqui or j.editor.focado:
            if j.editor.teclado(ent) == "compilar":
                self.executar(j)
        if j.editor.focado:
            for outra in self.codigos():
                if outra is not j:
                    outra.editor.focado = False
        j.editor.desenhar(ui, caixa, ent, livre=aqui, dt=1 / 60)
        y = caixa.bottom + 4
        msg, cor = j.status
        if j.editor.texto != self._texto_aplicado(j) and cor != COR_TIPO["erro"]:
            msg, cor = "Mudanças não aplicadas: aperte Executar.", CORES["destaque"]
        ui.texto(corpo.x + 8, y, msg[:80], 12, cor=cor, sombra=False)
        y += 18
        for local, m, dica in j.erros[:3]:
            linha = pygame.Rect(corpo.x + 4, y - 1, corpo.w - 8, 30)
            if aqui and linha.collidepoint(ent.mouse_tela):
                pygame.draw.rect(ui.surface, (45, 48, 60), linha)
                if ent.clicou(1):
                    ent.consumir_clique()
                    j.editor.ir_para(local.pos.linha - 1, local.pos.coluna - 1)
            cor_e = COR_TIPO["erro"] if local.gravidade == "erro" else (230, 200, 110)
            ui.texto(corpo.x + 8, y, f"linha {local.pos.linha}: {m}"[:int(corpo.w / 6.3)], 12, cor=cor_e, sombra=False)
            if dica:
                ui.texto(corpo.x + 20, y + 14, dica[:int(corpo.w / 6)], 11, cor=(170, 175, 190), sombra=False)
            y += 32

    def _texto_aplicado(self, j):
        fonte = self.srv.fonte or ""
        cab = "agente gerente" if j.alvo == "gerente" else f"modelo {j.modelo}"
        m = re.search(re.escape(cab) + r" \{\n(.*?)\n\}(?:\n|$)", fonte, re.S)
        return m.group(1) if m else None

    # --- janela de informação (tutorial) ----------------------------------------------------------------
    def _janela_info(self, ui, j, ent, aqui):
        tut = self.cena.servicos.get("tutorial")
        titulo, texto, codigo, rotulo = tut.conteudo() if tut else ("Informação", "", "", None)
        r = j.rect
        ui.texto(r.x + 10, r.y + 13, "Informação", 13, ancora="midleft", negrito=True, sombra=False)
        if tut and tut.ativo:
            ui.texto(r.x + 110, r.y + 13, f"tutorial {tut.passo + 1}/{tut.total}", 11, ancora="midleft",
                     cor=(170, 175, 190), sombra=False)
        elif tut and tut.em_missao:
            ui.texto(r.x + 110, r.y + 13, "missão", 11, ancora="midleft", cor=(255, 215, 90), sombra=False)
        if j.minimizada:
            return
        corpo = j.corpo()
        anterior = ui.surface.get_clip()
        ui.surface.set_clip(corpo)
        if aqui and ent.roda:
            j.rolagem = max(0, j.rolagem - ent.roda * 30)
        y = corpo.y + 8 - j.rolagem
        ui.texto(corpo.x + 12, y, titulo, 17, negrito=True, cor=(255, 215, 90), sombra=False)
        y += 28
        largura = max(20, int((corpo.w - 24) / 7.2))
        for par in texto.split("\n"):
            for l in (quebrar(par, largura) or [""]):
                ui.texto(corpo.x + 12, y, l, 13, sombra=False)
                y += 18
        if codigo:
            y += 4
            fonte = pygame.font.SysFont("consolas,couriernew", 13)
            cabe = max(20, (corpo.w - 36) // max(1, fonte.size("M")[0]))
            linhas = []                                  # quebra as linhas compridas (nada sai da janela)
            for l in codigo.split("\n"):
                recuo = ""
                while len(recuo + l) > cabe:
                    corte = l.rfind(" ", 0, cabe - len(recuo))
                    corte = corte if corte > 10 else cabe - len(recuo)
                    linhas.append(recuo + l[:corte])
                    l, recuo = l[corte:].lstrip(), "    "
                linhas.append(recuo + l)
            pygame.draw.rect(ui.surface, (16, 17, 22), (corpo.x + 10, y - 2, corpo.w - 20, 18 * len(linhas) + 8),
                             border_radius=4)
            for l in linhas:
                ui.surface.blit(fonte.render(l, True, (140, 210, 255)), (corpo.x + 18, y + 2))
                y += 18
            y += 10
        ui.surface.set_clip(anterior)
        if rotulo and botao(ui, (corpo.right - 130, corpo.bottom - 34, 118, 26), rotulo, aqui, ent,
                            cor=(70, 90, 140), tamanho=13):
            tut.avancar()
        if y > corpo.bottom - 4:                         # o texto não coube: dá para rolar
            ui.retangulo((corpo.right - 150, corpo.bottom - 22, 142, 18), (40, 44, 58), raio=4)
            ui.texto(corpo.right - 79, corpo.bottom - 13, "role para ver mais ▼", 11, ancora="center",
                     cor=(200, 205, 220), sombra=False)
        elif tut and (tut.ativo or tut.em_missao) and not rotulo:
            ui.texto(corpo.x + 12, corpo.bottom - 22, "objetivo em andamento...", 12, cor=(150, 200, 150),
                     sombra=False)

    # --- janela de saída (log) -------------------------------------------------------------------------
    def _janela_saida(self, ui, j, ent, aqui):
        r = j.rect
        ui.texto(r.x + 10, r.y + 13, "Saída", 13, ancora="midleft", negrito=True, sombra=False)
        if j.minimizada:
            return
        corpo = j.corpo()
        if aqui and ent.roda:
            j.rolagem = max(0, j.rolagem + ent.roda * 2)
        cabem = max(1, (corpo.h - 10) // 16)
        eventos = self.fab.eventos
        fim = max(0, len(eventos) - j.rolagem)
        y = corpo.y + 6
        for texto, tipo in eventos[max(0, fim - cabem):fim]:
            ui.texto(corpo.x + 8, y, texto[:int(corpo.w / 6.3)], 12, cor=COR_TIPO.get(tipo, COR_TIPO["info"]),
                     sombra=False)
            y += 16

    # --- tela de início ---------------------------------------------------------------------------------
    def _tela_inicio(self, ui):
        W, H = ui.largura, ui.altura
        ui.retangulo((0, 0, W, H), (12, 14, 20, 225), raio=0, bloquear=True)
        cx = W // 2
        ui.desenhar_imagem("Assets/Sprites/Itens/sorvete_misto.png", cx, H // 2 - 170, tamanho=110)
        ui.texto(cx, H // 2 - 90, "Fábrica de Sorvete", 46, ancora="center", negrito=True, cor=(255, 215, 90))
        ui.texto(cx, H // 2 - 45, "programe os robôs em AgentDSL para montar sorvetes", 17, ancora="center",
                 cor=(200, 205, 220))
        y = H // 2 + 10
        if self.fab.tem_save():
            if ui.botao((cx - 130, y, 260, 44), "Continuar", tamanho_texto=18):
                self._comecar()
            y += 54
        if ui.botao((cx - 130, y, 260, 44), "Novo jogo" if self.fab.tem_save() else "Começar", tamanho_texto=18):
            if self.fab.tem_save():
                self.fab.recomecar()
            self._comecar()
        ui.texto(cx, H - 60, "Ctrl+Enter executa · T árvore · F1 comandos · arraste as janelas pela barra", 13,
                 ancora="center", cor=(150, 155, 170))
        ui.texto(cx, H - 36, "Engine2D + AgentDSL · sprites Kenney (CC0)", 12, ancora="center", cor=(110, 115, 130))

    def _comecar(self):
        self.tela = None
        self.motor.pausado = False

    # --- Árvore --------------------------------------------------------------------------------------
    def _tela_arvore(self, ui):
        ent = self.motor.entrada
        W, H = ui.largura, ui.altura
        ui.retangulo((0, 0, W, H), (10, 12, 18, 240), raio=0, bloquear=True)
        ui.texto(24, 20, "Árvore de habilidades", 24, negrito=True)
        ui.texto(300, 27, f"você tem $ {int(self.fab.dinheiro)}", 17, cor=(255, 220, 90), negrito=True)
        if not self.fab.tem_estacao("balcao"):
            ui.texto(500, 29, "termine o tutorial para começar a comprar", 14, cor=(240, 170, 110))
        if ui.botao((W - 150, 16, 130, 30), "Fechar (T / Esc)", tamanho_texto=13):
            self.tela = None
        bw, bh = min(150, (W - 40) // 8 - 10), 62
        larg_col = (W - 40 - bw) / 7
        alt_lin = (H - 80 - bh - 20) / 6

        def pos(no):
            return 20 + no.coluna * larg_col, 64 + no.linha * alt_lin

        for chave, no in ARVORE.items():
            x, y = pos(no)
            for req in no.requisitos:
                rx, ry = pos(ARVORE[req])
                ui.linha((rx + bw, ry + bh / 2), (x, y + bh / 2),
                         (120, 200, 120) if self.fab.tem(req) else (62, 66, 80), 2)
        dica = None
        for chave, no in ARVORE.items():
            x, y = pos(no)
            r = pygame.Rect(x, y, bw, bh)
            est = self.fab.estado(chave)
            fundo = {"comprado": (36, 80, 48), "disponivel": (64, 62, 28), "caro": (40, 43, 56),
                     "bloqueado": (24, 26, 34)}[est]
            borda = {"comprado": (110, 200, 120), "disponivel": (255, 215, 90), "caro": (90, 95, 115),
                     "bloqueado": (52, 55, 66)}[est]
            hover = r.collidepoint(ent.mouse_tela)
            if hover:
                fundo = tuple(min(255, c + 18) for c in fundo)
            ui.retangulo(r, fundo, borda=borda, raio=7)
            cor_txt = (235, 235, 240) if est != "bloqueado" else (115, 118, 132)
            ui.texto(r.x + 8, r.y + 6, no.titulo[:20], 13, negrito=True, sombra=False, cor=cor_txt)
            nivel = self.fab.niveis[chave]
            if no.niveis > 1:
                ui.texto(r.right - 6, r.y + 7, f"{nivel}/{no.niveis}", 11, ancora="topright", sombra=False,
                         cor=cor_txt)
            for k, parte in enumerate(quebrar(no.desc, 24)[:2]):
                ui.texto(r.x + 8, r.y + 24 + 11 * k, parte, 10, sombra=False,
                         cor=(165, 170, 185) if est != "bloqueado" else (90, 93, 105))
            if est == "comprado":
                ui.texto(r.right - 6, r.bottom - 15, "ok", 12, ancora="topright", sombra=False, cor=(140, 230, 150),
                         negrito=True)
            else:
                ui.texto(r.right - 6, r.bottom - 16, f"$ {self.fab.custo(chave)}", 12, ancora="topright",
                         sombra=False, negrito=True, cor=(255, 220, 90) if est == "disponivel" else (140, 140, 150))
            if hover:
                req = ", ".join(ARVORE[q].titulo for q in no.requisitos) or "nada"
                dica = (no.desc, f"precisa de: {req}", r)
                if ent.clicou(1):
                    ent.consumir_clique()
                    if est == "disponivel":
                        self.fab.comprar(chave)
        if dica:
            desc, req, r = dica
            x = min(r.x, W - 340)
            y = r.bottom + 6 if r.bottom + 60 < H else r.y - 56
            ui.retangulo((x, y, 330, 50), (50, 54, 68), borda=(110, 115, 135), raio=6)
            ui.texto(x + 10, y + 7, desc, 13, sombra=False)
            ui.texto(x + 10, y + 27, req, 12, sombra=False, cor=(180, 185, 200))

    # --- Comandos (F1) --------------------------------------------------------------------------------
    def _tela_comandos(self, ui):
        ent = self.motor.entrada
        W, H = ui.largura, ui.altura
        ui.retangulo((0, 0, W, H), (10, 12, 18, 240), raio=0, bloquear=True)
        ui.texto(24, 18, "Comandos", 24, negrito=True)
        ui.texto(170, 26, "em branco: já liberado · cinza: compre na Árvore", 14, cor=(190, 195, 210))
        if ui.botao((W - 150, 16, 130, 30), "Fechar (F1 / Esc)", tamanho_texto=13):
            self.tela = None
        if ent.roda:
            self.rolagem_cmd = max(0, self.rolagem_cmd - ent.roda * 40)
        fonte = pygame.font.SysFont("consolas,couriernew", 13)
        colunas = 3 if W >= 1200 else 2
        col_w = (W - 40) // colunas
        anterior = ui.surface.get_clip()
        ui.surface.set_clip(pygame.Rect(0, 56, W, H - 56))
        secoes = []
        for sec, sint, expl, chave in COMANDOS:
            if not secoes or secoes[-1][0] != sec:
                secoes.append((sec, []))
            secoes[-1][1].append((sint, expl, chave))
        alturas = [0] * colunas
        for sec, itens in secoes:
            c = alturas.index(min(alturas))
            x, y = 20 + c * col_w, 64 + alturas[c] - self.rolagem_cmd
            ui.texto(x, y, sec, 16, negrito=True, cor=(255, 210, 110))
            y += 24
            for sint, expl, chave in itens:
                livre = chave is None or self.fab.tem(chave)
                ui.surface.blit(fonte.render(sint, True, (140, 210, 255) if livre else (90, 95, 110)), (x + 6, y))
                if expl or not livre:
                    ui.texto(x + 6, y + 16, expl if livre else f"[{ARVORE[chave].titulo}] {expl}", 11, sombra=False,
                             cor=(215, 218, 228) if livre else (100, 102, 115))
                y += 36
            alturas[c] = y + self.rolagem_cmd - 64 + 10
        ui.surface.set_clip(anterior)

    # --- menu ≡ ---------------------------------------------------------------------------------------
    def _tela_menu(self, ui):
        cx, cy = ui.largura // 2, ui.altura // 2
        ui.retangulo((cx - 190, cy - 140, 380, 310), borda=CORES["borda"], bloquear=True)
        ui.texto(cx, cy - 114, "Menu", 22, ancora="center", negrito=True)
        tut = self.cena.servicos.get("tutorial")
        if ui.botao((cx - 150, cy - 80, 300, 36), "Rever o tutorial"):
            if tut:
                tut.reiniciar()
            self.mostrar_janela("info")
            self.tela = None
        rot = "Clique de novo para APAGAR tudo" if self.confirmar else "Recomeçar do zero (novo jogo)"
        if ui.botao((cx - 150, cy - 34, 300, 36), rot, selecionado=self.confirmar):
            if self.confirmar:
                self.fab.recomecar()
            else:
                self.confirmar = True
        if ui.botao((cx - 150, cy + 12, 300, 36), "Organizar janelas"):
            self._organizar()
            self.tela = None
        if ui.botao((cx - 150, cy + 58, 300, 36), "Salvar agora"):
            self.fab.salvar_agora()
            self.fab.registrar("jogo salvo")
            self.tela = None
        if ui.botao((cx - 150, cy + 100, 145, 30), "Voltar ao jogo", tamanho_texto=14):
            self.tela = None
        if ui.botao((cx + 5, cy + 100, 145, 30), "Sair do jogo", tamanho_texto=14):
            self.sair()
        ui.texto(cx, cy + 150, "Esc de novo sai do jogo (o progresso é salvo)", 12, ancora="center",
                 cor=(170, 175, 190))

    def sair(self):
        self.fab.salvar_agora()
        if getattr(self.motor, "editor", None) is None:
            self.motor.rodando = False
        else:
            self.tela = None

    def _organizar(self):
        W, H = self.motor.largura, self.motor.altura
        y = TOPO + 20
        abertas = [j for j in self.codigos() if not j.fechada]
        for k, j in enumerate(abertas):
            j.rect = pygame.Rect(480 + 30 * k, H - 345 - 30 * (len(abertas) - 1 - k), 590, 330)
            j.minimizada = False
        for j in self.janelas:
            if j.tipo == "info":
                j.rect = pygame.Rect(12, H - 315, 458, 300)
            elif j.tipo == "saida":
                j.rect = pygame.Rect(12, H - 480, 458, 160)

    # --- "Novo!" -------------------------------------------------------------------------------------------
    def _tela_novidade(self, ui):
        no = ARVORE.get(self.novidade)
        if no is None:
            self.tela = None
            return
        linhas = no.novidade.split("\n")
        exemplo = no.exemplo.split("\n") if no.exemplo else []
        h = 130 + 20 * len(linhas) + (30 + 18 * len(exemplo) if exemplo else 0)
        cx, cy = ui.largura // 2, ui.altura // 2
        w = min(ui.largura - 40, 760)
        r = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
        ui.retangulo(r, (30, 33, 44), borda=(255, 215, 90), bloquear=True, raio=10)
        ui.texto(r.centerx, r.y + 26, f"Novo: {no.titulo}!", 24, ancora="center", negrito=True, cor=(255, 215, 90))
        y = r.y + 56
        for l in linhas:
            ui.texto(r.x + 22, y, l, 14, sombra=False)
            y += 20
        if exemplo:
            y += 8
            ui.texto(r.x + 22, y, "Exemplo:", 13, sombra=False, cor=(180, 185, 200))
            y += 20
            fonte = pygame.font.SysFont("consolas,couriernew", 13)
            for l in exemplo:
                ui.surface.blit(fonte.render(l, True, (140, 210, 255)), (r.x + 30, y))
                y += 18
        if ui.botao((r.centerx - 70, r.bottom - 48, 140, 34), "Legal!"):
            self.tela = None
