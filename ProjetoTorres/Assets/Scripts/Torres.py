"""Torres, projéteis e as ações de tiro usadas pela DSL.

Quando cada torre atira, quanto dano dá e o que muda a cada nível está em Assets/Agentes/torres.agt.
"""
import math

from Comum import criar_fumaca
from engine2d import Componente, SpriteRenderer
from engine2d.projeto import acao_dsl, alvo_dsl, percepcao_dsl

percepcao_dsl("inimigo_no_alcance")
# nomes usados como argumento de atirar(...) no .agt
alvo_dsl("primeiro", "ultimo", "forte", "perto", "todos", "bala", "bola", "missil", "gelo")

PROJETEIS = {"bala": ("Assets/Sprites/Efeitos/bala.png", 0.8), "bola": ("Assets/Sprites/Efeitos/bola.png", 1.2),
             "missil": ("Assets/Sprites/Efeitos/missil.png", 0.7)}


class Torre(Componente):
    """Gera a percepção inimigo_no_alcance e guarda quanto foi gasto (para vender)."""

    CAMPOS = {"tipo": "str", "investido": "int"}
    tipo = "metralhadora"
    investido = 0

    def iniciar(self):
        self.agente = self.obter("ComportamentoAgente")
        self.torreta = self.gameobject.filhos[0] if self.gameobject.filhos else None

    def alcance(self):
        return self.agente.crenca_num("alcance", 100) if self.agente and self.agente._iniciado else 100

    def nivel(self):
        return int(self.agente.crenca_num("nivel", 1)) if self.agente and self.agente._iniciado else 1

    def atualizar(self, dt):
        if self.agente is None or not self.agente._iniciado:
            return
        x, y = self.transform.posicao_mundo
        perto = self.cena.fisica.consultar_circulo(x, y, self.alcance(), camada="inimigo")
        self.agente.perceber({("inimigo_no_alcance", ())} if perto else set())


class ProjetilTD(Componente):
    CAMPOS = {"dano": "float", "velocidade": "float", "area": "float"}
    dano = 1.0
    velocidade = 600.0
    area = 0.0
    alvo = None        # definido por quem atira, antes do iniciar() rodar

    def iniciar(self):
        self.destino = None
        self.vida = 2.5

    def atualizar(self, dt):
        self.vida -= dt
        if self.alvo is not None and not self.alvo.destruido:
            self.destino = self.alvo.transform.posicao_mundo
        if self.destino is None or self.vida <= 0:
            self.gameobject.destruir()
            return
        t = self.transform
        dx, dy = self.destino[0] - t.x, self.destino[1] - t.y
        d = math.hypot(dx, dy)
        passo = self.velocidade * dt
        t.rotacao = math.degrees(math.atan2(dy, dx))
        if d <= passo + 6:
            self._acertar()
            return
        t.x += dx / d * passo
        t.y += dy / d * passo

    def _acertar(self):
        x, y = self.destino
        if self.area > 0:
            for c in self.cena.fisica.consultar_circulo(x, y, self.area, camada="inimigo"):
                ini = c.gameobject.obter("InimigoTD")
                if ini:
                    ini.receber_dano(self.dano)
            criar_fumaca(self.cena, x, y, self.area / 50)
        elif self.alvo is not None and not self.alvo.destruido:
            ini = self.alvo.obter("InimigoTD")
            if ini:
                ini.receber_dano(self.dano)
        self.gameobject.destruir()


class AnelGelo(Componente):
    CAMPOS = {"raio": "float"}
    raio = 120.0

    def iniciar(self):
        self.t = 0.0
        self.r = self.obter("SpriteRenderer")

    def atualizar(self, dt):
        self.t += dt
        f = min(1.0, self.t / 0.35)
        s = self.raio * 2 / 256 * (0.4 + 0.6 * f)
        self.transform.escala_x = self.transform.escala_y = s
        self.r.cor = (0.5, 0.8, 1.0, 0.8 * (1 - f))
        if f >= 1:
            self.gameobject.destruir()


def escolher_alvo(cena, torre_go, estrategia, alcance):
    x, y = torre_go.transform.posicao_mundo
    cand = [c.gameobject for c in cena.fisica.consultar_circulo(x, y, alcance, camada="inimigo")]
    cand = [g for g in cand if g.obter("SeguirCaminho")]
    if not cand:
        return None
    if estrategia == "forte":
        return max(cand, key=lambda g: g.obter("InimigoTD").vida())
    if estrategia == "ultimo":
        return min(cand, key=lambda g: g.obter("SeguirCaminho").progresso)
    if estrategia == "perto":
        return min(cand, key=lambda g: math.dist(g.transform.posicao_mundo, (x, y)))
    return max(cand, key=lambda g: g.obter("SeguirCaminho").progresso)   # "primeiro": o mais adiantado


@acao_dsl("atirar", "atomo", "atomo", "num", "num", "num",
          descricao="atirar(estratégia, projétil, dano, velocidade, área)")
def atirar(corpo, agente, estrategia, projetil, dano, velocidade, area):
    cena = corpo.cena
    go = corpo.gameobject
    torre = go.obter("Torre")
    x, y = go.transform.posicao_mundo
    estrategia, projetil = str(estrategia), str(projetil)
    if projetil == "gelo":     # efeito em área em volta da torre, sem projétil
        lent = corpo.crenca_num("lentidao", 0.5)
        for c in cena.fisica.consultar_circulo(x, y, float(area), camada="inimigo"):
            seg = c.gameobject.obter("SeguirCaminho")
            if seg:
                seg.desacelerar(lent)
        cena.criar("anel de gelo", x, y, componentes=[SpriteRenderer(imagem="Assets/Sprites/Efeitos/anel.png", camada=7),
                                                     AnelGelo(raio=float(area))])
        return
    alvo = escolher_alvo(cena, go, estrategia, torre.alcance())
    if alvo is None:
        return
    ax, ay = alvo.transform.posicao_mundo
    if torre.torreta is not None:   # a torreta (filha) gira; a base fica parada. As imagens apontam para cima
        torre.torreta.transform.rotacao = math.degrees(math.atan2(ay - y, ax - x)) - 90
    img, esc = PROJETEIS.get(projetil, PROJETEIS["bala"])
    p = cena.criar("projétil", x, y, escala=esc, componentes=[
        SpriteRenderer(imagem=img, camada=6),
        ProjetilTD(dano=float(dano), velocidade=float(velocidade), area=float(area))])
    p.obter("ProjetilTD").alvo = alvo


@acao_dsl("trocar_torreta", "texto", descricao="troca a imagem da torreta (usada nas melhorias)")
def trocar_torreta(corpo, agente, imagem):
    if corpo.gameobject.filhos:
        corpo.gameobject.filhos[0].obter("SpriteRenderer").trocar_imagem(str(imagem))
