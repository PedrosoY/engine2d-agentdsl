"""O MESMO comportamento do agente `guarda` de exemplos/jogo.agt, escrito em Python puro.

Serve para a avaliação "a DSL realmente simplifica a tarefa?" (item 5.1 do roteiro):
compare linhas, tokens e, principalmente, o que o programador precisa controlar à mão
(detecção de mudança de estado, ordem dos testes, contadores, flags).
"""


class Guarda:
    def __init__(self, sprite, ambiente):
        self.sprite = sprite
        self.amb = ambiente
        self.vivo = True
        self.vida = 3
        self.patrulhando = True
        self.raio_visao = 210
        self.jogador_perto_antes = False
        self.tocando_antes = False
        self.amb.velocidade(self, 90, 0)

    def atualizar(self, jogador_perto, tocando, bateu_borda, recebeu_dano):
        # Detectar as MUDANÇAS de estado à mão (a DSL gera esses eventos sozinha).
        if bateu_borda and self.patrulhando:
            self.amb.inverter(self)

        if jogador_perto and not self.jogador_perto_antes and self.vivo:
            self.patrulhando = False
            self.amb.perseguir(self, "jogador", 125)
            self.amb.cor(self, 1, 0.75, 0.75)
        elif not jogador_perto and self.jogador_perto_antes and self.vivo:
            self.patrulhando = True
            self.amb.velocidade(self, 90, 0)
            self.amb.cor(self, 1, 1, 1)
        self.jogador_perto_antes = jogador_perto

        if tocando and not self.tocando_antes and self.vivo:
            self.amb.atacar(self, "jogador", 1)
        self.tocando_antes = tocando

        if recebeu_dano and self.vivo:
            if self.vida > 1:
                self.vida -= 1
                self.amb.rotacionar(self, 30)
                self.amb.escalar(self, 0.85)
                print("ai! vida restante:", self.vida)
            elif self.vida == 1:
                self.vida = 0
                self.vivo = False
                self.amb.parar(self)
                self.amb.sumir(self)
                self.amb.pontuar(self, 50)


class Guarda2(Guarda):
    def __init__(self, sprite, ambiente):
        super().__init__(sprite, ambiente)
        self.raio_visao = 260
        self.amb.velocidade(self, 0, 110)
