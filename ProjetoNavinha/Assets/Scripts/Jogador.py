"""A nave do jogador: anda com WASD/setas, atira segurando Espaço (ou Z) e pega itens.

Filhos esperados no objeto (montados no editor): "Escudo" (sprite do escudo, começa desligado)
e "Fogo" (EmissorParticulas da turbina).
"""
import math

from engine2d import Componente

import Navinha as N


class Jogador(Componente):
    CAMPOS = {"velocidade": "float", "vidas": "int", "intervalo_tiro": "float", "velocidade_tiro": "float",
              "nivel_arma": "int", "invencivel_ao_levar_dano": "float"}
    velocidade = 330.0
    vidas = 3
    intervalo_tiro = 0.16
    velocidade_tiro = 760.0
    nivel_arma = 1                  # 1 a 4: quantos tiros saem de uma vez
    invencivel_ao_levar_dano = 2.0

    MAX_ARMA = 4

    def iniciar(self):
        self.recarga = 0.0
        self.invencivel = 1.5        # um respiro no começo da fase
        self.escudo = 0.0
        self.vivo = True
        self.render = self.obter("SpriteRenderer")
        self.obj_escudo = next((f for f in self.gameobject.filhos if f.nome == "Escudo"), None)
        self.fogo = next((f for f in self.gameobject.filhos if f.nome == "Fogo"), None)
        self._piscar = 0.0

    # --- controle ---------------------------------------------------------------------------
    def atualizar(self, dt):
        if not self.vivo:
            return
        ent = self.motor.entrada
        dx, dy = ent.direcao_wasd()
        lento = ent.tecla("left shift") or ent.tecla("right shift")   # Shift = desvio fino
        v = self.velocidade * (0.45 if lento else 1.0)
        t = self.transform
        t.x = min(max(t.x + dx * v * dt, N.ESQUERDA + 26), N.DIREITA - 26)
        t.y = min(max(t.y + dy * v * dt, N.BAIXO + 24), N.CIMA - 40)
        self.recarga -= dt
        if (ent.tecla("space") or ent.tecla("z")) and self.recarga <= 0:
            self.atirar()
            self.recarga = self.intervalo_tiro
        self._tempos(dt)

    def _tempos(self, dt):
        self.invencivel = max(0.0, self.invencivel - dt)
        if self.escudo > 0:
            self.escudo = max(0.0, self.escudo - dt)
            if self.escudo == 0:
                N.tocar(self.cena, "escudo_caiu")
        if self.obj_escudo is not None:
            self.obj_escudo.ativo = self.escudo > 0
            sr = self.obj_escudo.obter("SpriteRenderer")
            if sr is not None and self.escudo < 2:          # pisca avisando que vai acabar
                sr.visivel = int(self.escudo * 8) % 2 == 0
        self._piscar += dt
        if self.render is not None:                        # piscando = invencível
            self.render.visivel = self.invencivel <= 0 or int(self._piscar * 14) % 2 == 0

    def atirar(self):
        x, y = self.transform.posicao_mundo
        n = max(1, min(self.MAX_ARMA, self.nivel_arma))
        padroes = {1: [(0, 0)], 2: [(-9, 0), (9, 0)], 3: [(0, 0), (-10, 8), (10, -8)],
                   4: [(-6, 0), (6, 0), (-14, 12), (14, -12)]}
        for desloc, ang in padroes[n]:
            self._tiro(x + desloc, y + 30, 90 + ang)
        N.tocar(self.cena, "laser", 0.35)

    def _tiro(self, x, y, angulo):
        tiro = self.cena.instanciar("Assets/Prefabs/tiro_jogador.prefab", x, y)
        tiro.transform.rotacao = angulo - 90
        rb = tiro.obter("CorpoRigido")
        rb.vx = math.cos(math.radians(angulo)) * self.velocidade_tiro
        rb.vy = math.sin(math.radians(angulo)) * self.velocidade_tiro

    # --- dano e itens ---------------------------------------------------------------------
    def levar_dano(self):
        if not self.vivo or self.invencivel > 0:
            return False
        x, y = self.transform.posicao_mundo
        if self.escudo > 0:                     # o escudo segura um golpe e acaba
            self.escudo = 0.0
            self.invencivel = 0.8
            N.faisca(self.cena, x, y)
            N.tocar(self.cena, "escudo_caiu")
            return False
        self.vidas -= 1
        self.nivel_arma = max(1, self.nivel_arma - 1)
        N.explosao(self.cena, x, y, 0.8)
        self.motor.tremer(10, 0.4)                     # levou dano: a tela treme forte
        if self.vidas <= 0:
            self.morrer()
        else:
            self.invencivel = self.invencivel_ao_levar_dano
            N.tocar(self.cena, "perdeu", 0.5)
        return True

    def morrer(self):
        self.vivo = False
        x, y = self.transform.posicao_mundo
        N.explosao(self.cena, x, y, 2.2)
        if self.render is not None:
            self.render.visivel = False
        for f in (self.fogo, self.obj_escudo):
            if f is not None:
                f.ativo = False
        h = N.hud(self.cena)
        if h is not None:
            h.fim_de_jogo()

    def pegar_item(self, tipo):
        N.tocar(self.cena, "item")
        h = N.hud(self.cena)
        if tipo == "arma":
            if self.nivel_arma < self.MAX_ARMA:
                self.nivel_arma += 1
                texto = f"Arma nível {self.nivel_arma}!"
            else:
                texto = "Arma no máximo: +500"
                if h:
                    h.somar(500)
        elif tipo == "escudo":
            self.escudo = 10.0
            texto = "Escudo!"
        elif tipo == "vida":
            self.vidas = min(5, self.vidas + 1)
            texto = "Vida extra!"
        else:
            texto = "+250"
            if h:
                h.somar(250)
        if h:
            h.mensagem_curta(texto)

    def ao_entrar_colisao(self, outro):
        go = outro.gameobject
        if go.tag == "item":
            item = go.obter("Item")
            if item is not None and not go.destruido:
                self.pegar_item(item.tipo)
                go.destruir()
        elif go.tag == "inimigo" and self.vivo:
            nave = go.obter("NaveInimiga")
            if nave is not None:
                nave.bateu_no_jogador(self)
