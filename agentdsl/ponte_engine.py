"""Ligação entre a DSL e a engine 2D:  Ação do agente → Engine 2D → Sprite (eq. 5).

A engine NÃO interpreta crenças nem escolhe comportamentos: ela só executa
as ações recebidas (mover, girar, perseguir...) e devolve percepções, que a
ponte transforma em adições/remoções de crenças (e portanto em eventos).
"""
from __future__ import annotations

import math

from .interpretador import Simbolo


class AmbienteEngine:
    def __init__(self, motor, percepcoes: set[str] = frozenset(), limites=None, margem: float = 24):
        self.motor = motor
        self.objetos: dict[str, object] = {}       # nome → sprite (agentes e extras, ex.: jogador)
        self.estado: dict[str, dict] = {}          # nome do agente → velocidade/comportamento
        self.percepcoes_gerenciadas = set(percepcoes)
        self.acoes_extras: dict[str, callable] = {}
        self.limites = limites or (0, 0, motor.largura, motor.altura)
        self.margem = margem
        self._pulsos: list[tuple] = []
        self.historico_acoes: list[tuple] = []

    # --- registro -----------------------------------------------------------
    def vincular(self, agente, sprite) -> None:
        agente.sprite = sprite
        sprite.dados["agente"] = agente
        self.objetos[agente.nome] = sprite
        self.estado[agente.nome] = {"vx": 0.0, "vy": 0.0, "giro": 0.0, "comportamento": None}

    def registrar_objeto(self, nome: str, sprite) -> None:
        self.objetos[nome] = sprite

    def registrar_acao(self, nome: str, funcao) -> None:
        """Ações específicas da aplicação (ex.: atacar no jogo). funcao(agente, *args)."""
        self.acoes_extras[nome] = funcao

    # --- ações vindas do interpretador ---------------------------------------
    def executar(self, agente, nome: str, args: list) -> None:
        self.historico_acoes.append((agente.nome, nome, tuple(args)))
        sp, st = agente.sprite, self.estado.get(agente.nome)
        if nome in self.acoes_extras:
            self.acoes_extras[nome](agente, *args)
            return
        if sp is None:
            return
        tr = sp.transformacao
        if nome == "mover":
            tr.transladar(args[0], args[1])
        elif nome == "posicionar":
            tr.posicao = (args[0], args[1])
        elif nome == "rotacionar":
            tr.rotacionar(args[0])
        elif nome == "girar":
            st["giro"] = float(args[0])
        elif nome == "escalar":
            tr.escalar(args[0])
        elif nome == "velocidade":
            st["vx"], st["vy"], st["comportamento"] = float(args[0]), float(args[1]), None
        elif nome == "inverter":
            st["vx"], st["vy"] = -st["vx"], -st["vy"]
        elif nome == "parar":
            st["vx"] = st["vy"] = st["giro"] = 0.0
            st["comportamento"] = None
        elif nome in ("perseguir", "fugir"):
            alvo = args[0].nome if isinstance(args[0], Simbolo) else str(args[0])
            st["comportamento"] = (nome, alvo, float(args[1]))
        elif nome == "mudar_camada":
            sp.camada = int(args[0])
        elif nome == "cor":
            sp.cor = (float(args[0]), float(args[1]), float(args[2]), sp.cor[3])
        elif nome == "sumir":
            sp.visivel = False
        elif nome == "aparecer":
            sp.visivel = True
        else:
            raise ValueError(f"ação '{nome}' não implementada pela engine")

    # --- percepções ------------------------------------------------------------
    def pulsar(self, agente, nome: str, args: tuple = ()) -> None:
        """Adiciona a crença agora e a remove no próximo quadro (evento instantâneo)."""
        agente.adicionar(nome, args)
        self._pulsos.append((agente, nome, tuple(args)))

    def atualizar_percepcoes(self, agente, atuais: set[tuple]) -> None:
        """Compara as percepções atuais com as crenças e gera só as DIFERENÇAS."""
        for c in list(agente.crencas):
            if c[0] in self.percepcoes_gerenciadas and c not in atuais and \
                    not any(p[0] is agente and (p[1], p[2]) == c for p in self._pulsos):
                agente.remover(*c)
        for nome, args in atuais:
            agente.adicionar(nome, args)

    # --- simulação por quadro ----------------------------------------------------
    def atualizar(self, dt: float) -> None:
        for agente, nome, args in self._pulsos_antigos():
            agente.remover(nome, args)
        x0, y0, x1, y1 = self.limites
        for nome, st in self.estado.items():
            sp = self.objetos[nome]
            if not sp.visivel:
                continue
            tr = sp.transformacao
            comp = st["comportamento"]
            if comp:
                tipo, alvo_nome, vel = comp
                alvo = self.objetos.get(alvo_nome)
                if alvo is not None:
                    dx, dy = alvo.x - tr.x, alvo.y - tr.y
                    d = math.hypot(dx, dy) or 1.0
                    sinal = 1 if tipo == "perseguir" else -1
                    st["vx"], st["vy"] = sinal * vel * dx / d, sinal * vel * dy / d
            if st["vx"] or st["vy"]:
                tr.transladar(st["vx"] * dt, st["vy"] * dt)
            if st["giro"]:
                tr.rotacionar(st["giro"] * dt)
            # Bordas do mundo: prende o sprite e gera a percepção "borda".
            m = self.margem
            bateu = False
            if tr.x < x0 + m or tr.x > x1 - m:
                tr.x = min(max(tr.x, x0 + m), x1 - m)
                bateu = True
            if tr.y < y0 + m or tr.y > y1 - m:
                tr.y = min(max(tr.y, y0 + m), y1 - m)
                bateu = True
            if bateu and "borda" in self.percepcoes_gerenciadas:
                ag = sp.dados.get("agente")
                if ag is not None and not ag.acredita("borda"):
                    self.pulsar(ag, "borda")

    def _pulsos_antigos(self):
        antigos, self._pulsos = self._pulsos, []
        return antigos

    @staticmethod
    def distancia(a, b) -> float:
        return math.hypot(a.x - b.x, a.y - b.y)
