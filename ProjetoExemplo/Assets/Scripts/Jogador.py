import math

from engine2d import Componente, CorpoRigido


class Jogador(Componente):
    # Estes campos aparecem no Inspector e podem ser mudados sem mexer no código.
    CAMPOS = {"velocidade": "float", "vida": "int", "intervalo_tiro": "float", "velocidade_bala": "float"}
    velocidade = 220.0
    vida = 3
    intervalo_tiro = 0.25          # segundos entre um tiro e outro
    velocidade_bala = 650.0

    def iniciar(self):
        # iniciar(): pega o CorpoRigido do mesmo objeto
        self.corpo = self.obter(CorpoRigido)
        self.pontos = 0
        self.invencivel = 0.0
        self.recarga = 0.0

    def atualizar(self, dt):
        entrada = self.motor.entrada
        # atualizar(): anda com WASD...
        dx, dy = entrada.direcao_wasd()
        self.corpo.vx = dx * self.velocidade
        self.corpo.vy = dy * self.velocidade
        # ...e mira no mouse (mouse_mundo = posição do mouse no mundo, já considerando a câmera)
        mx, my = entrada.mouse_mundo
        self.transform.olhar_para(mx, my)
        # Botão esquerdo (pode segurar): atira na direção do mouse
        self.recarga = max(0.0, self.recarga - dt)
        if entrada.mouse_pressionado(1) and self.recarga <= 0:
            self.atirar(mx, my)
            self.recarga = self.intervalo_tiro
        self.invencivel = max(0.0, self.invencivel - dt)

    def atirar(self, mx, my):
        x, y = self.transform.posicao_mundo
        angulo = math.degrees(math.atan2(my - y, mx - x))
        # instanciar(prefab): cria uma cópia do prefab da bala na posição do jogador
        bala = self.cena.instanciar("Assets/Prefabs/bala.prefab", x, y)
        bala.transform.rotacao = angulo
        corpo_bala = bala.obter("CorpoRigido")
        corpo_bala.vx = math.cos(math.radians(angulo)) * self.velocidade_bala
        corpo_bala.vy = math.sin(math.radians(angulo)) * self.velocidade_bala

    def ao_entrar_colisao(self, outro):
        # ao_entrar_colisao: "outro" é o Colisor que encostou
        objeto = outro.gameobject
        if objeto.tag == "moeda":
            self.pontos += 1
            objeto.destruir()
            print(f"Pegou uma moeda! Pontos: {self.pontos}")
        elif objeto.tag == "inimigo" and self.invencivel <= 0:
            self.vida -= 1
            self.invencivel = 1.0
            print(f"Ai! Vida: {self.vida}")
            if self.vida <= 0:
                print("Fim de jogo — reiniciando a cena")
                self.motor.trocar_cena(self.cena.servicos["fabrica"])
