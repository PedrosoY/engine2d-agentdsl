"""Item que cai de um inimigo destruído. O Jogador.py aplica o efeito quando encosta."""
import math

from engine2d import Componente

import Navinha as N


class Item(Componente):
    CAMPOS = {"tipo": "str", "velocidade": "float"}
    tipo = "arma"            # arma | escudo | vida | pontos
    velocidade = 90.0

    def iniciar(self):
        self.t = 0.0
        self.x0 = self.transform.x

    def atualizar(self, dt):
        self.t += dt
        tr = self.transform
        tr.y -= self.velocidade * dt
        tr.x = self.x0 + math.sin(self.t * 3) * 14          # balança enquanto cai
        tr.escala_x = tr.escala_y = 1.0 + 0.12 * math.sin(self.t * 8)
        if tr.y < N.BAIXO - 30:
            self.gameobject.destruir()
