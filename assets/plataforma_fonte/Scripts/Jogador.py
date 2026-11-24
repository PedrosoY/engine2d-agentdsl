"""O personagem: anda com A/D ou setas, pula com Espaço/W/seta para cima.

Usa a física da engine (CorpoRigido dinâmico + gravidade do projeto): o script só muda a
velocidade, e a física cuida do chão, das paredes e das plataformas.
"""
from engine2d import Componente

import Plataforma as P

IMG = "Assets/Sprites/Personagem/character_green_"


class Jogador(Componente):
    CAMPOS = {"velocidade": "float", "aceleracao": "float", "freio": "float", "forca_pulo": "float",
              "vidas": "int", "tempo_coiote": "float", "lembrar_pulo": "float", "altura_queda": "float"}
    velocidade = 330.0
    aceleracao = 2400.0        # px/s² para chegar na velocidade
    freio = 2800.0             # px/s² para parar quando solta a tecla
    forca_pulo = 860.0
    vidas = 3
    tempo_coiote = 0.1         # ainda dá para pular um instante depois de sair da beirada
    lembrar_pulo = 0.12        # apertou o pulo um pouco antes de encostar no chão: pula ao encostar
    altura_queda = -200.0      # abaixo disso caiu no buraco

    def iniciar(self):
        self.rb = self.obter("CorpoRigido")
        self.render = self.obter("SpriteRenderer")
        self.inicio = self.transform.posicao_mundo
        self.ponto_retorno = self.inicio
        self.invencivel = 0.0
        self.t_coiote = 0.0
        self.t_pulo = 0.0
        self.t_anim = 0.0
        self.no_chao_antes = False
        self.pulando = False
        self.ultimo_bloco = None
        self.controle = True
        self.venceu = False
        self.morto = False

    # --- controle -----------------------------------------------------------------------------
    def atualizar(self, dt):
        if self.morto:
            return
        ent = self.motor.entrada
        rb = self.rb
        if self.venceu:                          # andando sozinho até o fim depois da bandeira
            rb.vx = 140
            self._animar(dt, andando=True)
            return
        direcao = ent.eixo(("a", "left"), ("d", "right")) if self.controle else 0.0
        alvo = direcao * self.velocidade
        taxa = self.aceleracao if direcao else self.freio
        if not rb.no_chao:
            taxa *= 0.65                         # no ar dá para corrigir, mas menos
        if rb.vx < alvo:
            rb.vx = min(alvo, rb.vx + taxa * dt)
        elif rb.vx > alvo:
            rb.vx = max(alvo, rb.vx - taxa * dt)
        # pulo com tempo de coiote, pulo lembrado e altura variável
        self.t_coiote = self.tempo_coiote if rb.no_chao else max(0.0, self.t_coiote - dt)
        apertou = any(ent.tecla_baixou(t) for t in ("space", "w", "up", "z"))
        self.t_pulo = self.lembrar_pulo if apertou else max(0.0, self.t_pulo - dt)
        if self.t_pulo > 0 and self.t_coiote > 0 and self.controle:
            rb.vy = self.forca_pulo
            self.t_pulo = self.t_coiote = 0.0
            self.pulando = True
            P.tocar(self.cena, "pulo", 0.4)
            P.poeira(self.cena, self.transform.x, self.transform.y - 40, 5)
        if rb.vy <= 0:
            self.pulando = False
        segurando = any(ent.tecla(t) for t in ("space", "w", "up", "z"))
        if self.pulando and rb.vy > 0 and not segurando:
            rb.vy -= 2600 * dt                   # soltou cedo: pulo mais baixo (só o pulo, não a mola)
        if rb.no_chao and not self.no_chao_antes and rb.vy <= 0:
            P.poeira(self.cena, self.transform.x, self.transform.y - 40, 4)
        self.no_chao_antes = rb.no_chao
        self._bater_cabeca()
        self._animar(dt, andando=abs(rb.vx) > 20)
        self.invencivel = max(0.0, self.invencivel - dt)
        if self.render is not None:
            self.render.visivel = self.invencivel <= 0 or int(self.invencivel * 15) % 2 == 0
        if self.transform.y < self.altura_queda:
            self.caiu()

    def _animar(self, dt, andando):
        if self.render is None:
            return
        rb = self.rb
        if rb.vx > 5:
            self.render.virar_x = False
        elif rb.vx < -5:
            self.render.virar_x = True
        self.t_anim += dt
        if not rb.no_chao:
            img = "jump"
        elif andando:
            img = "walk_a" if int(self.t_anim * 10) % 2 == 0 else "walk_b"
        else:
            img = "idle"
        self.render.imagem = IMG + img + ".png"

    def _bater_cabeca(self):
        """Bateu a cabeça num bloco por baixo: avisa o agente do bloco (+batido na DSL)."""
        if not self.rb.no_teto:
            self.ultimo_bloco = None
            return
        for outro, nx, ny in self.rb.contatos:
            go = outro.gameobject
            if ny < -0.7 and go.tag == "bloco" and go is not self.ultimo_bloco:
                self.ultimo_bloco = go
                corpo = go.obter("ComportamentoAgente")
                if corpo is not None and getattr(corpo, "ag", None) is not None:
                    corpo.pulsar("batido")
                break

    # --- vida ---------------------------------------------------------------------------------
    def levar_dano(self):
        if self.invencivel > 0 or self.morto or self.venceu:
            return
        self.vidas -= 1
        P.tocar(self.cena, "dano")
        if self.vidas <= 0:
            self.morrer()
            return
        self.invencivel = 1.6
        self.rb.vy = 520
        self.rb.vx = -260 if not self.render.virar_x else 260

    def caiu(self):
        """Caiu no buraco: perde uma vida e volta no último checkpoint."""
        self.vidas -= 1
        P.tocar(self.cena, "dano")
        if self.vidas <= 0:
            self.morrer()
            return
        self.transform.posicao_mundo = self.ponto_retorno
        self.rb.vx = self.rb.vy = 0.0
        self.invencivel = 1.6

    def morrer(self):
        self.morto = True
        self.rb.vx, self.rb.vy = 0.0, 650.0
        self.rb.tipo = "cinematico"                 # sobe e cai atravessando tudo, como nos clássicos
        if self.render is not None:
            self.render.imagem = IMG + "hit.png"
            self.render.virar_y = True
        h = P.hud(self.cena)
        if h is not None:
            h.fim_de_jogo()

    def atualizar_tardio(self, dt):
        if self.morto:
            self.rb.vy -= 1800 * dt

    def ganhar_vida(self):
        self.vidas = min(9, self.vidas + 1)

    def vencer(self):
        self.venceu = True
        self.controle = False

    # --- encostou em algo -------------------------------------------------------------------------
    def ao_entrar_colisao(self, outro):
        if self.morto:
            return
        go = outro.gameobject
        if go.tag == "inimigo":
            inimigo = go.pai if go.pai is not None else go
            corpo = inimigo.obter("Inimigo")
            if corpo is None or corpo.morto:
                return
            # pisão: vindo de cima, com os pés acima do meio do inimigo
            pes = self.obter("Colisor").aabb()[1]
            meio = outro.centro()[1]
            if self.rb.vy < 60 and pes > meio - 4:
                corpo.pisado()
                segurando = any(self.motor.entrada.tecla(t) for t in ("space", "w", "up", "z"))
                self.rb.vy = 760 if segurando else 520
            else:
                self.levar_dano()
        elif go.tag == "perigo":
            self.levar_dano()
