import math

from engine2d import Componente

TAM_MUNDO = 2560      # o mapa vai de (0, 0) até (TAM_MUNDO, TAM_MUNDO)


class Jogador(Componente):
    """Movimento com WASD, vida, experiência e nível. As armas atiram sozinhas (veja arena.agt)."""

    CAMPOS = {"vida": "float", "vida_max": "float", "velocidade": "float", "ima": "float",
              "multiplicador_dano": "float"}
    vida = 100.0
    vida_max = 100.0
    velocidade = 210.0
    ima = 90.0                    # distância em que os cristais começam a vir até você
    multiplicador_dano = 1.0

    def iniciar(self):
        self.corpo = self.obter("CorpoRigido")
        self.piscar = self.obter("Piscar")
        self.invencivel = 0.0
        self.xp = 0
        self.nivel = 1
        self.xp_proximo = 5

    def atualizar(self, dt):
        dx, dy = self.motor.entrada.direcao_wasd()
        self.corpo.vx, self.corpo.vy = dx * self.velocidade, dy * self.velocidade
        if dx or dy:
            self.transform.rotacao = math.degrees(math.atan2(dy, dx))
        t = self.transform
        t.x = min(max(t.x, 40), TAM_MUNDO - 40)
        t.y = min(max(t.y, 40), TAM_MUNDO - 40)
        self.invencivel = max(0.0, self.invencivel - dt)
        self.vida = min(self.vida_max, self.vida + 0.4 * dt)   # regeneração lenta

    def ferir(self, dano):
        if self.invencivel > 0 or self.vida <= 0:
            return
        self.vida -= dano
        self.invencivel = 0.25
        if self.piscar:
            self.piscar.disparar()

    def ganhar_xp(self, n):
        self.xp += n
        gerente = self.cena.servicos["gerente"]
        while self.xp >= self.xp_proximo:
            self.xp -= self.xp_proximo
            self.nivel += 1
            self.xp_proximo = int(5 + self.nivel * 4.5)
            gerente.subir_nivel()
