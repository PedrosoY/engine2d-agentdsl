import math

from engine2d import Componente


class Moeda(Componente):
    CAMPOS = {"velocidade_giro": "float", "altura_pulo": "float"}
    velocidade_giro = 180.0
    altura_pulo = 6.0

    def iniciar(self):
        self.y_inicial = self.transform.y
        self.tempo = 0.0

    def atualizar(self, dt):
        # Gira e "flutua" para cima e para baixo
        self.tempo += dt
        self.transform.rotacao += self.velocidade_giro * dt
        self.transform.y = self.y_inicial + math.sin(self.tempo * 4) * self.altura_pulo
