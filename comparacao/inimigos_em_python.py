"""O MESMO comportamento dos modelos `zumbi` e `atirador` de jogos/arena/arena.agt, em Python puro.

Serve para a avaliação "a DSL realmente simplifica a tarefa?" (item 5.1 do roteiro).
Repare no que o programador precisa controlar à mão aqui e que a DSL faz sozinha:
  - detectar MUDANÇAS de estado (guardar o valor anterior de cada percepção);
  - temporizadores (contadores decrementados a cada quadro);
  - a ordem dos testes que, na DSL, é a ordem dos planos.
"""


class Zumbi:
    vida = 10
    dano = 8
    xp = 1
    velocidade = 75

    def __init__(self, corpo, jogo):
        self.corpo = corpo
        self.jogo = jogo
        self.tocando_antes = False
        self.tempo_mordida = None
        self.corpo.perseguir("jogador", self.velocidade)

    def atualizar(self, dt, dano_recebido, tocando_jogador, jogador_perto):
        if dano_recebido > 0:
            if self.vida > dano_recebido:
                self.vida -= dano_recebido
                self.corpo.piscar()
            else:
                self.jogo.soltar_xp(self.corpo, self.xp)
                self.corpo.morrer()
                return
        if tocando_jogador and not self.tocando_antes:
            self.jogo.ferir_jogador(self.dano)
            self.tempo_mordida = 0.8
        if self.tempo_mordida is not None:
            self.tempo_mordida -= dt
            if self.tempo_mordida <= 0:
                if tocando_jogador:
                    self.jogo.ferir_jogador(self.dano)
                    self.tempo_mordida = 0.8
                else:
                    self.tempo_mordida = None
        self.tocando_antes = tocando_jogador


class Atirador(Zumbi):
    vida = 18
    dano = 6
    xp = 3
    velocidade = 85
    alcance = 320

    def __init__(self, corpo, jogo):
        super().__init__(corpo, jogo)
        self.perto_antes = False
        self.mirando = False
        self.tempo_disparo = None

    def atualizar(self, dt, dano_recebido, tocando_jogador, jogador_perto):
        super().atualizar(dt, dano_recebido, tocando_jogador, jogador_perto)
        if jogador_perto and not self.perto_antes:
            self.corpo.parar()
            self.mirando = True
            self.tempo_disparo = 0.9
        elif not jogador_perto and self.perto_antes:
            self.mirando = False
            self.corpo.perseguir("jogador", self.velocidade)
        self.perto_antes = jogador_perto
        if self.tempo_disparo is not None:
            self.tempo_disparo -= dt
            if self.tempo_disparo <= 0:
                if self.mirando:
                    self.jogo.atirar_no_jogador(self.corpo, 9, 280)
                    self.tempo_disparo = 1.7
                else:
                    self.tempo_disparo = None
