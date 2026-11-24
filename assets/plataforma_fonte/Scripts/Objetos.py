"""Objetos da fase: bloco surpresa, coletáveis (moeda, cogumelo), mola, checkpoint e bandeira do fim."""
import math

from engine2d import Componente

import Plataforma as P


class Bloco(Componente):
    """Bloco que o jogador bate por baixo. O que sai dele é decidido pelo agente da DSL
    (modelos bloco_moeda e bloco_cogumelo); aqui só fica a animação e o "soltar"."""
    CAMPOS = {"imagem_vazio": "str"}
    imagem_vazio = "Assets/Sprites/Tiles/block_empty.png"

    def iniciar(self):
        self.y0 = self.transform.y
        self.t = 0.0

    def quicar(self):
        self.t = 0.18

    def atualizar(self, dt):
        if self.t > 0:
            self.t = max(0.0, self.t - dt)
            self.transform.y = self.y0 + math.sin(self.t / 0.18 * math.pi) * 14
        else:
            self.transform.y = self.y0

    def esvaziar(self):
        sr = self.obter("SpriteRenderer")
        if sr is not None:
            sr.imagem = self.imagem_vazio

    def soltar(self, prefab):
        x, y = self.transform.x, self.y0 + 64
        self.cena.instanciar(f"Assets/Prefabs/{prefab}.prefab", x, y)


class Coletavel(Componente):
    """``tipo``: moeda (gira parada), moeda_bloco (sai do bloco, sobe e some sozinha) ou cogumelo
    (anda e dá uma vida)."""
    CAMPOS = {"tipo": "str", "quadros": "str", "velocidade": "float"}
    tipo = "moeda"
    quadros = ""
    velocidade = 120.0

    def iniciar(self):
        self.t = 0.0
        self.lista = [q.strip() for q in self.quadros.split(",") if q.strip()]
        self.render = self.obter("SpriteRenderer")
        self.rb = self.obter("CorpoRigido")
        self.pego = False
        if self.tipo == "moeda_bloco" and self.rb:
            self.rb.vy = 720
        if self.tipo == "cogumelo" and self.rb:
            self.rb.vy = 300
            self.rb.vx = self.velocidade

    def atualizar(self, dt):
        self.t += dt
        if self.lista and self.render:
            self.render.imagem = self.lista[int(self.t * 8) % len(self.lista)]
        if self.tipo == "moeda_bloco" and self.t > 0.45 and not self.pego:
            self._pegar()
        if self.tipo == "cogumelo" and self.rb:
            if self.rb.na_parede:
                self.velocidade = -self.velocidade
            self.rb.vx = self.velocidade
            if self.transform.y < -300:
                self.gameobject.destruir()

    def _pegar(self):
        self.pego = True
        h = P.hud(self.cena)
        x, y = self.transform.posicao_mundo
        if self.tipo in ("moeda", "moeda_bloco"):
            P.tocar(self.cena, "moeda", 0.45)
            if h:
                h.pegar_moeda(x, y)
        elif self.tipo == "cogumelo":
            P.tocar(self.cena, "poder")
            j = P.jogador(self.cena)
            if j:
                j.ganhar_vida()
            if h:
                h.somar(1000, x, y)
                h.mensagem("Vida extra!")
        self.cena.instanciar("Assets/Prefabs/brilho.prefab", x, y)
        self.gameobject.destruir()

    def ao_entrar_colisao(self, outro):
        if not self.pego and outro.gameobject.tag == "jogador" and self.tipo != "moeda_bloco":
            self._pegar()


class Mola(Componente):
    """Quem cai em cima é jogado bem para o alto."""
    CAMPOS = {"forca": "float", "imagem_solta": "str"}
    forca = 1350.0
    imagem_solta = "Assets/Sprites/Tiles/spring_out.png"

    def iniciar(self):
        self.render = self.obter("SpriteRenderer")
        self.normal = self.render.imagem if self.render else ""
        self.t = 0.0

    def atualizar(self, dt):
        if self.t > 0:
            self.t -= dt
            if self.t <= 0 and self.render:
                self.render.imagem = self.normal

    def ao_entrar_colisao(self, outro):
        rb = outro.gameobject.obter("CorpoRigido")
        if outro.gameobject.tag == "jogador" and rb is not None and rb.vy <= 0:
            rb.vy = self.forca
            self.t = 0.3
            if self.render:
                self.render.imagem = self.imagem_solta
            P.tocar(self.cena, "pulo_alto")


class Checkpoint(Componente):
    """Bandeirinha do meio da fase: depois de passar por ela, quem cai no buraco volta aqui."""
    CAMPOS = {"quadros_ativo": "str"}
    quadros_ativo = ""

    def iniciar(self):
        self.ativo = False
        self.t = 0.0
        self.render = self.obter("SpriteRenderer")
        self.lista = [q.strip() for q in self.quadros_ativo.split(",") if q.strip()]

    def atualizar(self, dt):
        self.t += dt
        if self.ativo and self.lista and self.render:
            self.render.imagem = self.lista[int(self.t * 5) % len(self.lista)]

    def ao_entrar_colisao(self, outro):
        if self.ativo or outro.gameobject.tag != "jogador":
            return
        self.ativo = True
        j = outro.gameobject.obter("Jogador")
        if j:
            j.ponto_retorno = (self.transform.x, self.transform.y + 20)
        P.tocar(self.cena, "alerta")
        h = P.hud(self.cena)
        if h:
            h.mensagem("Checkpoint!")


class Bandeira(Componente):
    """Fim da fase."""
    CAMPOS = {"quadros": "str"}
    quadros = ""

    def iniciar(self):
        self.t = 0.0
        self.render = self.obter("SpriteRenderer")
        self.lista = [q.strip() for q in self.quadros.split(",") if q.strip()]
        self.pega = False

    def atualizar(self, dt):
        self.t += dt
        if self.lista and self.render:
            self.render.imagem = self.lista[int(self.t * 5) % len(self.lista)]

    def ao_entrar_colisao(self, outro):
        if self.pega or outro.gameobject.tag != "jogador":
            return
        self.pega = True
        j = outro.gameobject.obter("Jogador")
        if j:
            j.vencer()
        P.tocar(self.cena, "vitoria", 0.8)
        h = P.hud(self.cena)
        if h:
            h.vitoria()


class CameraPlataforma(Componente):
    """Segue o jogador olhando um pouco para frente, sem mostrar fora do mapa (limites do MapaTiles)."""
    CAMPOS = {"alvo": "str", "mapa": "str", "suavidade": "float", "adiante": "float"}
    alvo = "Jogador"
    mapa = "Mapa"
    suavidade = 6.0
    adiante = 90.0

    def iniciar(self):
        self._adiante = 0.0

    def atualizar_tardio(self, dt):
        go = self.cena.encontrar(self.alvo)
        if go is None:
            return
        cam = self.motor.camera
        x, y = go.transform.posicao_mundo
        rb = go.obter("CorpoRigido")
        if rb is not None and abs(rb.vx) > 30:
            self._adiante += ((self.adiante if rb.vx > 0 else -self.adiante) - self._adiante) * min(1.0, 2 * dt)
        alvo_x, alvo_y = x + self._adiante, y + 60
        t = self.transform
        k = min(1.0, self.suavidade * dt)
        t.x += (alvo_x - t.x) * k
        t.y += (alvo_y - t.y) * k * 0.6
        m = self.cena.encontrar(self.mapa)
        mapa = m.obter("MapaTiles") if m else None
        if mapa is not None and mapa.linhas:
            mx, my = m.transform.posicao_mundo
            hw = cam.largura / (2 * cam.zoom)
            hh = cam.altura / (2 * cam.zoom)
            t.x = min(max(t.x, mx + hw), mx + mapa.largura_mundo - hw)
            t.y = min(max(t.y, my - mapa.altura_mundo + hh), my - hh)
        cam.x, cam.y = t.x, t.y          # já neste quadro (sem esperar a CameraPrincipal)
