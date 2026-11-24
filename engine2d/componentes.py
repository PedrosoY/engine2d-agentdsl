"""Componentes prontos da engine."""
from __future__ import annotations

import math

from .objeto import Componente
from .sprite import Sprite


class SpriteRenderer(Componente):
    """Desenha uma imagem na posição do GameObject.

    Ordem de desenho: ``camada_desenho`` (lista das Configurações do projeto: as primeiras ficam
    atrás), depois ``ordem`` (menor = mais atrás) e, empatando, a ordem na Hierarchy (quem vem
    depois fica na frente). ``imagem`` pode ser um PNG do projeto ou um sprite embutido
    ("embutido:quadrado", "embutido:circulo", "embutido:triangulo"...)."""

    MENU = "Renderização"
    EXECUTA_NO_EDITOR = True   # aparece na Scene mesmo fora do Play

    CAMPOS = {"imagem": "str", "cor": "cor", "camada_desenho": "camada_desenho", "ordem": "int",
              "virar_x": "bool", "virar_y": "bool", "largura": "float", "altura": "float",
              "visivel": "bool", "estatico": "bool", "receber_luz": "bool", "aditivo": "bool"}
    imagem = ""
    cor = (1.0, 1.0, 1.0, 1.0)
    camada_desenho = "Padrao"
    ordem = 0          # ordem dentro da camada de desenho
    virar_x = False    # espelha a imagem (o personagem olhando para o outro lado)
    virar_y = False
    largura = 0.0      # 0 = tamanho da textura
    altura = 0.0
    visivel = True
    estatico = False   # True: a pose é copiada uma vez só (chão, cenário); o editor reativa ao mexer
    receber_luz = True # False: ignora as luzes 2D (brilho próprio: tiros, letreiros, estrelas)
    aditivo = False    # mistura aditiva: soma a cor no que está atrás (brilho, fogo)

    # nome antigo de "ordem" (cenas e scripts antigos usam .camada)
    @property
    def camada(self) -> int:
        return self.ordem

    @camada.setter
    def camada(self, v) -> None:
        self.ordem = int(v)

    sprite = None
    _imagem_carregada = None
    _sincronizado = False

    def iniciar(self):
        self._sincronizado = False
        self.sprite = None
        self._imagem_carregada = None
        self._garantir_sprite()

    def _garantir_sprite(self):
        if self.imagem == self._imagem_carregada and self.sprite is not None:
            return
        if self.motor is None:
            return
        tex = self.motor.texturas.carregar(self.imagem)
        if self.sprite is None:
            self.sprite = Sprite(tex, camada=self.ordem, nome=self.gameobject.nome)
            self.sprite.dados["gameobject"] = self.gameobject
            self.cena.lista.adicionar(self.sprite)
        else:
            self.sprite.textura = tex
        self._imagem_carregada = self.imagem

    def trocar_imagem(self, imagem: str) -> None:
        self.imagem = imagem
        if self._iniciado and self.cena is not None:
            self._garantir_sprite()
            self._sincronizado = False

    def sincronizar(self):
        """Copia a pose do GameObject (no mundo) para o sprite antes de desenhar."""
        if self.imagem != getattr(self, "_imagem_carregada", None):
            self._garantir_sprite()           # a imagem mudou (Inspector, script ou DSL)
            self._sincronizado = False
        sp = self.sprite
        if sp is None or (self.estatico and self._sincronizado):
            return
        self._sincronizado = True
        x, y, r, sx, sy = self.transform.mundo()
        t = sp.transformacao
        t.x, t.y, t.rotacao = x, y, r
        t.sx = -sx if self.virar_x else sx
        t.sy = -sy if self.virar_y else sy
        sp.largura = self.largura or sp.textura.largura
        sp.altura = self.altura or sp.textura.altura
        sp.cor = tuple(self.cor) if len(self.cor) == 4 else (*self.cor, 1.0)
        sp.camada = self.ordem
        sp.indice_camada = self.motor.indice_camada(self.camada_desenho) if self.motor else 0
        sp.ordem_hierarquia = getattr(self.gameobject, "indice_hierarquia", 0)
        sp.iluminado, sp.aditivo = self.receber_luz, self.aditivo
        sp.visivel = self.visivel and self.habilitado and self.gameobject.ativo_na_hierarquia

    def contem_ponto(self, x: float, y: float) -> bool:
        return self.sprite is not None and self.sprite.contem_ponto(x, y)

    def ao_destruir(self):
        if getattr(self, "sprite", None) is not None and self.cena is not None:
            self.cena.lista.remover(self.sprite)
            self.sprite = None


class CorpoRigido(Componente):
    """Corpo da física. ``tipo``:

    * ``dinamico``: cai com a gravidade (vezes ``escala_gravidade``), é empurrado nas colisões e a
      velocidade contra a parede/chão é cortada (ele para em cima do chão em vez de afundar);
    * ``cinematico``: anda só pela velocidade que o script/DSL der; não cai nem é empurrado;
    * ``estatico``: não se mexe (chão, paredes). Um Colisor sem CorpoRigido também é estático.

    Depois de cada passo da física: ``no_chao`` (encostado em algo embaixo), ``no_teto``,
    ``na_parede`` (-1 esquerda, 1 direita, 0 nenhuma) e ``contatos`` (lista de (colisor, nx, ny))."""

    MENU = "Física"
    TIPOS = ("dinamico", "cinematico", "estatico")

    CAMPOS = {"tipo": "escolha:dinamico,cinematico,estatico", "vx": "float", "vy": "float", "escala_gravidade": "float", "arrasto": "float",
              "massa": "float", "elasticidade": "float", "velocidade_maxima": "float",
              "congelar_x": "bool", "congelar_y": "bool"}
    tipo = "dinamico"
    vx = 0.0
    vy = 0.0
    escala_gravidade = 1.0
    arrasto = 0.0           # fração da velocidade perdida por segundo
    massa = 1.0
    elasticidade = 0.0      # 0 = para no chão, 1 = quica sem perder nada
    velocidade_maxima = 0.0 # 0 = sem limite (útil para a queda não ficar rápida demais)
    congelar_x = False
    congelar_y = False

    no_chao = no_teto = False
    na_parede = 0

    # compatível com cenas antigas e com quem escreve CorpoRigido(cinematico=True)
    @property
    def cinematico(self) -> bool:
        return self.tipo != "dinamico"

    @cinematico.setter
    def cinematico(self, v: bool) -> None:
        if v:
            if self.tipo == "dinamico":
                self.tipo = "cinematico"
        elif self.tipo != "dinamico":
            self.tipo = "dinamico"

    def iniciar(self):
        self.contatos = []
        self.cena.fisica.registrar_corpo(self)

    def ao_destruir(self):
        if self.cena is not None:
            self.cena.fisica.remover_corpo(self)

    @property
    def velocidade(self) -> float:
        return math.hypot(self.vx, self.vy)

    def impulso(self, ix: float, iy: float) -> None:
        """Soma um impulso à velocidade (dividido pela massa), ex.: pulo, empurrão, explosão."""
        m = max(self.massa, 1e-6)
        self.vx += ix / m
        self.vy += iy / m


class Colisor(Componente):
    """Círculo ou caixa alinhada aos eixos. ``gatilho`` = só detecta, não empurra."""

    MENU = "Física"

    CAMPOS = {"forma": "escolha:circulo,caixa", "raio": "float", "largura": "float", "altura": "float",
              "gatilho": "bool", "so_por_cima": "bool", "camada_fisica": "str", "dx": "float", "dy": "float"}
    forma = "circulo"      # "circulo" | "caixa"
    raio = 16.0
    largura = 32.0
    altura = 32.0
    gatilho = False
    so_por_cima = False    # plataforma atravessável: segura quem cai de cima, deixa passar quem vem de baixo
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

    MENU = "Renderização"

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

    MENU = "Utilitários"

    CAMPOS = {"segundos": "float"}
    segundos = 1.0

    def atualizar(self, dt):
        self.segundos -= dt
        if self.segundos <= 0:
            self.gameobject.destruir()


class CameraSegue(Componente):
    """Faz a câmera seguir o objeto com suavização; opcionalmente presa a limites."""

    MENU = "Renderização"

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

    MENU = "Utilitários"

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


class CameraPrincipal(Componente):
    """A câmera do jogo: a tela mostra o que ela enxerga."""

    CAMPOS = {"zoom": "float", "cor_fundo": "cor"}
    zoom = 1.0
    cor_fundo = (0.08, 0.09, 0.12, 1.0)
    MENU = "Renderização"

    def iniciar(self):
        self.atualizar_tardio(0)

    def atualizar_tardio(self, dt):
        cam = self.motor.camera
        cam.x, cam.y = self.transform.posicao_mundo
        cam.zoom = self.zoom
        self.motor.renderizador.cor_fundo = tuple(self.cor_fundo)


class TextoUI(Componente):
    """Texto fixo na tela. x, y em pixels a partir do canto superior esquerdo."""

    CAMPOS = {"texto": "str", "tamanho": "int", "cor": "cor", "x": "float", "y": "float", "negrito": "bool",
              "ancora": "str", "fonte": "str"}
    texto = "Texto"
    tamanho = 24
    cor = (1.0, 1.0, 1.0, 1.0)
    x = 20.0
    y = 20.0
    negrito = False
    ancora = "topleft"     # topleft, center, midtop, topright... (o ponto x, y é esse canto do texto)
    fonte = ""             # arquivo .ttf do projeto; vazio = fonte do sistema
    MENU = "UI"

    def desenhar_ui(self, ui):
        cor = tuple(int(255 * max(0.0, min(1.0, c))) for c in self.cor[:3])
        alfa = int(255 * max(0.0, min(1.0, self.cor[3]))) if len(self.cor) > 3 else 255
        ui.texto(self.x, self.y, str(self.texto), int(self.tamanho), cor=cor, negrito=self.negrito,
                 ancora=self.ancora or "topleft", fonte=self.fonte or None, alfa=alfa)



class EmissorParticulas(Componente):
    """Solta partículas (fumaça, faíscas, explosões). Cada partícula é um sprite leve, sem GameObject,
    que anda, encolhe/cresce, muda de cor e some no fim da vida.

    ``rajada`` partículas saem de uma vez ao iniciar; ``taxa`` partículas por segundo saem enquanto
    ``emitindo`` for verdadeiro. Com ``destruir_ao_fim`` o objeto some quando a última partícula acaba."""

    MENU = "Renderização"
    CAMPOS = {"imagem": "str", "rajada": "int", "taxa": "float", "emitindo": "bool", "vida": "float",
              "vida_variacao": "float", "velocidade": "float", "velocidade_variacao": "float",
              "angulo": "float", "espalhamento": "float", "tamanho_inicial": "float", "tamanho_final": "float",
              "cor_inicial": "cor", "cor_final": "cor", "gravidade": "float", "arrasto": "float",
              "girar": "float", "camada": "int", "destruir_ao_fim": "bool", "max_particulas": "int",
              "area_largura": "float", "area_altura": "float", "camada_desenho": "camada_desenho",
              "receber_luz": "bool", "aditivo": "bool"}
    imagem = ""
    rajada = 0
    taxa = 20.0
    emitindo = True
    vida = 0.8
    vida_variacao = 0.3          # fração sorteada a mais ou a menos
    velocidade = 120.0
    velocidade_variacao = 0.5
    angulo = 90.0                # direção (graus; 90 = para cima)
    espalhamento = 360.0         # abertura do cone em graus (360 = para todo lado)
    tamanho_inicial = 1.0
    tamanho_final = 0.2
    cor_inicial = (1.0, 1.0, 1.0, 1.0)
    cor_final = (1.0, 1.0, 1.0, 0.0)
    gravidade = 0.0              # px/s² para baixo
    arrasto = 0.0                # fração da velocidade perdida por segundo
    girar = 0.0                  # graus por segundo (sorteia o sentido)
    camada = 5
    destruir_ao_fim = False
    max_particulas = 300
    area_largura = 0.0           # as partículas nascem num retângulo deste tamanho (0 = num ponto)
    area_altura = 0.0
    camada_desenho = "Padrao"
    receber_luz = True
    aditivo = False              # brilho: as partículas somam a cor (explosões, fogo)

    def iniciar(self):
        import random
        self._rnd = random.Random()
        self._vivas: list[list] = []       # [sprite, vx, vy, idade, vida, giro]
        self._acumulado = 0.0
        self._tex = self.motor.texturas.carregar(self.imagem)
        if self.rajada:
            self.emitir(self.rajada)

    def emitir(self, n: int = 1, x: float | None = None, y: float | None = None) -> None:
        """Solta ``n`` partículas agora (na posição do objeto ou em x, y)."""
        if not getattr(self, "_iniciado", False) or self.cena is None:
            return
        from .sprite import Sprite
        ox, oy = self.transform.posicao_mundo if x is None else (x, y)
        r = self._rnd
        for _ in range(int(n)):
            if len(self._vivas) >= self.max_particulas:
                break
            ang = math.radians(self.angulo + r.uniform(-self.espalhamento / 2, self.espalhamento / 2))
            vel = self.velocidade * (1 + r.uniform(-self.velocidade_variacao, self.velocidade_variacao))
            vida = max(0.05, self.vida * (1 + r.uniform(-self.vida_variacao, self.vida_variacao)))
            px = ox + r.uniform(-self.area_largura / 2, self.area_largura / 2)
            py = oy + r.uniform(-self.area_altura / 2, self.area_altura / 2)
            sp = Sprite(self._tex, px, py, camada=self.camada, rotacao=r.uniform(0, 360) if self.girar else 0.0,
                        cor=self.cor_inicial, nome="particula")
            sp.indice_camada = self.motor.indice_camada(self.camada_desenho)
            sp.ordem_hierarquia = self.gameobject.indice_hierarquia
            sp.iluminado, sp.aditivo = self.receber_luz, self.aditivo
            self.cena.lista.adicionar(sp)
            giro = self.girar * r.choice((-1, 1))
            self._vivas.append([sp, vel * math.cos(ang), vel * math.sin(ang), 0.0, vida, giro])
        self._aplicar(0.0)

    def atualizar(self, dt):
        if self.emitindo and self.taxa > 0:
            self._acumulado += self.taxa * dt
            n = int(self._acumulado)
            if n:
                self._acumulado -= n
                self.emitir(n)
        self._aplicar(dt)
        if self.destruir_ao_fim and not self._vivas and (not self.emitindo or self.taxa <= 0):
            self.gameobject.destruir()

    def _aplicar(self, dt):
        ci, cf = _cor4(self.cor_inicial), _cor4(self.cor_final)
        f_arrasto = max(0.0, 1.0 - self.arrasto * dt)
        restam = []
        for p in self._vivas:
            sp = p[0]
            p[3] += dt
            k = p[3] / p[4]
            if k >= 1.0:
                self.cena.lista.remover(sp)
                continue
            p[2] -= self.gravidade * dt
            p[1] *= f_arrasto
            p[2] *= f_arrasto
            t = sp.transformacao
            t.x += p[1] * dt
            t.y += p[2] * dt
            t.rotacao += p[5] * dt
            esc = self.tamanho_inicial + (self.tamanho_final - self.tamanho_inicial) * k
            t.sx = t.sy = esc
            sp.cor = tuple(a + (b - a) * k for a, b in zip(ci, cf))
            restam.append(p)
        self._vivas = restam

    def sincronizar(self):
        """Objeto ou componente desligado: as partículas somem (em vez de ficarem congeladas na tela)."""
        if self._vivas and not (self.habilitado and self.gameobject.ativo_na_hierarquia):
            for p in self._vivas:
                self.cena.lista.remover(p[0])
            self._vivas = []

    @property
    def quantidade(self) -> int:
        return len(getattr(self, "_vivas", []))

    def ao_destruir(self):
        if self.cena is not None:
            for p in getattr(self, "_vivas", []):
                self.cena.lista.remover(p[0])
        self._vivas = []


def _cor4(c):
    c = tuple(c)
    return c if len(c) == 4 else (*c, 1.0)


class FundoRolante(Componente):
    """Imagem repetida (ladrilhos) que cobre uma área e rola sem parar: céu, estrelas, chão.

    A área tem ``largura`` x ``altura`` em volta do objeto (0 = o tamanho da tela). Aparece também
    na Scene do editor, parada."""

    MENU = "Renderização"
    EXECUTA_NO_EDITOR = True
    CAMPOS = {"imagem": "str", "velocidade_x": "float", "velocidade_y": "float", "paralaxe": "float",
              "repetir_x": "bool", "repetir_y": "bool",
              "largura": "float",
              "altura": "float", "escala": "float", "camada_desenho": "camada_desenho", "camada": "int",
              "cor": "cor", "receber_luz": "bool"}
    imagem = ""
    velocidade_x = 0.0
    velocidade_y = -60.0
    paralaxe = 0.0       # filho da câmera: 0 = fica parado na tela, 0.3 = anda 30% do que a câmera anda
    repetir_x = True     # desligado: uma faixa só (ex.: morros só na horizontal)
    repetir_y = True
    largura = 0.0
    altura = 0.0
    escala = 1.0
    camada_desenho = "Fundo"
    camada = -100
    cor = (1.0, 1.0, 1.0, 1.0)
    receber_luz = True

    def iniciar(self):
        self._sprites = []
        self._dx = self._dy = 0.0
        self._chave = None
        self._montar()

    def _area(self):
        m = self.motor
        w = self.largura or (m.camera.largura / m.camera.zoom if m else 800)
        h = self.altura or (m.camera.altura / m.camera.zoom if m else 600)
        return w, h

    def _montar(self):
        from .sprite import Sprite
        for sp in self._sprites:
            self.cena.lista.remover(sp)
        self._tex = self.motor.texturas.carregar(self.imagem)
        tw, th = self._tex.largura * self.escala, self._tex.altura * self.escala
        w, h = self._area()
        cols = int(w // max(1, tw)) + 2 if self.repetir_x else 1
        linhas = int(h // max(1, th)) + 2 if self.repetir_y else 1
        self._sprites = [Sprite(self._tex, camada=self.camada, nome="fundo") for _ in range(cols * linhas)]
        for sp in self._sprites:
            sp.largura, sp.altura = tw, th
            self.cena.lista.adicionar(sp)
        self._chave = (self.imagem, self.escala, w, h, self.camada, self.repetir_x, self.repetir_y)
        self._grade = (cols, linhas, tw, th)

    def atualizar(self, dt):
        self._dx += self.velocidade_x * dt
        self._dy += self.velocidade_y * dt

    def sincronizar(self):
        w, h = self._area()
        if self._chave != (self.imagem, self.escala, w, h, self.camada, self.repetir_x, self.repetir_y):
            self._montar()
        cols, linhas, tw, th = self._grade
        cx, cy = self.transform.posicao_mundo
        ox = self._dx - cx * self.paralaxe          # paralaxe: rola conforme o objeto (câmera) anda
        oy = self._dy - cy * self.paralaxe
        x0 = cx - w / 2 + (ox % tw) - tw if self.repetir_x else cx - tw / 2
        y0 = cy - h / 2 + (oy % th) - th if self.repetir_y else cy - th / 2
        visivel = self.habilitado and self.gameobject.ativo_na_hierarquia
        cor = _cor4(self.cor)
        indice = self.motor.indice_camada(self.camada_desenho)
        for i, sp in enumerate(self._sprites):
            c, l = i % cols, i // cols
            sp.x, sp.y = x0 + tw * (c + 0.5), y0 + th * (l + 0.5)
            sp.visivel, sp.cor = visivel, cor
            sp.indice_camada = indice
            sp.ordem_hierarquia = self.gameobject.indice_hierarquia
            sp.iluminado = self.receber_luz

    def ao_destruir(self):
        if self.cena is not None:
            for sp in getattr(self, "_sprites", []):
                self.cena.lista.remover(sp)
        self._sprites = []


class MapaTiles(Componente):
    """Grade de tiles (Tilemap): cada célula guarda uma letra, e a legenda diz o que cada letra é.

    No editor, selecione o objeto do mapa: o Inspector mostra a PALETA. Escolha um bloco e pinte
    clicando/arrastando na Scene (Shift apaga, Ctrl+clique pega o bloco que está lá). Arrastar uma
    imagem ou um prefab do Project para a paleta cria um bloco novo. Tudo é salvo num arquivo .mapa::

        # legenda (uma por linha):  letra = imagem [solido] [so_por_cima]
        G = Assets/Sprites/Tiles/grama.png solido
        n = Assets/Sprites/Tiles/nuvem.png so_por_cima
        o = prefab Assets/Prefabs/moeda.prefab          (cria o prefab nessa célula)
        ---
        ......o.o.......
        GGGGGGGGGGGG..GG

    O objeto fica no canto de cima à esquerda do mapa. Os tiles sólidos viram poucos colisores
    grandes (retângulos juntados), na ``camada_fisica`` e com a ``tag`` escolhidas. Os prefabs só
    são criados no Play; no editor aparece a imagem deles."""

    MENU = "Renderização"
    EXECUTA_NO_EDITOR = True
    CAMPOS = {"arquivo": "str", "tamanho_celula": "float", "camada_desenho": "camada_desenho", "ordem": "int",
              "camada_fisica": "str", "tag_colisores": "str"}
    arquivo = ""
    tamanho_celula = 64.0
    camada_desenho = "Padrao"
    ordem = 0
    camada_fisica = "chao"
    tag_colisores = "chao"

    VAZIO = "."
    # letras que podem virar bloco novo ('#' começa comentário, '.' é vazio, '=' separa a legenda)
    LETRAS = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
              "$%&*+<>?!@^~[](){}|/:;,'\"_`")

    def iniciar(self):
        self._celulas: dict[tuple, Sprite] = {}   # (coluna, linha) → sprite do tile
        self._auxiliares = []                       # objetos ocultos com os colisores
        self.linhas: list[str] = []
        self.legenda: dict[str, dict] = {}          # na ordem do arquivo
        self._comentarios: list[str] = []
        self._assinatura = None
        self.montar()

    # --- arquivo ---------------------------------------------------------------------------------
    def _caminho(self):
        from pathlib import Path
        p = Path(self.arquivo)
        if not p.is_absolute() and self.motor and self.motor.texturas.pasta_base:
            p = self.motor.texturas.pasta_base / p
        return p

    def _mtime(self):
        try:
            return self._caminho().stat().st_mtime
        except OSError:
            return None

    @staticmethod
    def interpretar(texto: str):
        """(comentários, legenda, linhas) de um texto .mapa."""
        comentarios, legenda, linhas, no_mapa = [], {}, [], False
        for linha in texto.splitlines():
            if no_mapa:
                linhas.append(linha.rstrip("\n"))
                continue
            s = linha.strip()
            if s.startswith("---"):
                no_mapa = True
            elif s.startswith("#"):
                comentarios.append(linha)
            elif "=" in s:
                letra, resto = s.split("=", 1)
                partes = resto.split()
                if not letra.strip() or not partes:
                    continue
                d = {"solido": "solido" in partes[1:], "so_por_cima": "so_por_cima" in partes[1:]}
                if partes[0] == "prefab" and len(partes) > 1:
                    d["prefab"] = partes[1]
                else:
                    d["imagem"] = partes[0]
                legenda[letra.strip()[0]] = d
        return comentarios, legenda, linhas

    def texto(self) -> str:
        """O mapa atual no formato do arquivo .mapa."""
        saida = list(self._comentarios) or ["# letra = imagem [solido] [so_por_cima]   ou   letra = prefab arquivo"]
        for letra, d in self.legenda.items():
            alvo = d["imagem"] if "imagem" in d else "prefab " + d["prefab"]
            saida.append(f"{letra} = {alvo}" + (" solido" if d.get("solido") else "")
                         + (" so_por_cima" if d.get("so_por_cima") else ""))
        saida.append("---")
        saida += self.linhas
        return "\n".join(saida) + "\n"

    def salvar(self) -> None:
        """Grava o mapa no arquivo (o editor chama depois de pintar)."""
        p = self._caminho()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.texto(), encoding="utf-8")
        self._assinatura = self._assinatura_atual()

    def carregar_texto(self, texto: str, salvar: bool = True) -> None:
        """Troca o mapa inteiro (usado pelo Ctrl+Z do editor)."""
        self._comentarios, self.legenda, self.linhas = self.interpretar(texto)
        if salvar:
            self.salvar()
        self._remontar()

    # --- montagem -----------------------------------------------------------------------------
    def _assinatura_atual(self):
        x0, y0 = self.transform.posicao_mundo
        return (self.arquivo, self._mtime(), x0, y0, self.tamanho_celula, self.camada_desenho, self.ordem)

    def _limpar(self):
        for sp in self._celulas.values():
            self.cena.lista.remover(sp)
        for go in self._auxiliares:
            if not go.destruido:
                self.cena._destruir_agora(go)
        self._celulas, self._auxiliares = {}, []

    def montar(self):
        """Lê o arquivo e cria os tiles (e, no Play, os colisores e os prefabs)."""
        try:
            texto = self._caminho().read_text(encoding="utf-8-sig") if self.arquivo else ""
        except OSError:
            texto = ""
        self._comentarios, self.legenda, self.linhas = self.interpretar(texto)
        self._remontar()

    def _remontar(self):
        self._limpar()
        self._assinatura = self._assinatura_atual()
        for r, linha in enumerate(self.linhas):
            for c in range(len(linha)):
                self._atualizar_celula(c, r)
        if not self.cena.modo_edicao:
            x0, y0 = self.transform.posicao_mundo
            self._colisores(x0, y0, self.tamanho_celula)

    def _atualizar_celula(self, c, r):
        """Recria só o sprite de uma célula (pintar no editor não refaz o mapa inteiro)."""
        antigo = self._celulas.pop((c, r), None)
        if antigo is not None:
            self.cena.lista.remover(antigo)
        letra = self.linhas[r][c] if r < len(self.linhas) and c < len(self.linhas[r]) else self.VAZIO
        d = self.legenda.get(letra)
        if d is None:
            return
        x0, y0 = self.transform.posicao_mundo
        cs = self.tamanho_celula
        cx, cy = x0 + cs * (c + 0.5), y0 - cs * (r + 0.5)
        if "imagem" in d:
            self._celulas[(c, r)] = self._sprite(d["imagem"], cx, cy, cs)
        elif self.cena.modo_edicao:            # prévia do prefab (só a imagem dele)
            img = _imagem_do_prefab(d["prefab"])
            if img:
                sp = self._sprite(img, cx, cy, None)
                sp.cor = (1.0, 1.0, 1.0, 0.75)
                self._celulas[(c, r)] = sp
        else:
            self.cena.instanciar(d["prefab"], cx, cy)

    def _sprite(self, imagem, x, y, cs):
        tex = self.motor.texturas.carregar(imagem)
        sp = Sprite(tex, x, y, camada=self.ordem, nome="tile")
        if cs:
            sp.largura = sp.altura = cs
        sp.indice_camada = self.motor.indice_camada(self.camada_desenho)
        sp.ordem_hierarquia = self.gameobject.indice_hierarquia
        sp.dados["gameobject"] = self.gameobject
        self.cena.lista.adicionar(sp)
        return sp

    def _colisores(self, x0, y0, cs):
        """Junta as células sólidas em retângulos: primeiro faixas na horizontal, depois faixas
        iguais de linhas vizinhas viram um retângulo só."""
        from .objeto import GameObject
        for tipo in ("solido", "so_por_cima"):
            grade = [[bool(self.legenda.get(ch, {}).get(tipo)) for ch in linha] for linha in self.linhas]
            abertos: dict[tuple, list] = {}       # (c0, c1) -> [linha_inicial, linha_final]
            retangulos = []
            for r, linha in enumerate(grade):
                faixas, c = set(), 0
                while c < len(linha):
                    if linha[c]:
                        c1 = c
                        while c1 + 1 < len(linha) and linha[c1 + 1]:
                            c1 += 1
                        faixas.add((c, c1))
                        c = c1 + 1
                    else:
                        c += 1
                for f in list(abertos):
                    if f in faixas and tipo == "solido":
                        abertos[f][1] = r
                        faixas.discard(f)
                    else:
                        retangulos.append((f, *abertos.pop(f)))
                for f in faixas:
                    abertos[f] = [r, r]
            retangulos += [(f, *v) for f, v in abertos.items()]
            for (c0, c1), r0, r1 in retangulos:
                go = GameObject("colisor do mapa", tag=self.tag_colisores)
                go.oculto = True
                go.transform.x = x0 + cs * (c0 + c1 + 1) / 2
                go.transform.y = y0 - cs * (r0 + r1 + 1) / 2
                go.adicionar(Colisor(forma="caixa", largura=cs * (c1 - c0 + 1), altura=cs * (r1 - r0 + 1),
                                     camada_fisica=self.camada_fisica, so_por_cima=tipo == "so_por_cima"))
                go.mapa = self
                self.cena.adicionar(go)
                self._auxiliares.append(go)

    def sincronizar(self):
        """No editor: refaz o mapa se o arquivo (editado fora), a posição ou os campos mudaram."""
        import time
        if not self.cena.modo_edicao:
            return
        agora = time.time()
        if agora - getattr(self, "_ultima_conferida", 0) < 0.5:
            return
        self._ultima_conferida = agora
        atual = self._assinatura_atual()
        if atual != self._assinatura:
            if atual[1] != self._assinatura[1]:
                self.montar()                   # o arquivo mudou fora do editor
            else:
                self._remontar()                # só mudou a posição/tamanho/camada
        visivel = self.habilitado and self.gameobject.ativo_na_hierarquia
        for sp in self._celulas.values():
            sp.visivel = visivel

    # --- edição (usada pela paleta do editor) ------------------------------------------------------
    def celula_em(self, x: float, y: float) -> tuple[int, int]:
        """(coluna, linha) da célula que contém o ponto (x, y) do mundo (pode ser fora do mapa)."""
        import math as _m
        x0, y0 = self.transform.posicao_mundo
        return _m.floor((x - x0) / self.tamanho_celula), _m.floor((y0 - y) / self.tamanho_celula)

    def letra_na_celula(self, c: int, r: int) -> str:
        if 0 <= r < len(self.linhas) and 0 <= c < len(self.linhas[r]):
            return self.linhas[r][c]
        return self.VAZIO

    def centro_da_celula(self, c: int, r: int) -> tuple[float, float]:
        x0, y0 = self.transform.posicao_mundo
        cs = self.tamanho_celula
        return x0 + cs * (c + 0.5), y0 - cs * (r + 0.5)

    def definir_celula(self, c: int, r: int, letra: str) -> bool:
        """Põe ``letra`` na célula (``"."`` apaga). Pintar fora do mapa aumenta o mapa; à esquerda
        ou acima, o objeto anda para o canto continuar sendo o de cima à esquerda.
        Devolve True se algo mudou."""
        letra = letra or self.VAZIO
        if self.letra_na_celula(c, r) == letra:
            return False
        if letra == self.VAZIO and not (0 <= r < len(self.linhas) and 0 <= c < len(self.linhas[r])):
            return False
        cs = self.tamanho_celula
        mudou_origem = False
        if r < 0:
            self.linhas[:0] = [""] * (-r)
            self.transform.y += cs * (-r)
            r, mudou_origem = 0, True
        if c < 0:
            self.linhas = [self.VAZIO * (-c) + l for l in self.linhas]
            self.transform.x -= cs * (-c)
            c, mudou_origem = 0, True
        while len(self.linhas) <= r:
            self.linhas.append("")
        linha = self.linhas[r]
        if len(linha) <= c:
            linha += self.VAZIO * (c + 1 - len(linha))
        self.linhas[r] = linha[:c] + letra + linha[c + 1:]
        if mudou_origem:
            self._remontar()
        else:
            self._atualizar_celula(c, r)
        return True

    def letra_livre(self) -> str:
        usadas = set(self.legenda)
        return next(ch for ch in self.LETRAS if ch not in usadas)

    def adicionar_bloco(self, imagem: str | None = None, prefab: str | None = None, solido: bool = False,
                        so_por_cima: bool = False) -> str:
        """Bloco novo na legenda (imagem ou prefab). Se já existe um igual, devolve a letra dele."""
        for letra, d in self.legenda.items():
            if (imagem and d.get("imagem") == imagem) or (prefab and d.get("prefab") == prefab):
                return letra
        letra = self.letra_livre()
        d = {"solido": solido, "so_por_cima": so_por_cima}
        if prefab:
            d["prefab"] = prefab
        else:
            d["imagem"] = imagem
        self.legenda[letra] = d
        return letra

    def definir_bloco(self, letra: str, **campos) -> None:
        """Muda ``solido`` / ``so_por_cima`` de um bloco da legenda."""
        if letra in self.legenda:
            self.legenda[letra].update(campos)

    def remover_bloco(self, letra: str) -> None:
        """Tira o bloco da legenda e apaga as células com ele."""
        if letra not in self.legenda:
            return
        del self.legenda[letra]
        self.linhas = [l.replace(letra, self.VAZIO) for l in self.linhas]
        self._remontar()

    def imagem_do_bloco(self, letra: str) -> str | None:
        d = self.legenda.get(letra)
        if d is None:
            return None
        return d.get("imagem") or _imagem_do_prefab(d.get("prefab", ""))

    # --- consultas para os scripts ------------------------------------------------------------
    @property
    def largura_mundo(self) -> float:
        return max((len(l) for l in self.linhas), default=0) * self.tamanho_celula

    @property
    def altura_mundo(self) -> float:
        return len(self.linhas) * self.tamanho_celula

    def letra_em(self, x: float, y: float) -> str:
        """A letra do mapa na posição (x, y) do mundo (" " fora do mapa)."""
        c, r = self.celula_em(x, y)
        if 0 <= r < len(self.linhas) and 0 <= c < len(self.linhas[r]):
            return self.linhas[r][c]
        return " "

    def solido_em(self, x: float, y: float) -> bool:
        d = self.legenda.get(self.letra_em(x, y))
        return bool(d and (d.get("solido") or d.get("so_por_cima")))

    def ao_destruir(self):
        if self.cena is not None:
            self._limpar()


def _imagem_do_prefab(caminho):
    import json
    from pathlib import Path
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for c in dados.get("componentes", []):
        if c.get("tipo") == "SpriteRenderer":
            return c.get("campos", {}).get("imagem")
    return None


class Luz2D(Componente):
    """Luz 2D. ``tipo``:

    * ``global``: luz ambiente da cena inteira (sem nenhuma luz global, o que nenhuma luz alcança
      fica escuro). Várias globais se somam;
    * ``ponto``: ilumina em volta, até ``raio``, cheia até ``raio_interno`` (fração do raio);
    * ``cone``: como uma lanterna, na direção ``angulo`` (somada à rotação do objeto), com
      ``abertura`` em graus.

    ``sombras``: objetos com ProjetorSombra2D bloqueiam esta luz. ``piscar``: tremulação (0 a 1),
    como fogo. ``apagar_em``: some aos poucos nesses segundos (flash de explosão)."""

    MENU = "Luz"
    EXECUTA_NO_EDITOR = True
    CAMPOS = {"tipo": "escolha:ponto,cone,global", "cor": "cor", "intensidade": "float", "raio": "float",
              "raio_interno": "float", "angulo": "float", "abertura": "float", "sombras": "bool",
              "piscar": "float", "apagar_em": "float"}
    tipo = "ponto"
    cor = (1.0, 1.0, 1.0, 1.0)
    intensidade = 1.0
    raio = 200.0
    raio_interno = 0.0
    angulo = 90.0
    abertura = 60.0
    sombras = False
    piscar = 0.0
    apagar_em = 0.0

    def iniciar(self):
        import random
        self._t = 0.0
        self._fase = random.uniform(0, 100)
        self.cena.luzes.append(self)

    def atualizar(self, dt):
        self._t += dt
        if self.apagar_em > 0 and self._t >= self.apagar_em:
            self.habilitado = False

    def intensidade_atual(self) -> float:
        i = self.intensidade
        if self.apagar_em > 0:
            i *= max(0.0, 1.0 - getattr(self, "_t", 0.0) / self.apagar_em)
        if self.piscar > 0:
            t = getattr(self, "_t", 0.0) + getattr(self, "_fase", 0.0)
            i *= 1.0 - self.piscar * (0.5 + 0.25 * math.sin(t * 13.0) + 0.25 * math.sin(t * 31.7))
        return i

    def dados(self) -> dict:
        x, y, rot, _, _ = self.transform.mundo()        # o raio não muda com a escala do objeto
        d = {"x": x, "y": y, "raio": self.raio, "cor": tuple(self.cor[:3]),
             "intensidade": self.intensidade_atual(), "interno": self.raio_interno, "sombras": self.sombras}
        if self.tipo == "cone":
            d["cone"] = (self.angulo + rot, self.abertura)
        return d

    def ao_destruir(self):
        if self.cena is not None and self in self.cena.luzes:
            self.cena.luzes.remove(self)


class ProjetorSombra2D(Componente):
    """O objeto bloqueia as luzes que têm ``sombras`` ligado. ``forma`` "colisor" usa o Colisor do
    objeto; ou um círculo/caixa próprio."""

    MENU = "Luz"
    EXECUTA_NO_EDITOR = True
    CAMPOS = {"forma": "escolha:colisor,circulo,caixa", "raio": "float", "largura": "float", "altura": "float"}
    forma = "colisor"
    raio = 20.0
    largura = 40.0
    altura = 40.0

    def iniciar(self):
        self.cena.projetores_sombra.append(self)

    def dados(self) -> dict | None:
        if not (self.habilitado and self.gameobject.ativo_na_hierarquia):
            return None
        forma, raio, larg, alt = self.forma, self.raio, self.largura, self.altura
        x, y, _, sx, sy = self.transform.mundo()
        e = max(abs(sx), abs(sy))
        if forma == "colisor":
            col = self.obter(Colisor)
            if col is None:
                return None
            x, y = col.centro()
            forma, raio, larg, alt = col.forma, col.raio, col.largura, col.altura
        if forma == "circulo":
            return {"forma": "circulo", "x": x, "y": y, "raio": raio * e}
        return {"forma": "caixa", "x": x, "y": y, "hw": larg * e / 2, "hh": alt * e / 2}

    def ao_destruir(self):
        if self.cena is not None and self in self.cena.projetores_sombra:
            self.cena.projetores_sombra.remove(self)


class FonteAudio(Componente):
    """Toca um som: ao iniciar (``tocar_ao_iniciar``) ou quando um script chama ``tocar()``.
    Com ``musica`` o arquivo vira a música de fundo (repete sem parar)."""

    MENU = "Utilitários"
    CAMPOS = {"som": "str", "volume": "float", "tocar_ao_iniciar": "bool", "musica": "bool"}
    som = ""
    volume = 1.0
    tocar_ao_iniciar = False
    musica = False

    def iniciar(self):
        if self.tocar_ao_iniciar:
            self.tocar()

    def tocar(self):
        audio = getattr(self.motor, "audio", None)
        if audio is None:
            return
        if self.musica:
            audio.musica(self.som, self.volume)
        else:
            audio.tocar(self.som, self.volume)


class CamadasFisica(Componente):
    """Matriz de colisão: quais camadas físicas não colidem entre si.

    ``ignorar``: pares de camadas que NÃO colidem, separados por vírgula, ex.:
    "bala:bala, bala:jogador"."""

    CAMPOS = {"ignorar": "str"}
    ignorar = ""
    MENU = "Física"

    def iniciar(self):
        for par in self.ignorar.split(","):
            if ":" in par:
                a, b = (p.strip() for p in par.split(":", 1))
                self.cena.fisica.ignorar(a, b)
