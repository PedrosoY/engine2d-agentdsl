"""A fábrica: clientes e pedidos (estilo Papa's Freezeria), dinheiro, árvore, salvamento e o HUD de cima."""
import json
import random
from pathlib import Path

from engine2d import Componente, SpriteRenderer
from engine2d.projeto import acao_dsl
from engine2d.ui import CORES
from Desbloqueios import ARVORE, custo
from Itens import (CALDAS, COBERTURAS, ICONES, MASSAS, PONTOS, PRECO_EXTRA, PRECO_OPCAO, PRECO_TAMANHO, TAMANHOS,
                   TIPOS, atomo, texto)

FILA_X, FILA_Y0, FILA_PASSO = 1150, 600, 62
MAX_FILA = 6
PACIENCIA = 150.0
CORES_CLIENTES = [(1, 1, 1, 1), (0.7, 0.85, 1, 1), (1, 0.75, 0.8, 1), (0.8, 1, 0.75, 1), (1, 0.9, 0.6, 1)]
ESTACOES_DA_ARVORE = {"massas": "massas", "batedeira": "batedeira", "caldas": "caldas", "coberturas": "coberturas"}
OPCOES = {   # categoria -> [(opção, desbloqueio ou None)]
    "tamanho": [("medio", None), ("pequeno", "tamanhos"), ("grande", "tamanhos")],
    "tipo": [("creme", None), ("chocolate", "tipo_chocolate"), ("misto", "tipo_misto")],
    "massa": [("morango", "massas"), ("bolacha", "bolacha"), ("castanha", "castanha")],
    "calda": [("chocolate", "caldas"), ("caramelo", "caramelo"), ("menta", "menta")],
    "cobertura": [("chantilly", "coberturas"), ("cereja", "cereja"), ("mel", "mel"), ("granulado", "granulado")],
}
ARQ_SAVE = Path("Saves/progresso.json")
CENTRO = (640, 480)


class Fabrica(Componente):
    CAMPOS = {"dinheiro_inicial": "int", "salvar": "bool"}
    dinheiro_inicial = 0
    salvar = True

    def iniciar(self):
        self.cena.servicos["sorveteria"] = self
        self.motor.tecla_estatisticas = "f10"      # o F3 aqui é "buscar o próximo" do editor de código
        self.srv = self.cena.servicos["agentes"]
        self._zerar()
        self.dados_salvos = self._carregar()
        self._aplicar_estacoes()
        for i in range(1 + self.niveis["robos"]):
            self._criar_robo(i == 0)

    def _zerar(self):
        self.dinheiro = self.dinheiro_inicial
        self.ganho_total = 0
        self.niveis = {k: 0 for k in ARVORE}
        self.extras = set()              # estações dadas pelo tutorial: maquina, balcao
        self.clientes = []               # {pedido, paciencia, go, anotado_por, valor}
        self.t_cliente = 2.0
        self.tempo = 0.0
        self.vendidos = self.perdidos = self.recusados = self.devolvidas = self.falhas = 0
        self.falhas_comando = self.jogados = 0     # contadores usados pelo tutorial e pelas missões
        self.pedidos_passados = self.recados = self.vendas_perfeitas = self.compras_gerente = 0
        self.pegas_bancada = 0
        self.contagem_falhas = {}             # motivo -> quantas vezes (tutorial)
        self.vendas_tipo = {}
        self.vendas_robo = {}
        self.eventos = []
        self.percepcoes_mundo = set()
        self.rodando = False
        self.execucoes = 0
        self.venceu = self.mostrar_vitoria = False
        self.t_salvar = 0.0
        self.forcar_quebra = 0           # o tutorial pede para a próxima casquinha quebrar

    # --- salvar / carregar -----------------------------------------------------------------
    def _carregar(self):
        if not self.salvar or not ARQ_SAVE.exists():
            return {}
        try:
            d = json.loads(ARQ_SAVE.read_text(encoding="utf-8"))
        except Exception:
            return {}
        for k in ("dinheiro", "ganho_total", "vendidos", "perdidos", "recusados", "execucoes"):
            setattr(self, k, d.get(k, 0))
        for k, v in d.get("niveis", {}).items():
            if k in self.niveis:
                self.niveis[k] = v
        self.extras = set(d.get("extras", []))
        self.venceu = bool(self.niveis["franquia"])
        return d

    def salvar_agora(self):
        if not self.salvar:
            return
        painel = self.cena.servicos.get("painel")
        tutorial = self.cena.servicos.get("tutorial")
        d = {k: getattr(self, k) for k in ("dinheiro", "ganho_total", "vendidos", "perdidos", "recusados",
                                            "execucoes")}
        d.update(niveis=self.niveis, extras=sorted(self.extras),
                 janelas=painel.estado_janelas() if painel else None,
                 tutorial=tutorial.passo if tutorial else 0, **(tutorial.estado() if tutorial else {}))
        ARQ_SAVE.parent.mkdir(exist_ok=True)
        ARQ_SAVE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

    def tem_save(self):
        return bool(self.dados_salvos)

    def recomecar(self):
        """Novo jogo: apaga o progresso e volta para a fábrica vazia."""
        if ARQ_SAVE.exists():
            ARQ_SAVE.unlink()
        self.parar()
        for g in self.robos()[1:]:
            g.destruir()
        for c in self.clientes:
            c["go"].destruir()
        self._zerar()
        self.dados_salvos = {}
        for est in self.cena.servicos.get("estacoes", {}).values():
            est.reiniciar()
        self._aplicar_estacoes()
        primeiro = self.robos()[0]
        r = primeiro.obter("Robo")
        r.item, r.pedidos = None, []
        primeiro.transform.x, primeiro.transform.y = CENTRO
        for s in ("painel", "tutorial"):
            obj = self.cena.servicos.get(s)
            if obj:
                obj.recomecar()

    # --- estações e opções liberadas ---------------------------------------------------------------
    def _aplicar_estacoes(self):
        ativas = {"armazem"} | self.extras
        ativas |= {est for chave, est in ESTACOES_DA_ARVORE.items() if self.niveis[chave]}
        ativas |= {f"bancada{i}" for i in range(1, self.niveis["bancadas"] + 1)}
        for nome in ("armazem", "maquina", "balcao", "massas", "batedeira", "caldas", "coberturas",
                     "bancada1", "bancada2", "bancada3"):
            go = self.cena.encontrar(nome)
            if go is not None:
                go.ativo = nome in ativas

    def liberar_estacao(self, nome):
        self.extras.add(nome)
        self._aplicar_estacoes()
        if nome == "balcao":
            self.t_cliente = 0.5

    def tem_estacao(self, nome):
        go = self.cena.encontrar(nome)
        return go is not None and go.ativo

    def liberadas(self, categoria):
        return [op for op, chave in OPCOES[categoria] if chave is None or self.niveis.get(chave)]

    def tem(self, chave):
        return self.niveis.get(chave, 0) > 0

    @property
    def mult_velocidade(self):
        return 1 + 0.3 * self.niveis["velocidade"]

    def sortear_falha(self, comando, chance):
        if comando == "pegar_casquinha" and self.forcar_quebra:
            self.forcar_quebra -= 1
            self.falhas += 1
            return True
        tut = self.cena.servicos.get("tutorial")
        if tut is not None and tut.ativo and tut.passo < tut.passo_sem_azar:
            return False          # no começo do tutorial só falha o que ele mostra de propósito
        if random.random() < chance * 0.6 ** self.niveis["manutencao"]:
            self.falhas += 1
            return True
        return False

    def efeito(self, robo, texto_efeito):
        from Comum import criar_texto_flutuante
        x, y = robo.transform.posicao_mundo
        criar_texto_flutuante(self.cena, x, y + 40, texto_efeito, cor=(255, 110, 110))

    def robos(self):
        return [g for g in self.cena.com_tag("robo") if not g.destruido]

    def robo_por_nome(self, nome):
        return next((g for g in self.robos() if g.nome == nome), None)

    def registrar(self, texto_evento, tipo="info"):
        self.eventos.append((texto_evento, tipo))
        del self.eventos[:-80]

    # --- executar / parar -------------------------------------------------------------------------
    def ligar(self, nomes=None, objetivos=None):
        """Liga os robôs (todos ou só os da lista ``nomes``). ``objetivos``: robô -> primeiro objetivo."""
        self.rodando = True
        self.execucoes += 1
        for g in self.robos():
            if nomes is None or g.nome in nomes:
                r = g.obter("Robo")
                if r is not None:
                    r.ligar((objetivos or {}).get(g.nome))

    def parar(self, nomes=None):
        for g in self.robos():
            if nomes is None or g.nome in nomes:
                r = g.obter("Robo")
                if r is not None:
                    r.parar()
        if nomes is None:
            self.rodando = False

    # --- árvore -----------------------------------------------------------------------------------
    def custo(self, chave):
        return custo(chave, self.niveis[chave])

    def estado(self, chave):
        """'comprado' | 'disponivel' | 'caro' | 'bloqueado'."""
        no = ARVORE[chave]
        if self.niveis[chave] >= no.niveis:
            return "comprado"
        if not all(self.niveis[r] for r in no.requisitos) or not self.tem_estacao("balcao"):
            return "bloqueado"
        return "disponivel" if self.dinheiro >= self.custo(chave) else "caro"

    def comprar(self, chave, quem="você"):
        if chave not in ARVORE:
            return False, "nao_existe"
        est = self.estado(chave)
        if est != "disponivel":
            return False, "sem_dinheiro" if est == "caro" else "nao_pode"
        self.dinheiro -= self.custo(chave)
        self.niveis[chave] += 1
        self._aplicar_estacoes()
        if chave == "robos":
            self._criar_robo(False)
        if chave == "franquia":
            self.venceu = self.mostrar_vitoria = True
        self.registrar(f"{quem} comprou {ARVORE[chave].titulo}", "compra")
        if quem != "você":
            self.compras_gerente += 1
        tut = self.cena.servicos.get("tutorial")
        if tut is not None:
            tut.ao_comprar(chave)
        painel = self.cena.servicos.get("painel")
        if painel is not None:
            painel.ao_comprar(chave, mostrar=quem == "você")
        self.salvar_agora()
        return True, ""

    def _criar_robo(self, primeiro):
        n = len(self.robos()) + 1
        x, y = CENTRO if primeiro else (CENTRO[0] + random.uniform(-60, 60), CENTRO[1] + random.uniform(-40, 40))
        go = self.cena.instanciar("Assets/Prefabs/robo.prefab", x, y)
        go.nome = f"robo{n}"
        from agentdsl.componente import ComportamentoAgente
        painel = self.cena.servicos.get("painel")
        modelo = painel.modelo_do_robo(go.nome) if painel else next(iter(self.srv.sis.modelos), "robo")
        comp = ComportamentoAgente(modelo=modelo)
        comp.manter_nome = True
        go.adicionar(comp)
        r = go.obter("Robo")
        if r is not None and self.rodando and not primeiro and painel is not None:
            r.ligar_ao_iniciar = painel.primeiro_objetivo_do_robo(go.nome) or True
        return go

    # --- clientes e pedidos -------------------------------------------------------------------------
    def _novo_pedido(self):
        ped = {"tamanho": random.choice(self.liberadas("tamanho")), "tipo": random.choice(self.liberadas("tipo")),
               "massa": None, "ponto": None, "calda": None, "coberturas": []}
        if self.tem_estacao("massas"):
            ped["massa"] = random.choice(self.liberadas("massa"))
        if self.tem_estacao("batedeira"):
            ped["ponto"] = random.choice(PONTOS)
        if self.tem_estacao("caldas"):
            ped["calda"] = random.choice(self.liberadas("calda"))
        if self.tem_estacao("coberturas"):
            ops = self.liberadas("cobertura")
            ped["coberturas"] = random.sample(ops, min(len(ops), random.choice((1, 1, 2))))
        return ped

    def valor_pedido(self, ped):
        v = PRECO_TAMANHO[ped["tamanho"]]
        extras = [ped["massa"], ped["ponto"], ped["calda"]] + ped["coberturas"]
        v += PRECO_EXTRA * sum(1 for e in extras if e)
        v += sum(PRECO_OPCAO.get(o, 0) for o in [ped["tipo"], ped["massa"], ped["calda"]] + ped["coberturas"])
        return int(round(v * (1 + 0.25 * self.niveis["marketing"])))

    @staticmethod
    def acerto(item, ped):
        """Fração das etapas do pedido que o sorvete acertou (0..1)."""
        pares = [(item["tamanho"], ped["tamanho"]), (item["tipo"], ped["tipo"])]
        for k in ("massa", "ponto", "calda"):
            if ped[k] or item[k]:
                pares.append((item[k], ped[k]))
        certos = sum(1 for a, b in pares if a == b)
        total = len(pares)
        pedidas, feitas = set(ped["coberturas"]), set(item["coberturas"])
        certos += len(pedidas & feitas)
        total += len(pedidas | feitas)
        return certos / total if total else 0.0

    def _novo_cliente(self):
        ped = self._novo_pedido()
        go = self.cena.criar("cliente", FILA_X + 60, FILA_Y0 - FILA_PASSO * len(self.clientes), tag="cliente",
                             escala=3.4, componentes=[SpriteRenderer(
                                 imagem="Assets/Sprites/Personagens/cliente.png", camada=3,
                                 cor=random.choice(CORES_CLIENTES))])
        self.clientes.append({"pedido": ped, "paciencia": PACIENCIA, "go": go, "anotado_por": None,
                              "valor": self.valor_pedido(ped)})

    def proximo_pedido(self, robo):
        for c in self.clientes:
            if c["anotado_por"] is None:
                c["anotado_por"] = robo.gameobject.nome
                return c
        return None

    def entregar(self, item):
        """Entrega o sorvete. Devolve None (sem cliente), 0 (recusado) ou o valor pago."""
        cliente = next((c for c in self.clientes if c is item["ticket"]), None)
        if cliente is None:
            return None                     # o cliente cansou de esperar e foi embora
        nota = self.acerto(item, cliente["pedido"])
        from Comum import criar_texto_flutuante
        x, y = cliente["go"].transform.posicao_mundo
        if nota < 0.4:
            self.recusados += 1
            criar_texto_flutuante(self.cena, x, y + 30, "eca!", cor=(255, 110, 110))
            self.registrar(f"cliente recusou o sorvete (acertou {int(nota * 100)}%)", "falha")
            return 0
        valor = int(round(cliente["valor"] * nota * (1.2 if nota == 1 else 1)))
        self.clientes.remove(cliente)
        cliente["go"].destruir()
        self.dinheiro += valor
        self.ganho_total += valor
        self.vendidos += 1
        self.vendas_tipo[item["tipo"]] = self.vendas_tipo.get(item["tipo"], 0) + 1
        if nota == 1:
            self.vendas_perfeitas += 1
        criar_texto_flutuante(self.cena, x, y + 30, f"+${valor}" + (" perfeito!" if nota == 1 else ""),
                              cor=(255, 225, 90))
        return valor

    # --- quadro --------------------------------------------------------------------------------------
    def atualizar(self, dt):
        self.tempo += dt
        if self.tem_estacao("balcao"):
            self.t_cliente -= dt
            if self.t_cliente <= 0:
                # com 1 robô os clientes vêm devagar; cada robô a mais traz mais gente
                robos = len(self.robos())
                base = max(6.0, 24.0 - 5.0 * (robos - 1))
                self.t_cliente = random.uniform(0.8, 1.2) * base / (1 + 0.3 * self.niveis["marketing"])
                if len(self.clientes) < min(MAX_FILA, 2 + robos):
                    self._novo_cliente()
        for c in list(self.clientes):
            c["paciencia"] -= dt
            if c["paciencia"] <= 0:
                self.clientes.remove(c)
                c["go"].destruir()
                self.perdidos += 1
                for g in self.robos():          # quem sabia esse pedido esquece
                    r = g.obter("Robo")
                    if r is not None and any(x is c for x in r.pedidos):
                        r.pedidos = [x for x in r.pedidos if x is not c]
        for i, c in enumerate(self.clientes):      # a fila anda
            t = c["go"].transform
            alvo_y = FILA_Y0 - FILA_PASSO * i
            t.x += (FILA_X - t.x) * min(1, 6 * dt)
            t.y += (alvo_y - t.y) * min(1, 6 * dt)
        self.t_salvar += dt
        if self.t_salvar > 15:
            self.t_salvar = 0
            self.salvar_agora()
        self._atualizar_percepcoes()

    def _atualizar_percepcoes(self):
        p = {("fila", (sum(1 for c in self.clientes if c["anotado_por"] is None),))}
        for nome, est in self.cena.servicos.get("estacoes", {}).items():
            if est.eh_bancada and est.disponivel:
                p.add(("na_bancada", (atomo(nome),)) if est.item is not None else ("bancada_livre", (atomo(nome),)))
        self.percepcoes_mundo = p
        gerente = self.srv.sis.agentes.get("gerente") if self.srv.sis else None
        if gerente is not None and gerente.corpo is not None and self.rodando:
            pg = set(p)
            pg.add(("dinheiro", (int(self.dinheiro),)))
            pg.add(("robos", (len(self.robos()),)))
            pg.add(("clientes", (len(self.clientes),)))
            for chave in ARVORE:
                if self.estado(chave) in ("disponivel", "caro"):
                    pg.add(("preco", (atomo(chave), self.custo(chave))))
            gerente.corpo.perceber(pg)

    # --- HUD: balões dos pedidos e barra de cima ---------------------------------------------------
    def desenhar_ui(self, ui):
        for c in self.clientes:
            self._desenhar_pedido(ui, c)
        painel = self.cena.servicos.get("painel")
        if painel is not None and painel.tela == "inicio":
            return
        W = ui.largura
        ui.retangulo((0, 0, W, 44), (24, 26, 34, 245), raio=0, bloquear=True)
        ui.texto(12, 22, f"$ {int(self.dinheiro)}", 24, cor=(255, 220, 90), ancora="midleft", negrito=True)
        ui.texto(118, 9, f"vendidos {self.vendidos}", 12, cor=(200, 200, 210))
        ui.texto(118, 24, f"perdidos {self.perdidos + self.recusados} · falhas {self.falhas}", 11,
                 cor=(160, 160, 170))
        if painel is not None:
            x = 280
            for rotulo, acao, larg, sel in (
                    ("+ Janela de código", painel.nova_janela, 150, False),
                    ("Árvore (T)", lambda: painel.alternar("arvore"), 100, painel.tela == "arvore"),
                    ("Comandos (F1)", lambda: painel.alternar("comandos"), 116, painel.tela == "comandos"),
                    ("Informação", lambda: painel.mostrar_janela("info"), 100, False),
                    ("Saída", lambda: painel.mostrar_janela("saida"), 64, False),
                    ("≡", lambda: painel.alternar("menu"), 40, painel.tela == "menu")):
                if ui.botao((x, 8, larg, 28), rotulo, tamanho_texto=13, selecionado=sel):
                    acao()
                x += larg + 6
        for i, v in enumerate((1.0, 2.0, 4.0)):
            if ui.botao((W - 196 + i * 46, 9, 42, 26), f"x{v:g}", selecionado=self.motor.escala_tempo == v,
                        tamanho_texto=13):
                self.motor.escala_tempo = v
        if ui.botao((W - 54, 9, 46, 26), "||" if not self.motor.pausado else ">", tamanho_texto=13,
                    dica="pausar o tempo"):
            self.motor.pausado = not self.motor.pausado
        if self.mostrar_vitoria:
            ui.sobrepor(self._janela_vitoria)

    def _desenhar_pedido(self, ui, c):
        """Balão com o pedido do cliente: ícones de cada etapa."""
        ped = c["pedido"]
        x, y = ui.mundo_para_tela(*c["go"].transform.posicao_mundo)
        icones = [ICONES[ped["tipo"]]]
        if ped["massa"]:
            icones.append(ICONES[ped["massa"]])
        if ped["calda"]:
            icones.append(ICONES[f"calda_{ped['calda']}"])
        icones += [ICONES[k] for k in ped["coberturas"]]
        w = 26 + 20 * len(icones)
        bx = x - 40 - w
        ui.retangulo((bx, y - 24, w, 40), (255, 255, 255, 238), raio=8)
        tam = {"pequeno": "P", "medio": "M", "grande": "G"}[ped["tamanho"]]
        ui.texto(bx + 10, y - 4, tam, 14, ancora="midleft", negrito=True, cor=(60, 60, 70), sombra=False)
        for k, img in enumerate(icones):
            ui.desenhar_imagem(img, bx + 34 + 20 * k, y - 8, tamanho=18)
        if ped["ponto"]:
            ui.texto(bx + 34, y + 9, f"batido: {ped['ponto']}", 10, ancora="midleft", cor=(70, 70, 90),
                     sombra=False)
        if c["anotado_por"]:
            ui.texto(bx + w - 4, y - 22, c["anotado_por"], 9, ancora="topright", cor=(40, 120, 60), sombra=False)
        ui.barra((bx, y + 18, w, 4), c["paciencia"] / PACIENCIA,
                 cor=CORES["verde"] if c["paciencia"] > 35 else CORES["vermelho"])

    def _janela_vitoria(self, ui):
        cx, cy = ui.largura // 2, ui.altura // 2
        ui.retangulo((cx - 260, cy - 100, 520, 200), borda=CORES["borda"], bloquear=True)
        ui.texto(cx, cy - 58, "Franquia aberta!", 32, ancora="center", negrito=True, cor=CORES["verde"])
        ui.texto(cx, cy - 16, f"Você faturou ${self.ganho_total} e vendeu {self.vendidos} sorvetes.", 15,
                 ancora="center")
        if ui.botao((cx - 80, cy + 30, 160, 36), "Continuar"):
            self.mostrar_vitoria = False


# --- ações da DSL do gerente (desbloqueio Gerência) ------------------------------------------------
@acao_dsl("comprar", "atomo", descricao="compra um item da árvore: robos, velocidade, manutencao, ...")
def acao_comprar(corpo, agente, item):
    fab = corpo.cena.servicos["sorveteria"]
    ok, motivo = fab.comprar(texto(item), quem=agente.nome)
    if not ok and corpo is not None:
        corpo.pulsar("falhou", (atomo(motivo),))
