"""O corpo dos robôs: executa os comandos do programa UM DE CADA VEZ.

Um plano como ``+!produzir <- pegar_casquinha(medio); adicionar_sorvete(creme); entregar.`` põe três
comandos na FILA do robô. Cada comando anda sozinho até a estação certa, espera a estação ficar livre
e leva um tempo. Alguns podem FALHAR ao acaso (a casquinha quebra, o sorvete derrama...): a fila é
descartada, o robô percebe ``+falhou(Motivo)`` e o objetivo em andamento gera ``-!objetivo``.

``!objetivo`` no meio de um plano funciona como a pilha de intenções do Jason: os comandos que vêm
depois esperam o objetivo terminar.
"""
import math
from collections import deque

from engine2d import Componente, SpriteRenderer
from agentdsl.semantica import Assinatura
from engine2d.projeto import ACOES_DSL, acao_dsl
from Itens import (CALDAS, COBERTURAS, ICONES, MASSAS, PONTOS, TAMANHOS, TIPOS, atomo, icone_item, novo_item,
                   texto)

# comando: (estação, duração base em segundos)
COMANDOS = {
    "pegar_casquinha": ("armazem", 0.6), "devolver": ("armazem", 0.4), "jogar_fora": ("armazem", 0.3),
    "adicionar_sorvete": ("maquina", 1.2), "adicionar_massa": ("massas", 0.8), "bater": ("batedeira", 1.0),
    "adicionar_calda": ("caldas", 0.8), "adicionar_cobertura": ("coberturas", 0.7),
    "entregar": ("balcao", 0.5), "perguntar_pedido": ("balcao", 0.6), "passar_pedido": (None, 0.2),
    "deixar": (None, 0.3), "pegar_de": (None, 0.3), "esperar": (None, 0), "dancar": (None, 1.0),
}
FALHAS = {"pegar_casquinha": ("quebrou", 0.12), "adicionar_sorvete": ("derramou", 0.08),
          "adicionar_massa": ("caiu", 0.08), "bater": ("passou_do_ponto", 0.08),
          "adicionar_calda": ("entupiu", 0.08), "adicionar_cobertura": ("escorregou", 0.08)}
TEMPO_BATER = {"pouco": 1.0, "medio": 2.0, "bem": 3.0}
ESPERA_CLIENTE = 6.0


class Robo(Componente):
    CAMPOS = {"velocidade": "float"}
    velocidade = 135.0

    def iniciar(self):
        self.agente = self.obter("ComportamentoAgente")
        self.item = None             # o sorvete (dict) na mão
        self.pedidos = []            # pedidos que o robô sabe (perguntou no balcão ou recebeu de outro)
        self.em = None               # estação onde está parado
        self.t = 0.0
        self.entregas = 0
        self.fila = deque()          # comandos esperando: (nome, args)
        self.pilha = []              # [(fila_restante, nº de objetivos antes)]: o que fazer quando o objetivo acabar
        self.objetivos = []          # objetivos em andamento, do mais externo ao mais interno
        self.atual = None            # [nome, args, tempo_restante, estação, fase]
        self.ocupado = False
        self.esperando = ""
        self.aguardando = 0          # quadros esperando o plano de um objetivo chegar
        self.pausa = 0.0
        self.ligar_ao_iniciar = False
        self.falha_recente = 0.0     # para desenhar o "X" vermelho
        n = len(self.cena.com_tag("robo"))
        self.desvio = (((n - 1) % 4) - 1.5) * 18
        self.icone = self.cena.criar("item na mão", 0, 10, pai=self.gameobject, escala=0.5,
                                     componentes=[SpriteRenderer(imagem=ICONES["casquinha"], camada=7, visivel=False)])

    @property
    def fabrica(self):
        return self.cena.servicos["sorveteria"]

    @property
    def mult(self):
        return self.fabrica.mult_velocidade

    def _pulsar(self, nome, *args):
        if self.agente is not None and self.agente._iniciado:
            self.agente.pulsar(nome, tuple(args))

    # --- fila, objetivos e falhas --------------------------------------------------------------
    def enfileirar(self, nome, *args):
        if not self.fabrica.rodando:
            return
        self.fila.append((nome, args))
        self.ocupado = True
        self.aguardando = 0

    def objetivo_dsl(self, nome, args):
        """``!nome`` no programa: vira um marcador na fila. Quando o robô chegar nele, o objetivo começa."""
        if self.fabrica.rodando:
            self.fila.append(("!", (nome, tuple(args))))
            self.ocupado = True
            self.aguardando = 0
        return True

    def sem_plano_dsl(self, nome, args):
        self._falhar("sem_plano")

    def _soltar_estacao(self):
        if self.atual and self.atual[3] is not None and self.atual[3].ocupante is self:
            self.atual[3].ocupante = None
            self.atual[3].progresso = 0.0

    def parar(self):
        self._soltar_estacao()
        self.fila.clear()
        self.pilha.clear()
        self.objetivos.clear()
        self.atual = None
        self.ocupado = False
        self.esperando = ""
        self.pausa = 0.0
        self.aguardando = 0

    def ligar(self, objetivo=None):
        """Executar: o robô para o que estava fazendo e começa pelo primeiro objetivo da janela dele.
        O mundo continua como estava: se ele segurava uma casquinha, continua segurando (e não consegue
        pegar outra até devolver ou jogar fora); os pedidos que ele sabia continua sabendo."""
        self.parar()
        self._pulsar("ligado")
        if objetivo:
            self.objetivo_dsl(objetivo, ())

    def receber_pedido(self, cliente):
        self.pedidos.append(cliente)
        cliente["anotado_por"] = self.gameobject.nome
        self._pulsar("novo_pedido")

    def _falhar(self, motivo):
        """Um comando falhou. Como no Jason, a falha sobe pelos objetivos até achar um que tenha plano
        -!objetivo. Os objetivos de dentro são abandonados; o plano -!objetivo roda no lugar do objetivo
        que falhou e, quando ele termina, o robô CONTINUA o que vinha depois desse objetivo."""
        self._soltar_estacao()
        k = None
        if self.agente is not None and self.agente._iniciado:
            k = next((i for i in range(len(self.objetivos) - 1, -1, -1)
                      if self.agente.ag.planos.get(("-!", self.objetivos[i][0], len(self.objetivos[i][1])))), None)
        self.fila.clear()
        self.atual = None
        self.esperando = ""
        self.pausa = 0.4 / self.mult
        self.falha_recente = 1.2
        self.fabrica.falhas_comando += 1
        self.fabrica.contagem_falhas[motivo] = self.fabrica.contagem_falhas.get(motivo, 0) + 1
        self.fabrica.registrar(f"{self.gameobject.nome}: falhou ({motivo})", "falha")
        self._pulsar("falhou", atomo(motivo))
        if k is None:                         # ninguém trata a falha: o programa para
            self.pilha.clear()
            self.objetivos.clear()
            return
        nome, args = self.objetivos[k]
        quadro = max((i for i, (_, n) in enumerate(self.pilha) if n <= k), default=None)
        if quadro is None:
            self.pilha.clear()
        else:
            del self.pilha[quadro + 1:]       # mantém o que vinha DEPOIS do objetivo que falhou
        del self.objetivos[k + 1:]
        self.agente.ag.objetivo(nome, args, "-!")     # -!objetivo: o objetivo falhou
        self.ocupado = True
        self.aguardando = 3

    # --- execução ---------------------------------------------------------------------------------
    def _estacao(self, nome):
        return self.cena.servicos.get("estacoes", {}).get(nome)

    def _comecar(self, nome, args):
        if nome == "!":
            objetivo, vals = args
            if not self.fila and self.pilha:
                # "!g" no fim do plano (como em +!produzir <- ...; !produzir.): o plano atual já acabou,
                # então o novo objetivo volta direto para quem chamou (a pilha não cresce ao repetir).
                continuacao, n = self.pilha.pop()
            else:
                continuacao, n = self.fila, len(self.objetivos)
            nomes = [o[0] for o in self.objetivos[n:]]
            if objetivo in nomes:            # recursão: o objetivo recomeça
                del self.objetivos[n + nomes.index(objetivo):]
            self.objetivos.append((objetivo, vals))
            self.pilha.append((continuacao, n))
            self.fila = deque()
            self.aguardando = 3
            self.agente.ag.objetivo(objetivo, vals)
            return
        est_nome, dur = COMANDOS[nome]
        if nome in ("deixar", "pegar_de"):
            est_nome = args[0]
        est = self._estacao(est_nome) if est_nome else None
        if est_nome and est is None:
            return self._falhar("nao_existe")
        if est is not None and not est.disponivel:
            return self._falhar("nao_comprado")
        if nome == "esperar":
            dur = float(args[0])
        elif nome == "bater":
            dur = TEMPO_BATER.get(args[0], 1.0)
        self.atual = [nome, args, dur / (1 if nome == "esperar" else self.mult), est, "andar" if est else "fazer"]
        if est is not None:
            self.em = None

    def _andar(self, dt, est):
        tx, ty = est.ponto(self.desvio)
        x, y = self.transform.posicao_mundo
        dx, dy = tx - x, ty - y
        d = math.hypot(dx, dy)
        passo = self.velocidade * self.mult * dt
        if d <= passo:
            self.transform.x, self.transform.y = tx, ty
            self.em = est.nome_dsl
            self.transform.rotacao = 0
            return True
        self.transform.x += dx / d * passo
        self.transform.y += dy / d * passo
        if abs(dx) > 1:
            self.transform.escala_x = math.copysign(abs(self.transform.escala_x), dx)
        self.transform.rotacao = math.sin(self.t * 18) * 4
        return False

    def _avancar(self, dt):
        nome, args, _, est, fase = self.atual
        if fase == "andar":
            if not self._andar(dt, est):
                return
            self.atual[4] = fase = "fila" if not est.eh_bancada else "fazer"
        if fase == "fila":                       # espera a estação ficar livre
            if est.ocupante is not None and est.ocupante is not self:
                self.esperando = f"esperando a vez na {est.nome_dsl}"
                return
            erro = self._checar(nome, args)
            if erro:
                return self._falhar(erro)
            est.ocupante = self
            self.esperando = ""
            self.atual[4] = "fazer"
        elif fase == "fazer" and est is None and self.atual[2] == self._duracao_total():
            erro = self._checar(nome, args)
            if erro:
                return self._falhar(erro)
        self.atual[2] -= dt
        total = self._duracao_total()
        if est is not None and est.ocupante is self and total > 0:
            est.progresso = max(0.0, min(1.0, 1 - self.atual[2] / total))
        if nome == "dancar":
            self.transform.rotacao = (1 - max(0.0, self.atual[2]) * self.mult) * 360
        if self.atual[2] > 0:
            return
        resultado = self._executar(nome, args, est)
        if resultado == "esperar":
            return
        self._soltar_estacao()
        if resultado:
            return self._falhar(resultado)
        self.transform.rotacao = 0
        self.atual = None

    def _duracao_total(self):
        nome, args = self.atual[0], self.atual[1]
        if nome == "esperar":
            return float(args[0])
        base = TEMPO_BATER.get(args[0], 1.0) if nome == "bater" else COMANDOS[nome][1]
        return base / self.mult

    @staticmethod
    def _opcao(valor, validas, liberadas):
        if valor not in validas:
            return "opcao_invalida"
        if valor not in liberadas:
            return "opcao_bloqueada"
        return None

    def _checar(self, nome, args):
        """Confere se dá para fazer o comando (antes de começar). Devolve o motivo da falha ou None."""
        fab, item = self.fabrica, self.item
        a = args[0] if args else None
        if nome == "pegar_casquinha":
            return "maos_cheias" if item else self._opcao(a or "medio", TAMANHOS, fab.liberadas("tamanho"))
        if nome == "devolver":
            if not item:
                return "maos_vazias"
            return "nao_pode" if item["tipo"] or item["estragado"] else None
        if nome == "jogar_fora":
            return None                       # com as mãos vazias não faz nada (e não falha)
        if nome in ("adicionar_sorvete", "adicionar_massa", "bater", "adicionar_calda", "adicionar_cobertura",
                    "entregar"):
            if not item:
                return "sem_casquinha"
            if item["estragado"]:
                return "estragado"
            if nome == "adicionar_sorvete":
                return "ja_tem" if item["tipo"] else self._opcao(a, TIPOS, fab.liberadas("tipo"))
            if not item["tipo"]:
                return "sem_sorvete"
            if nome == "adicionar_massa":
                if item["ponto"]:
                    return "ja_batido"
                return "ja_tem" if item["massa"] else self._opcao(a, MASSAS, fab.liberadas("massa"))
            if nome == "bater":
                return "ja_batido" if item["ponto"] else self._opcao(a, PONTOS, PONTOS)
            if nome == "adicionar_calda":
                return "ja_tem" if item["calda"] else self._opcao(a, CALDAS, fab.liberadas("calda"))
            if nome == "adicionar_cobertura":
                if a in item["coberturas"] or len(item["coberturas"]) >= 2:
                    return "ja_tem"
                return self._opcao(a, COBERTURAS, fab.liberadas("cobertura"))
        return None

    def _executar(self, nome, args, est):
        """Faz o comando. Devolve None (deu certo), "esperar" (ainda não dá) ou o motivo da falha."""
        fab = self.fabrica
        a = args[0] if args else None
        falha = FALHAS.get(nome)
        azar = falha is not None and fab.sortear_falha(nome, falha[1])
        if nome == "pegar_casquinha":
            if azar:
                fab.efeito(self, "quebrou!")
                return "quebrou"
            self.item = novo_item(a or "medio", self.pedidos.pop(0) if self.pedidos else None)
        elif nome == "devolver":
            if self.item["ticket"]:
                self.pedidos.insert(0, self.item["ticket"])
            self.item = None
            fab.devolvidas += 1
        elif nome == "jogar_fora":
            if self.item is not None and self.item["tipo"]:
                fab.jogados += 1
            if self.item is not None and self.item["ticket"]:
                self.pedidos.insert(0, self.item["ticket"])     # o pedido continua valendo
            self.item = None
        elif nome == "adicionar_sorvete":
            if azar:
                self.item["estragado"] = True
                fab.efeito(self, "derramou!")
                return "derramou"
            self.item["tipo"] = a
        elif nome == "adicionar_massa":
            if azar:
                return "caiu"
            self.item["massa"] = a
        elif nome == "bater":
            if azar:
                i = PONTOS.index(a)
                self.item["ponto"] = PONTOS[i + 1] if i + 1 < len(PONTOS) else "demais"
                fab.efeito(self, "passou do ponto!")
                return "passou_do_ponto"
            self.item["ponto"] = a
        elif nome == "adicionar_calda":
            if azar:
                return "entupiu"
            self.item["calda"] = a
        elif nome == "adicionar_cobertura":
            if azar:
                return "escorregou"
            self.item["coberturas"].append(a)
        elif nome == "entregar":
            if self.item["ticket"] is None:
                return "sem_pedido"               # ninguém pediu esse sorvete: pergunte antes!
            valor = fab.entregar(self.item)
            if valor is None:
                self.item["ticket"] = None
                return "cliente_foi_embora"
            self.item = None
            self.esperando = ""
            if valor == 0:
                return "recusado"
            self.entregas += 1
            fab.vendas_robo[self.gameobject.nome] = fab.vendas_robo.get(self.gameobject.nome, 0) + 1
            self._pulsar("entregou", valor)
        elif nome == "perguntar_pedido":
            if self.pedidos or (self.item is not None and self.item["ticket"] is not None):
                return None                       # já sabe um pedido para fazer: não pergunta de novo
            cliente = fab.proximo_pedido(self)
            if cliente is None:
                self.esperando = "esperando cliente"
                return "esperar"                  # espera o próximo cliente chegar
            self.esperando = ""
            if self.item is not None and self.item["ticket"] is None:
                self.item["ticket"] = cliente
                cliente["anotado_por"] = self.gameobject.nome
                self._pulsar("novo_pedido")
            else:
                self.receber_pedido(cliente)
        elif nome == "passar_pedido":
            outro = fab.robo_por_nome(a)
            if outro is None or outro.obter("Robo") is None:
                return "nao_existe"
            if not self.pedidos:
                return "sem_pedido"
            fab.pedidos_passados += 1
            outro.obter("Robo").receber_pedido(self.pedidos.pop(0))
        elif nome == "deixar":
            if not self.item:
                return "maos_vazias"
            if est.item is not None:
                self.esperando = "bancada ocupada"
                return "esperar"
            est.item, self.item = self.item, None
            self.esperando = ""
        elif nome == "pegar_de":
            if self.item:
                return "maos_cheias"
            if est.item is None:
                return "vazia"
            self.item, est.item = est.item, None
            fab.pegas_bancada += 1
        return None

    # --- quadro -----------------------------------------------------------------------------------
    def atualizar(self, dt):
        self.t += dt
        self.falha_recente = max(0.0, self.falha_recente - dt)
        if self.ligar_ao_iniciar and self.agente is not None and self.agente._iniciado:
            objetivo = self.ligar_ao_iniciar if isinstance(self.ligar_ao_iniciar, str) else None
            self.ligar_ao_iniciar = False
            self.ligar(objetivo)
        if self.aguardando > 0:
            self.aguardando -= 1
        elif self.atual is None and self.pausa > 0:
            self.pausa -= dt
        elif self.atual is None and self.fila:
            self._comecar(*self.fila.popleft())
        elif self.atual is None and not self.fila and self.pilha:
            self.fila, n = self.pilha.pop()          # o objetivo acabou: volta ao que vinha depois
            del self.objetivos[n:]
        if self.atual is not None:
            self._avancar(dt)
        elif not self.fila and not self.pilha and self.ocupado and self.pausa <= 0 and self.aguardando <= 0:
            self.ocupado = False
            self.transform.rotacao = 0
            self._pulsar("terminou")
        r = self.icone.obter("SpriteRenderer")
        r.visivel = self.item is not None
        if self.item is not None:
            r.trocar_imagem(icone_item(self.item))
        if self.agente is not None and self.agente._iniciado:
            self.agente.perceber(self._percepcoes())

    def _percepcoes(self):
        fab, item = self.fabrica, self.item
        p = set(fab.percepcoes_mundo)
        if item is None:
            p.add(("livre", ()))
        else:
            p.add(("segurando", (atomo(item["tamanho"]),)))
            if item["estragado"]:
                p.add(("estragado", ()))
            if item["tipo"]:
                p.add(("tem_sorvete", (atomo(item["tipo"]),)))
            if item["massa"]:
                p.add(("tem_massa", (atomo(item["massa"]),)))
            if item["ponto"]:
                p.add(("batido", (atomo(item["ponto"]),)))
            if item["calda"]:
                p.add(("tem_calda", (atomo(item["calda"]),)))
            for c in item["coberturas"]:
                p.add(("tem_cobertura", (atomo(c),)))
        if self.em and self.atual is None:
            p.add(("esta_em", (atomo(self.em),)))
        cliente = (item or {}).get("ticket") or (self.pedidos[0] if self.pedidos else None)
        if cliente is not None and any(c is cliente for c in fab.clientes):
            ped = cliente["pedido"]
            p.add(("tem_pedido", ()))
            p.add(("pedido_tamanho", (atomo(ped["tamanho"]),)))
            p.add(("pedido_sabor", (atomo(ped["tipo"]),)))
            for chave, nome in (("massa", "pedido_massa"), ("ponto", "pedido_ponto"), ("calda", "pedido_calda")):
                if ped[chave]:
                    p.add((nome, (atomo(ped[chave]),)))
            for c in ped["coberturas"]:
                p.add(("pedido_cobertura", (atomo(c),)))
        return p

    def descricao(self):
        if self.atual:
            nome, args = self.atual[0], self.atual[1]
            base = f"{nome}({', '.join(texto(a) for a in args)})" if args else nome
            return base + (f" — {self.esperando}" if self.esperando else "")
        if self.objetivos and self.aguardando:
            return f"!{self.objetivos[-1][0]}"
        if not self.fabrica.rodando:
            return "desligado"
        return "parado (sem comandos)"

    def desenhar_ui(self, ui):
        x, y = ui.mundo_para_tela(*self.transform.posicao_mundo)
        painel = self.cena.servicos.get("painel")
        destacado = painel is not None and painel.robo_destacado is self
        ui.texto(x, y + 36, self.gameobject.nome, 11, ancora="center",
                 cor=(255, 230, 120) if destacado else (235, 235, 235))
        if self.item is not None and not self.item["estragado"]:
            icones = [self.item["massa"]] + ([f"calda_{self.item['calda']}"] if self.item["calda"] else []) \
                + self.item["coberturas"]
            for k, ic in enumerate([i for i in icones if i]):
                ui.desenhar_imagem(ICONES[ic], x + 16 + 11 * k, y - 22, tamanho=14)
        if self.pedidos or (self.item and self.item["ticket"] is not None):
            ui.retangulo((x - 26, y - 30, 10, 12), (255, 255, 255), raio=2)
        if self.esperando:
            ui.texto(x, y - 42, "...", 16, ancora="center", negrito=True)
        if self.falha_recente > 0:
            ui.texto(x, y - 44, "X", 22, ancora="center", negrito=True, cor=(255, 80, 80))
        if destacado:
            ui.circulo((x, y), 36, (255, 230, 120), 2)


def _robo(corpo):
    return corpo.obter("Robo") if corpo is not None else None


def _registrar_comando(nome, *tipos, descricao=""):
    def acao(corpo, agente, *args):
        r = _robo(corpo)
        if r:
            r.enfileirar(nome, *[a if isinstance(a, (int, float)) else texto(a) for a in args])
    acao_dsl(nome, *tipos, descricao=descricao)(acao)


_registrar_comando("pegar_casquinha", "atomo", descricao="pega uma casquinha no armazém (tamanho opcional)")
ACOES_DSL["pegar_casquinha"] = (Assinatura(("atomo",), ACOES_DSL["pegar_casquinha"][0].descricao, variadica=True),
                                ACOES_DSL["pegar_casquinha"][1])     # pegar_casquinha ou pegar_casquinha(grande)
_registrar_comando("devolver", descricao="devolve a casquinha vazia ao armazém")
_registrar_comando("jogar_fora", descricao="joga fora o que está na mão (lixeira do armazém)")
_registrar_comando("adicionar_sorvete", "atomo", descricao="máquina: creme, chocolate ou misto")
_registrar_comando("adicionar_massa", "atomo", descricao="estação de massas: morango, bolacha, castanha")
_registrar_comando("bater", "atomo", descricao="batedeira: pouco, medio ou bem")
_registrar_comando("adicionar_calda", "atomo", descricao="caldas: chocolate, caramelo, menta")
_registrar_comando("adicionar_cobertura", "atomo", descricao="coberturas: chantilly, cereja, mel, granulado")
_registrar_comando("entregar", descricao="entrega o sorvete no balcão")
_registrar_comando("perguntar_pedido", descricao="pergunta ao próximo cliente o que ele quer")
_registrar_comando("passar_pedido", "atomo", descricao="passa o pedido que sabe para outro robô")
_registrar_comando("deixar", "atomo", descricao="deixa o sorvete numa bancada: deixar(bancada1)")
_registrar_comando("pegar_de", "atomo", descricao="pega o sorvete de uma bancada")
_registrar_comando("esperar", "num", descricao="fica parado alguns segundos")
_registrar_comando("dancar", descricao="dá uma voltinha")


@acao_dsl("avisar", "atomo", "atomo", descricao="manda um recado para outro robô: avisar(robo2, pronto)")
def acao_avisar(corpo, agente, robo, recado):
    fab = corpo.cena.servicos["sorveteria"]
    alvo = fab.robo_por_nome(texto(robo))
    if alvo is None:
        r = _robo(corpo)
        if r:
            r._falhar("nao_existe")
        return
    comp = alvo.obter("ComportamentoAgente")
    if comp is not None and comp._iniciado:
        comp.pulsar("recado", (atomo(texto(recado)),))
        fab.recados += 1
