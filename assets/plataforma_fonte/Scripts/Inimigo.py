"""O "corpo" de um inimigo. Quem decide o que ele faz é o agente da DSL (Assets/Agentes/plataforma.agt).

Percepções que o agente recebe:
  ativado                      apareceu perto da tela (os inimigos só começam a andar aí)
  jogador_lado(esquerda|direita)
  jogador_perto                o jogador está a menos de ``distancia_perto`` pixels
  no_chao                      está apoiado em alguma coisa
Eventos instantâneos:
  parede_a_frente, buraco_a_frente   (andando: vai bater / vai cair)
  pisado                              o jogador pulou em cima
"""
import math

from agentdsl.interpretador import Simbolo
from engine2d import Componente

import Plataforma as P

LADOS = {n: Simbolo(n) for n in ("esquerda", "direita")}


class Inimigo(Componente):
    CAMPOS = {"animacoes": "str", "olha_para_esquerda": "bool", "distancia_perto": "float"}
    animacoes = ""              # "andar=a.png,b.png; parado=c.png; achatado=d.png"
    olha_para_esquerda = True   # o desenho original olha para a esquerda
    distancia_perto = 380.0

    def iniciar(self):
        self.rb = self.obter("CorpoRigido")
        self.render = self.obter("SpriteRenderer")
        self.agente = self.obter("ComportamentoAgente")
        self.anims = {}
        for parte in self.animacoes.split(";"):
            if "=" in parte:
                nome, quadros = parte.split("=", 1)
                self.anims[nome.strip()] = [q.strip() for q in quadros.split(",") if q.strip()]
        self.anim = "parado" if "parado" in self.anims else next(iter(self.anims), None)
        self.t = 0.0
        self.ativado = False
        self.morto = False
        self.direcao = 0               # -1 esquerda, 1 direita (andar)
        self.vel = 0.0
        self.patrulha = None           # (x0, y0, distancia, velocidade)
        self.pulando = False
        self.t_virou = 0.0

    # --- ações pedidas pela DSL -------------------------------------------------------------------
    def andar(self, direcao, vel):
        self.direcao = -1 if direcao == "esquerda" else 1
        self.vel = float(vel)
        self.patrulha = None

    def virar(self):
        if self.direcao:
            self.direcao = -self.direcao
            self.t_virou = 0.25

    def parar(self):
        self.direcao = 0
        self.patrulha = None
        if self.rb:
            self.rb.vx = 0.0

    def patrulhar_voando(self, distancia, vel):
        x, y = self.transform.posicao_mundo
        self.patrulha = (x, y, float(distancia), float(vel))
        self.direcao = -1

    def pular_para_jogador(self, vx, vy):
        j = P.jogador(self.cena)
        lado = -1 if j is None or j.transform.x < self.transform.x else 1
        self.direcao = 0
        self.rb.vx, self.rb.vy = lado * float(vx), float(vy)
        self.pulando = True
        if self.render:
            self.render.virar_x = (lado > 0) == self.olha_para_esquerda

    def animacao(self, nome):
        if nome in self.anims and nome != self.anim:
            self.anim, self.t = nome, 0.0

    def pisado(self):
        """O jogador pulou em cima: o agente da DSL decide (+pisado)."""
        P.poeira(self.cena, self.transform.x, self.transform.y + 10, 6)
        self._pulsar("pisado")

    def achatar(self, pontos=0):
        if self.morto:
            return
        self.morto = True
        self.parar()
        self.animacao("achatado")
        for f in self.gameobject.filhos:             # o "toque" não machuca mais
            f.ativo = False
        if self.rb:
            self.rb.tipo = "cinematico"
            self.rb.vy = 0.0
        h = P.hud(self.cena)
        if h is not None and pontos:
            h.somar(int(pontos), *self.transform.posicao_mundo)
        self.gameobject.destruir(0.5)

    # --- percepções e movimento --------------------------------------------------------------------
    def _pulsar(self, nome, args=()):
        if self.agente is not None and getattr(self.agente, "ag", None) is not None:
            self.agente.pulsar(nome, args)

    def atualizar(self, dt):
        self.t += dt
        self.t_virou = max(0.0, self.t_virou - dt)
        x, y = self.transform.posicao_mundo
        cam = self.motor.camera
        if not self.ativado and abs(x - cam.x) < cam.largura / (2 * cam.zoom) + 120:
            self.ativado = True
        if y < -300:
            self.gameobject.destruir()
            return
        if not self.morto:
            self._mover(dt, x, y)
        self._perceber(x)
        quadros = self.anims.get(self.anim)
        if quadros and self.render:
            self.render.imagem = quadros[int(self.t * 6) % len(quadros)]

    def _mover(self, dt, x, y):
        rb = self.rb
        if self.patrulha is not None:
            x0, y0, dist, vel = self.patrulha
            if (x < x0 - dist and self.direcao < 0) or (x > x0 + dist and self.direcao > 0):
                self.direcao = -self.direcao
            rb.vx = self.direcao * vel
            rb.vy = (y0 + math.sin(self.t * 3) * 18 - y) * 6
        elif self.direcao:
            rb.vx = self.direcao * self.vel
            if self.t_virou <= 0 and rb.no_chao:
                if rb.na_parede == self.direcao:
                    self._pulsar("parede_a_frente")
                    self.t_virou = 0.25
                elif self._buraco_a_frente(x, y):
                    self._pulsar("buraco_a_frente")
                    self.t_virou = 0.25
        elif self.pulando and rb.no_chao and rb.vy <= 0:
            rb.vx = 0.0
            self.pulando = False
        if self.render and (self.direcao or self.patrulha is not None):
            self.render.virar_x = (self.direcao > 0) == self.olha_para_esquerda

    def _buraco_a_frente(self, x, y):
        """Raio para baixo saindo um pouco à frente do pé: se não acha chão perto, é buraco."""
        col = self.obter("Colisor")
        x0, y0, x1, _ = col.aabb()
        frente = x1 + 4 if self.direcao > 0 else x0 - 4
        return self.cena.fisica.lancar_raio(frente, y0 + 4, 0, -1, 30, ignorar=self.gameobject) is None

    def _perceber(self, x):
        if self.agente is None or getattr(self.agente, "ag", None) is None:
            return
        atuais = set()
        if self.ativado:
            atuais.add(("ativado", ()))
        if self.rb is not None and self.rb.no_chao:
            atuais.add(("no_chao", ()))
        j = P.jogador(self.cena)
        if j is not None and not j.morto:
            jx, jy = j.transform.posicao_mundo
            atuais.add(("jogador_lado", (LADOS["esquerda" if jx < x else "direita"],)))
            if math.hypot(jx - x, jy - self.transform.y) < self.distancia_perto:
                atuais.add(("jogador_perto", ()))
        self.agente.perceber(atuais)
