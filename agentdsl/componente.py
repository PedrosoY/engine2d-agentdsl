"""Integração da AgentDSL com a engine:  Ação → Engine 2D → GameObject.

* ``ServicoAgentes`` (um por cena): compila o .agt, roda o ciclo de raciocínio de
  todos os agentes em ``atualizar_tardio`` (depois que os componentes do jogo
  geraram as percepções do quadro), cuida de temporizadores e invocações.
* ``ComportamentoAgente`` (um por GameObject controlado): liga o objeto a um
  agente da DSL. Executa as ações genéricas (mover, perseguir, cor...) e recebe
  percepções do jogo, que viram crenças — e só as MUDANÇAS viram eventos.

A engine continua sem saber o que é crença ou plano; a DSL continua sem saber o que
é OpenGL. As ações específicas de cada jogo (atirar, recompensa...) são registradas
pelo jogo junto com a assinatura, para a análise semântica conferir aridade e tipos.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from engine2d.componentes import CorpoRigido, SpriteRenderer
from engine2d.objeto import Componente

from .erros import ErroCompilacao
from .interpretador import Simbolo, SistemaAgentes, formatar_crenca
from .semantica import ACOES_ENGINE


class ServicoAgentes(Componente):
    """Roda os agentes de um arquivo .agt. Num projeto: um objeto com este componente,
    campo ``arquivo`` = "Assets/Agentes/x.agt". Ações extras vêm dos scripts (@acao_dsl)."""

    CAMPOS = {"arquivo": "str"}
    arquivo = ""
    MENU = "AgentDSL"

    def __init__(self, fonte: str | None = None, acoes_jogo: dict | None = None,
                 percepcoes: dict | None = None, alvos=(), prefabs: dict | None = None, **campos):
        """
        acoes_jogo: nome → (Assinatura, função(comportamento_ou_None, agente, *args))
        percepcoes: (nome, aridade) → tipos; crenças que o JOGO adiciona/remove
        prefabs:    modelo da DSL → nome do prefab da cena usado para criar o corpo
        """
        super().__init__(**campos)
        from engine2d.projeto import ACOES_DSL, ALVOS_DSL, PERCEPCOES_DSL
        self.fonte = fonte
        self.acoes_jogo = dict(ACOES_DSL if acoes_jogo is None else acoes_jogo)
        self.percepcoes = dict(PERCEPCOES_DSL if percepcoes is None else percepcoes)
        self.nomes_percepcoes = {n for n, _ in self.percepcoes}
        self.alvos = tuple(alvos) or tuple(ALVOS_DSL)
        self.prefabs = dict(prefabs or {})
        self.sis: SistemaAgentes | None = None
        self.temporizadores: list[list] = []     # [segundos_restantes, agente, crença]
        self.series: list[list] = []             # [modelo, restantes, intervalo, t, origem]
        self.ponto_de_invocacao = None           # f(modelo) -> (x, y), definido pelo jogo
        self.ao_invocar = None                   # f(go_novo, comportamento_origem | None)
        self.pode_invocar = None                 # f(modelo) -> bool (limite de inimigos, etc.)
        self.ao_registrar = None                 # f(linha, tipo) para o log do jogo
        self.erros: list[str] = []

    # --- ciclo ---------------------------------------------------------------
    def iniciar(self):
        if self.fonte is None:
            self.fonte = Path(self.arquivo).read_text(encoding="utf-8-sig")
        acoes = {**ACOES_ENGINE, **{n: a for n, (a, _) in self.acoes_jogo.items()}}
        try:
            self.sis = SistemaAgentes(self.fonte, ambiente=self, acoes=acoes, percepcoes=self.percepcoes,
                                      alvos=self.alvos, arquivo=self.arquivo or "<fonte>")
        except ErroCompilacao as e:
            self.erros = [d.formatar(self.fonte, self.arquivo or "<fonte>") for d in e.diagnosticos]
            raise
        self.sis.ao_registrar = self._log
        self.cena.servicos["agentes"] = self
        self._criar_agentes_unicos()
        self.sis.iniciar()   # crenças iniciais dos agentes únicos → eventos +b

    def _criar_agentes_unicos(self):
        # Agentes únicos (sem "modelo") ganham um GameObject próprio para aparecerem
        # na hierarquia e no inspector. Se tiverem sprite declarado, ele é criado.
        for ag in list(self.sis.agentes.values()):
            go = self.cena.criar(f"agente {ag.nome}", tag="agente")
            d = ag.decl.sprite
            if d is not None:
                go.transform.x, go.transform.y = d.x, d.y
                go.adicionar(SpriteRenderer(imagem=d.imagem, camada=d.camada))
            go.adicionar(ComportamentoAgente(agente=ag.nome))

    # --- trocar o programa com o jogo rodando ------------------------------------
    def compilar(self, fonte: str):
        """Só compila (léxico, sintático, semântico). Devolve (sistema | None, diagnósticos)."""
        acoes = {**ACOES_ENGINE, **{n: a for n, (a, _) in self.acoes_jogo.items()}}
        try:
            sis = SistemaAgentes(fonte, ambiente=self, acoes=acoes, percepcoes=self.percepcoes,
                                 alvos=self.alvos, arquivo=self.arquivo or "<fonte>")
        except ErroCompilacao as e:
            return None, e.diagnosticos
        return sis, sis.avisos

    def recompilar(self, fonte: str):
        """Compila um programa novo e, se não tiver erros, troca o programa de TODOS os agentes
        sem reiniciar o jogo: cada objeto com ``modelo`` ganha uma instância nova do mesmo modelo
        (as crenças recomeçam e as percepções voltam no próximo quadro); os agentes únicos são
        recriados. Devolve (ok, diagnósticos)."""
        novo, diags = self.compilar(fonte)
        if novo is None:
            return False, diags
        self.fonte = fonte
        self.sis = novo
        novo.ao_registrar = self._log
        self.temporizadores.clear()
        self.series.clear()
        for go in list(self.cena.objetos):
            c = go.obter(ComportamentoAgente)
            if c is None or not c._iniciado or go.destruido:
                continue
            if c.agente:
                self.cena._destruir_agora(go)
            else:
                self.religar(c, c.modelo)
        self._criar_agentes_unicos()
        self.cena.iniciar_pendentes()
        novo.iniciar()
        return True, diags

    def religar(self, comp, modelo: str) -> str:
        """Liga o objeto a uma instância nova de ``modelo`` (usa o primeiro modelo se ele não existir)."""
        if modelo not in self.sis.modelos:
            if not self.sis.modelos:
                return comp.modelo
            novo_nome = next(iter(self.sis.modelos))
            self._log(f"[{comp.gameobject.nome}] modelo '{modelo}' não existe mais; usando '{novo_nome}'", "erro")
            modelo = novo_nome
        ag = self.sis.criar_instancia(modelo, nome=comp.gameobject.nome)
        ag.corpo = comp
        comp.ag = ag
        comp.modelo = modelo
        comp._pulsos = []
        comp.comportamento = None
        comp.giro = 0.0
        return modelo

    def trocar_modelo(self, comp, modelo: str) -> str:
        """Muda o modelo (o "programa") de um objeto já existente."""
        if getattr(comp, "ag", None) is not None:
            self.sis.remover_instancia(comp.ag)
        return self.religar(comp, modelo)

    def _log(self, linha, tipo):
        if self.ao_registrar:
            self.ao_registrar(linha, tipo)

    def atualizar_tardio(self, dt):
        for t in self.temporizadores:
            t[0] -= dt
        vencidos = [t for t in self.temporizadores if t[0] <= 0]
        if vencidos:
            self.temporizadores = [t for t in self.temporizadores if t[0] > 0]
            for _, ag, crenca in vencidos:
                if ag.vivo:
                    ag.adicionar(crenca, ())
        for s in list(self.series):
            s[3] -= dt
            while s[3] <= 0 and s[1] > 0:
                self.invocar(s[0], 1, s[4])
                s[1] -= 1
                s[3] += s[2]
            if s[1] <= 0:
                self.series.remove(s)
        self.sis.passo()

    # --- criação de agentes com corpo --------------------------------------------
    def invocar(self, modelo: str, n: int = 1, origem=None) -> list:
        """Cria N GameObjects controlados por instâncias do modelo."""
        criados = []
        for _ in range(int(n)):
            if self.pode_invocar is not None and not self.pode_invocar(modelo):
                break
            if origem is not None and origem.gameobject is not None and not origem.gameobject.destruido:
                ox, oy = origem.transform.posicao_mundo
                x, y = ox + random.uniform(-12, 12), oy + random.uniform(-12, 12)
            elif self.ponto_de_invocacao:
                x, y = self.ponto_de_invocacao(modelo)
            else:   # padrão: na borda da área que a câmera mostra (nasce "fora da tela")
                x, y = self._borda_da_camera()
            go = self.criar_corpo(modelo, x, y)
            if self.ao_invocar:
                self.ao_invocar(go, origem)
            criados.append(go)
        return criados

    def _borda_da_camera(self):
        m = self.motor
        if m is None:
            return random.uniform(0, 800), random.uniform(0, 600)
        cam = m.camera
        hw, hh = cam.largura / (2 * cam.zoom) + 30, cam.altura / (2 * cam.zoom) + 30
        lado = random.randrange(4)
        if lado < 2:
            return cam.x + random.uniform(-hw, hw), cam.y + (hh if lado == 0 else -hh)
        return cam.x + (hw if lado == 2 else -hw), cam.y + random.uniform(-hh, hh)

    def criar_corpo(self, modelo: str, x: float, y: float):
        prefab = self.prefabs.get(modelo)
        arq_prefab = Path("Assets/Prefabs") / f"{modelo}.prefab"   # convenção dos projetos
        if prefab is None and arq_prefab.exists():
            import json
            prefab = json.loads(arq_prefab.read_text(encoding="utf-8"))
        if prefab is not None:
            go = self.cena.instanciar(prefab, x, y)
        else:
            go = self.cena.criar(modelo, x, y)
            d = self.sis.modelos[modelo].sprite
            if d is not None:
                go.adicionar(SpriteRenderer(imagem=d.imagem, camada=d.camada))
        comp = go.obter(ComportamentoAgente)
        if comp is None:
            go.adicionar(ComportamentoAgente(modelo=modelo))
        else:                    # o prefab já traz o componente (com os campos ajustados no Inspector)
            comp.modelo, comp.agente = modelo, ""
        return go

    # --- ações vindas do interpretador ----------------------------------------------
    # --- objetivos (+!g): o corpo pode decidir quando o objetivo começa ------------------------------
    def _gancho_corpo(self, agente, metodo):
        corpo = getattr(agente, "corpo", None)
        if corpo is None or corpo.gameobject is None:
            return None
        for comp in corpo.gameobject.componentes:
            f = getattr(comp, metodo, None)
            if f is not None:
                return f
        return None

    def objetivo(self, agente, nome: str, args: tuple) -> bool:
        """``!nome`` no corpo de um plano. Se um componente do objeto tiver ``objetivo_dsl``, ele cuida
        (ex.: o robô só começa o objetivo depois dos comandos anteriores). Devolve True se cuidou."""
        f = self._gancho_corpo(agente, "objetivo_dsl")
        return bool(f and f(nome, args))

    def sem_plano(self, agente, nome: str, args: tuple) -> None:
        f = self._gancho_corpo(agente, "sem_plano_dsl")
        if f:
            f(nome, args)

    def executar(self, agente, nome: str, args: list) -> None:
        corpo = agente.corpo
        if nome in self.acoes_jogo:
            self.acoes_jogo[nome][1](corpo, agente, *args)
        elif nome == "temporizador":
            self.temporizadores.append([float(args[0]), agente, _nome(args[1])])
        elif nome == "invocar":
            self.invocar(_nome(args[0]), int(args[1]))
        elif nome == "invocar_aqui":
            self.invocar(_nome(args[0]), int(args[1]), origem=corpo)
        elif nome == "invocar_serie":
            self.series.append([_nome(args[0]), int(args[1]), float(args[2]), 0.0, None])
        elif corpo is not None:
            corpo.executar(nome, args)


def _nome(v) -> str:
    return v.nome if isinstance(v, Simbolo) else str(v)


class ComportamentoAgente(Componente):
    """Liga o GameObject a um agente: ``modelo`` (cria instância) ou ``agente`` (único)."""

    CAMPOS = {"modelo": "str", "agente": "str", "olhar_movimento": "bool", "frente_do_sprite": "float"}
    modelo = ""
    agente = ""
    olhar_movimento = True     # gira o sprite para a direção em que anda
    frente_do_sprite = 0.0     # para onde o desenho aponta (graus): 0 = direita, 90 = cima, -90 = baixo
    MENU = "AgentDSL"

    def iniciar(self):
        srv = self.cena.servicos.get("agentes")
        if srv is None:   # o serviço ainda não iniciou (ordem dos objetos na cena): inicia agora
            for s in self.cena.componentes_do_tipo(ServicoAgentes):
                if not s._iniciado:
                    s._iniciado = True
                    s.iniciar()
            srv = self.cena.servicos.get("agentes")
            if srv is None:
                raise RuntimeError("ComportamentoAgente precisa de um objeto com ServicoAgentes na cena")
        self.srv = srv
        if self.agente:
            self.ag = srv.sis.agentes[self.agente]
        elif getattr(self, "manter_nome", False):     # o jogo já deu um nome ao objeto (ex.: robo2)
            self.ag = srv.sis.criar_instancia(self.modelo, nome=self.gameobject.nome)
        else:
            self.ag = srv.sis.criar_instancia(self.modelo)
            self.gameobject.nome = self.ag.nome
        self.ag.corpo = self
        self.rb = self.obter(CorpoRigido)
        self.render = self.obter(SpriteRenderer)
        self.giro = 0.0
        self.comportamento = None     # ("perseguir" | "fugir", alvo, velocidade)
        self._pulsos: list[tuple] = []

    # --- percepções -------------------------------------------------------------------
    def pulsar(self, nome: str, args: tuple = ()) -> None:
        """Crença instantânea: entra agora e sai no próximo quadro (gera +b e depois -b)."""
        self.ag.adicionar(nome, tuple(args))
        self._pulsos.append((nome, tuple(args), self.motor.quadro if self.motor else 0))

    def perceber(self, atuais: set) -> None:
        """Atualiza as percepções gerenciadas pelo jogo; só as diferenças viram eventos."""
        ag = self.ag
        gerenciadas = self.srv.nomes_percepcoes
        pulsos = {(n, a) for n, a, _ in self._pulsos}
        for c in [c for c in ag.crencas if c[0] in gerenciadas and c not in atuais and c not in pulsos]:
            ag.remover(*c)
        for nome, args in atuais:
            ag.adicionar(nome, tuple(args))

    def crenca_num(self, nome: str, padrao: float = 0.0) -> float:
        """Lê o valor de uma crença numérica de aridade 1, ex.: alcance(180)."""
        for _, args in self.ag.crencas_com(nome, 1):
            return float(args[0])
        return padrao

    # --- ações genéricas ------------------------------------------------------------------
    def executar(self, nome: str, args: list) -> None:
        t = self.transform
        if nome == "mover":
            t.transladar(args[0], args[1])
        elif nome == "posicionar":
            t.x, t.y = args[0], args[1]
        elif nome == "rotacionar":
            t.rotacao += args[0]
        elif nome == "girar":
            self.giro = float(args[0])
        elif nome == "escalar":
            t.escala_x *= args[0]
            t.escala_y *= args[0]
        elif nome == "velocidade":
            self.comportamento = None
            self._vel(float(args[0]), float(args[1]))
        elif nome == "inverter":
            if self.rb:
                self._vel(-self.rb.vx, -self.rb.vy)
        elif nome == "parar":
            self.comportamento = None
            self.giro = 0.0
            self._vel(0.0, 0.0)
        elif nome in ("perseguir", "fugir"):
            self.comportamento = (nome, _nome(args[0]), float(args[1]))
        elif nome == "mudar_camada":
            if self.render:
                self.render.camada = int(args[0])
        elif nome == "cor":
            if self.render:
                self.render.cor = (float(args[0]), float(args[1]), float(args[2]), 1.0)
                piscar = self.obter("Piscar")
                if piscar:
                    piscar.cor_original = self.render.cor
        elif nome == "trocar_imagem":
            if self.render:
                self.render.trocar_imagem(str(args[0]))
        elif nome == "sumir":
            if self.render:
                self.render.visivel = False
        elif nome == "aparecer":
            if self.render:
                self.render.visivel = True
        elif nome == "morrer":
            self.gameobject.destruir()
        elif nome == "piscar":
            piscar = self.obter("Piscar")
            if piscar:
                piscar.disparar()
        else:
            raise ValueError(f"ação '{nome}' não implementada")

    def _vel(self, vx, vy):
        if self.rb is None:
            self.rb = self.gameobject.adicionar(CorpoRigido(cinematico=True))
            self.rb._iniciado = True
            self.cena.fisica.registrar_corpo(self.rb)
        self.rb.vx, self.rb.vy = vx, vy

    def atualizar(self, dt):
        if self._pulsos:   # pulsos de quadros anteriores saem agora
            q = self.motor.quadro if self.motor else 0
            velhos = [p for p in self._pulsos if p[2] < q]
            for nome, args, _ in velhos:
                self.ag.remover(nome, args)
            self._pulsos = [p for p in self._pulsos if p[2] >= q]
        if self.comportamento:
            tipo, alvo_nome, vel = self.comportamento
            alvo = self.cena.encontrar(alvo_nome)
            if alvo is not None:
                ax, ay = alvo.transform.posicao_mundo
                x, y = self.transform.posicao_mundo
                dx, dy = ax - x, ay - y
                d = math.hypot(dx, dy) or 1.0
                s = 1.0 if tipo == "perseguir" else -1.0
                self._vel(s * vel * dx / d, s * vel * dy / d)
        if self.giro:
            self.transform.rotacao += self.giro * dt
        elif self.olhar_movimento and self.rb is not None and (self.rb.vx or self.rb.vy):
            self.transform.rotacao = math.degrees(math.atan2(self.rb.vy, self.rb.vx)) - self.frente_do_sprite

    def ao_destruir(self):
        if getattr(self, "ag", None) is not None:
            self.ag.corpo = None
            if not self.agente:
                self.srv.sis.remover_instancia(self.ag)

    def linhas_inspector(self) -> list[str]:
        if getattr(self, "ag", None) is None:
            return []
        linhas = [f"agente: {self.ag.nome}  (fila: {len(self.ag.fila)} eventos)", "crenças:"]
        linhas += ["  " + formatar_crenca(c) for c in sorted(self.ag.crencas, key=str)]
        if self.ag.log:
            linhas.append("últimos eventos:")
            linhas += ["  " + l for l in list(self.ag.log)[-5:]]
        return linhas
