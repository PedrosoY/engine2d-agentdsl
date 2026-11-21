"""Componentes prontos da engine (equivalentes aos built-in da Unity)."""
from __future__ import annotations

import math

from .objeto import Componente
from .sprite import Sprite


class SpriteRenderer(Componente):
    """Desenha uma imagem na posição do GameObject (Sprite Renderer)."""

    CAMPOS = {"imagem": "str", "camada": "int", "cor": "cor", "largura": "float",
              "altura": "float", "visivel": "bool", "estatico": "bool"}
    imagem = ""
    camada = 0
    cor = (1.0, 1.0, 1.0, 1.0)
    largura = 0.0      # 0 = tamanho da textura
    altura = 0.0
    visivel = True
    estatico = False   # True: a pose é copiada uma vez só (chão, cenário); o editor reativa ao mexer

    def iniciar(self):
        self._sincronizado = False
        self.sprite = None
        self._imagem_carregada = None
        self._garantir_sprite()

    def _garantir_sprite(self):
        if self.imagem == self._imagem_carregada and self.sprite is not None:
            return
        tex = self.motor.texturas.carregar(self.imagem)
        if self.sprite is None:
            self.sprite = Sprite(tex, camada=self.camada, nome=self.gameobject.nome)
            self.sprite.dados["gameobject"] = self.gameobject
            self.cena.lista.adicionar(self.sprite)
        else:
            self.sprite.textura = tex
        self._imagem_carregada = self.imagem

    def trocar_imagem(self, imagem: str) -> None:
        self.imagem = imagem
        if getattr(self, "sprite", None) is not None:
            self._garantir_sprite()

    def sincronizar(self):
        """Copia a pose do GameObject (no mundo) para o sprite antes de desenhar."""
        sp = self.sprite
        if sp is None or (self.estatico and self._sincronizado):
            return
        self._sincronizado = True
        if self.imagem != self._imagem_carregada:
            self._garantir_sprite()
        x, y, r, sx, sy = self.transform.mundo()
        t = sp.transformacao
        t.x, t.y, t.rotacao, t.sx, t.sy = x, y, r, sx, sy
        sp.largura = self.largura or sp.textura.largura
        sp.altura = self.altura or sp.textura.altura
        sp.cor = tuple(self.cor) if len(self.cor) == 4 else (*self.cor, 1.0)
        sp.camada = self.camada
        sp.visivel = self.visivel and self.habilitado and self.gameobject.ativo_na_hierarquia

    def contem_ponto(self, x: float, y: float) -> bool:
        return self.sprite is not None and self.sprite.contem_ponto(x, y)

    def ao_destruir(self):
        if getattr(self, "sprite", None) is not None and self.cena is not None:
            self.cena.lista.remover(self.sprite)
            self.sprite = None


class CorpoRigido(Componente):
    """Movimento por velocidade (Rigidbody2D simplificado, sem gravidade)."""

    CAMPOS = {"vx": "float", "vy": "float", "arrasto": "float", "massa": "float", "cinematico": "bool"}
    vx = 0.0
    vy = 0.0
    arrasto = 0.0       # fração da velocidade perdida por segundo
    massa = 1.0
    cinematico = False  # True = não é empurrado em colisões

    def iniciar(self):
        self.cena.fisica.registrar_corpo(self)

    def ao_destruir(self):
        if self.cena is not None:
            self.cena.fisica.remover_corpo(self)

    @property
    def velocidade(self) -> float:
        return math.hypot(self.vx, self.vy)


class Colisor(Componente):
    """Círculo ou caixa alinhada aos eixos. ``gatilho`` = só detecta, não empurra."""

    CAMPOS = {"forma": "str", "raio": "float", "largura": "float", "altura": "float",
              "gatilho": "bool", "camada_fisica": "str", "dx": "float", "dy": "float"}
    forma = "circulo"      # "circulo" | "caixa"
    raio = 16.0
    largura = 32.0
    altura = 32.0
    gatilho = False
    camada_fisica = "padrao"
    dx = 0.0               # deslocamento em relação ao centro do objeto
    dy = 0.0

    def iniciar(self):
        self.cena.fisica.registrar_colisor(self)

    def ao_destruir(self):
        if self.cena is not None:
            self.cena.fisica.remover_colisor(self)

    def centro(self) -> tuple[float, float]:
        x, y = self.transform.posicao_mundo
        return x + self.dx, y + self.dy

    def escala(self) -> float:
        _, _, _, sx, sy = self.transform.mundo()
        return max(abs(sx), abs(sy))

    def aabb(self) -> tuple[float, float, float, float]:
        cx, cy = self.centro()
        e = self.escala()
        if self.forma == "circulo":
            r = self.raio * e
            return cx - r, cy - r, cx + r, cy + r
        hw, hh = self.largura * e / 2, self.altura * e / 2
        return cx - hw, cy - hh, cx + hw, cy + hh


class Animador(Componente):
    """Troca a imagem do SpriteRenderer em sequência (animação por quadros)."""

    CAMPOS = {"quadros": "str", "fps": "float", "repetir": "bool", "destruir_ao_fim": "bool"}
    quadros = ""            # imagens separadas por vírgula
    fps = 8.0
    repetir = True
    destruir_ao_fim = False

    def iniciar(self):
        self._t = 0.0
        self.lista = [q.strip() for q in self.quadros.split(",") if q.strip()]
        self.render = self.obter(SpriteRenderer)

    def atualizar(self, dt):
        if not self.lista or self.render is None:
            return
        self._t += dt
        i = int(self._t * self.fps)
        if i >= len(self.lista):
            if self.destruir_ao_fim:
                self.gameobject.destruir()
                return
            i = i % len(self.lista) if self.repetir else len(self.lista) - 1
        self.render.trocar_imagem(self.lista[i])


class TempoDeVida(Componente):
    """Destrói o objeto depois de N segundos (projéteis, efeitos)."""

    CAMPOS = {"segundos": "float"}
    segundos = 1.0

    def atualizar(self, dt):
        self.segundos -= dt
        if self.segundos <= 0:
            self.gameobject.destruir()


class CameraSegue(Componente):
    """Faz a câmera seguir o objeto com suavização; opcionalmente presa a limites."""

    CAMPOS = {"suavidade": "float", "limitar": "bool", "min_x": "float", "min_y": "float",
              "max_x": "float", "max_y": "float"}
    suavidade = 8.0
    limitar = False
    min_x = min_y = 0.0
    max_x = max_y = 0.0

    def atualizar(self, dt):
        cam = self.motor.camera
        x, y = self.transform.posicao_mundo
        k = min(1.0, self.suavidade * dt) if self.suavidade > 0 else 1.0
        cam.x += (x - cam.x) * k
        cam.y += (y - cam.y) * k
        if self.limitar:
            hw = cam.largura / (2 * cam.zoom)
            hh = cam.altura / (2 * cam.zoom)
            cam.x = min(max(cam.x, self.min_x + hw), self.max_x - hw)
            cam.y = min(max(cam.y, self.min_y + hh), self.max_y - hh)


class Piscar(Componente):
    """Feedback de dano: tinge o sprite por um instante e volta à cor original."""

    CAMPOS = {"duracao": "float"}
    duracao = 0.12

    def iniciar(self):
        self._t = 0.0
        self.render = self.obter(SpriteRenderer)
        self.cor_original = tuple(self.render.cor) if self.render else (1, 1, 1, 1)

    def disparar(self, cor=(1.0, 0.35, 0.35, 1.0)):
        if self.render:
            self._t = self.duracao
            self.render.cor = cor

    def atualizar(self, dt):
        if self._t > 0:
            self._t -= dt
            if self._t <= 0 and self.render:
                self.render.cor = self.cor_original
