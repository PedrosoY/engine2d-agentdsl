"""Arena dos Sobreviventes — estilo Vampire Survivors.

WASD/setas movem; as armas atiram sozinhas. Colete os cristais para subir de
nível e escolher melhorias. Sobreviva até o minuto 6 ou derrote o chefe (min 4).
ESC pausa · F1 editor · F2 reinicia.

Todo o comportamento de inimigos, armas e ondas está em arena.agt (AgentDSL).
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from agentdsl.componente import ComportamentoAgente, ServicoAgentes
from agentdsl.semantica import ATOMO, NUM, Assinatura
from engine2d import (CameraSegue, Cena, Colisor, Componente, CorpoRigido, Piscar,
                      SpriteRenderer, TempoDeVida)
from engine2d.ui import CORES
from jogos.comum import SH, LogDSL, Pausa, criar_fumaca, painel_fim, td

PASTA = Path(__file__).parent
TAM_MUNDO = 2560
LIMITE_INIMIGOS = 260

IMG = {
    "jogador": SH + "Survivor 1/survivor1_gun.png",
    "zumbi": SH + "Zombie 1/zoimbie1_hold.png",
    "corredor": SH + "Man Brown/manBrown_hold.png",
    "brutamontes": SH + "Robot 1/robot1_hold.png",
    "atirador": SH + "Soldier 1/soldier1_gun.png",
    "chefe": SH + "Robot 1/robot1_machine.png",
}


# =============================================================================
# Componentes do jogo
# =============================================================================
class Jogador(Componente):
    CAMPOS = {"vida": "float", "vida_max": "float", "velocidade": "float", "ima": "float",
              "multiplicador_dano": "float"}
    vida = 100.0
    vida_max = 100.0
    velocidade = 210.0
    ima = 90.0
    multiplicador_dano = 1.0

    def iniciar(self):
        self.rb = self.obter(CorpoRigido)
        self.piscar = self.obter(Piscar)
        self.invencivel = 0.0
        self.xp = 0
        self.nivel = 1
        self.xp_proximo = 5

    def atualizar(self, dt):
        dx, dy = self.motor.entrada.direcao_wasd()
        self.rb.vx, self.rb.vy = dx * self.velocidade, dy * self.velocidade
        if dx or dy:
            self.transform.rotacao = math.degrees(math.atan2(dy, dx))
        t = self.transform
        t.x = min(max(t.x, 40), TAM_MUNDO - 40)
        t.y = min(max(t.y, 40), TAM_MUNDO - 40)
        self.invencivel = max(0.0, self.invencivel - dt)
        self.vida = min(self.vida_max, self.vida + 0.4 * dt)   # regeneração lenta

    def ferir(self, dano):
        if self.invencivel > 0 or self.vida <= 0:
            return
        self.vida -= dano
        self.invencivel = 0.25
        self.piscar.disparar()

    def ganhar_xp(self, n):
        self.xp += n
        gerente = self.cena.servicos["gerente"]
        while self.xp >= self.xp_proximo:
            self.xp -= self.xp_proximo
            self.nivel += 1
            self.xp_proximo = int(5 + self.nivel * 4.5)
            gerente.subir_nivel()


class Inimigo(Componente):
    """Gera as percepções do inimigo e acumula o dano do quadro num único pulso."""

    CAMPOS = {"raio_toque": "float"}
    raio_toque = 30.0

    def iniciar(self):
        self.dano_acumulado = 0.0
        self.agente = self.obter(ComportamentoAgente)
        self.jogador = self.cena.encontrar("jogador")

    def receber_dano(self, d):
        self.dano_acumulado += d

    def atualizar(self, dt):
        corpo = self.agente
        if corpo is None or not corpo._iniciado:
            return
        if self.dano_acumulado > 0:
            corpo.pulsar("atingido", (round(self.dano_acumulado, 1),))
            self.dano_acumulado = 0.0
        jx, jy = self.jogador.transform.posicao_mundo
        x, y = self.transform.posicao_mundo
        d = math.hypot(jx - x, jy - y)
        p = set()
        if d < self.raio_toque * self.transform.escala_x + 22:
            p.add(("tocando_jogador", ()))
        alcance = corpo.crenca_num("alcance")
        if alcance and d < alcance:
            p.add(("jogador_perto", ()))
        corpo.perceber(p)

    def ao_destruir(self):
        if self.cena is not None and "gerente" in self.cena.servicos:
            x, y = self.transform.posicao_mundo
            criar_fumaca(self.cena, x, y, 0.7 * self.transform.escala_x)
            self.cena.servicos["gerente"].abates += 1


class Projetil(Componente):
    CAMPOS = {"dano": "float", "perfuracao": "int", "alvo": "str"}
    dano = 5.0
    perfuracao = 1
    alvo = "inimigo"      # camada física que este projétil fere

    def iniciar(self):
        self.atingidos = set()

    def ao_entrar_colisao(self, outro):
        if self.perfuracao <= 0 or outro.camada_fisica != self.alvo:
            return
        go = outro.gameobject
        if go.id in self.atingidos:
            return
        self.atingidos.add(go.id)
        if self.alvo == "inimigo":
            ini = go.obter(Inimigo)
            if ini:
                ini.receber_dano(self.dano)
        else:
            j = go.obter(Jogador)
            if j:
                j.ferir(self.dano)
        self.perfuracao -= 1
        if self.perfuracao <= 0:
            self.gameobject.destruir()


class Serra(Componente):
    """Lâmina que orbita o jogador (filha de um pivô que gira: hierarquia de cena)."""

    CAMPOS = {"dano": "float"}
    dano = 8.0

    def iniciar(self):
        self.recarga: dict[int, float] = {}

    def atualizar(self, dt):
        self.transform.rotacao += 720 * dt
        for k in list(self.recarga):
            self.recarga[k] -= dt
            if self.recarga[k] <= 0:
                del self.recarga[k]

    def ao_entrar_colisao(self, outro):
        if outro.camada_fisica != "inimigo":
            return
        go = outro.gameobject
        if go.id in self.recarga:
            return
        self.recarga[go.id] = 0.5
        ini = go.obter(Inimigo)
        if ini:
            ini.receber_dano(self.dano)


class Girar(Componente):
    CAMPOS = {"velocidade": "float"}
    velocidade = 180.0

    def atualizar(self, dt):
        self.transform.rotacao += self.velocidade * dt


class Gema(Componente):
    CAMPOS = {"valor": "int"}
    valor = 1

    def iniciar(self):
        self.jogador = self.cena.encontrar("jogador")
        self.comp = self.jogador.obter(Jogador)
        self.atraida = False
        self.vel = 0.0

    def atualizar(self, dt):
        jx, jy = self.jogador.transform.posicao_mundo
        t = self.transform
        dx, dy = jx - t.x, jy - t.y
        d = math.hypot(dx, dy)
        if not self.atraida and d < self.comp.ima:
            self.atraida = True
        if self.atraida:
            self.vel = min(900.0, self.vel + 1400 * dt)
            passo = min(d, self.vel * dt)
            t.x += dx / (d or 1) * passo
            t.y += dy / (d or 1) * passo
            if d < 18:
                self.comp.ganhar_xp(self.valor)
                self.gameobject.destruir()


class Anel(Componente):
    """Efeito visual da onda de choque: cresce e some."""
    CAMPOS = {"raio": "float"}
    raio = 150.0

    def iniciar(self):
        self.t = 0.0
        self.render = self.obter(SpriteRenderer)

    def atualizar(self, dt):
        self.t += dt
        f = min(1.0, self.t / 0.3)
        s = (self.raio * 2 / 256) * (0.3 + 0.7 * f)
        self.transform.escala_x = self.transform.escala_y = s
        self.render.cor = (1, 1, 1, 1 - f)
        if f >= 1:
            self.gameobject.destruir()


# =============================================================================
# Gerente: relógio, ondas, nível, HUD
# =============================================================================
MELHORIAS_PASSIVAS = {
    "botas": ("Botas", "+12% de velocidade"),
    "coracao": ("Coração", "+25 de vida máxima e cura"),
    "ima": ("Ímã", "+40% de alcance de coleta"),
    "furia": ("Fúria", "+15% de dano em tudo"),
}
DESCRICAO_ARMAS = {
    "pistola": ("Pistola", ["", "", "mais dano e cadência", "+1 tiro por rajada", "perfura +1 inimigo",
                            "rajada dupla, muito rápida"]),
    "serras": ("Serras", ["", "1 serra orbitando", "mais dano e alcance", "+1 serra", "mais rápida", "+1 serra"]),
    "bomba": ("Onda de choque", ["", "explode em volta de você", "mais dano", "raio maior", "mais frequente",
                                  "devastadora"]),
}
NIVEL_MAX_ARMA = 5


class GerenteArena(Componente):
    def iniciar(self):
        self.cena.servicos["gerente"] = self
        self.jogador_go = self.cena.encontrar("jogador")
        self.jogador = self.jogador_go.obter(Jogador)
        self.srv: ServicoAgentes = self.cena.servicos["agentes"]
        self.tempo = 0.0
        self.segundo = -1
        self.abates = 0
        self.escolhas: list | None = None
        self.niveis_pendentes = 0
        self.fim = None
        self.passivas = {k: 0 for k in MELHORIAS_PASSIVAS}
        self.srv.ponto_de_invocacao = self.ponto_de_invocacao
        self.srv.pode_invocar = lambda modelo: len(self.cena.com_tag("inimigo")) < LIMITE_INIMIGOS or modelo == "chefe"

    def ponto_de_invocacao(self, modelo):
        """Nasce num anel fora da tela, em volta do jogador."""
        jx, jy = self.jogador_go.transform.posicao_mundo
        for _ in range(8):
            a = random.uniform(0, 2 * math.pi)
            r = random.uniform(720, 900)
            x, y = jx + r * math.cos(a), jy + r * math.sin(a)
            if 30 < x < TAM_MUNDO - 30 and 30 < y < TAM_MUNDO - 30:
                return x, y
        return min(max(x, 30), TAM_MUNDO - 30), min(max(y, 30), TAM_MUNDO - 30)

    def atualizar(self, dt):
        if self.fim:
            return
        self.tempo += dt
        s = int(self.tempo)
        if s != self.segundo:
            self.segundo = s
            for nome in ("diretor", "elite"):     # relógio da partida → percepções dos diretores
                corpo = self.srv.sis.agentes[nome].corpo
                if corpo is not None:
                    corpo.perceber({("segundo", (s,)), ("minuto", (s // 60,))})
        if self.jogador.vida <= 0:
            self.fim = "derrota"
            self.motor.pausado = True

    # --- nível ---------------------------------------------------------------------
    def subir_nivel(self):
        self.niveis_pendentes += 1
        if self.escolhas is None:
            self._sortear()

    def _sortear(self):
        opcoes = []
        for nome in DESCRICAO_ARMAS:
            n = self._nivel_arma(nome)
            if n < NIVEL_MAX_ARMA:
                opcoes.append(("arma", nome, n + 1))
        for k in MELHORIAS_PASSIVAS:
            if self.passivas[k] < 5:
                opcoes.append(("passiva", k, self.passivas[k] + 1))
        random.shuffle(opcoes)
        self.escolhas = opcoes[:3]
        self.motor.pausado = True

    def _nivel_arma(self, nome):
        ag = self.srv.sis.agentes[nome]
        for _, args in ag.crencas_com("nivel", 1):
            return int(args[0])
        return 0

    def escolher(self, opcao):
        tipo, nome, novo = opcao
        if tipo == "arma":
            ag = self.srv.sis.agentes[nome]
            ag.remover("nivel", (novo - 1,))
            ag.adicionar("nivel", (novo,))       # evento +nivel(N): a DSL aplica a melhoria
        else:
            self.passivas[nome] += 1
            j = self.jogador
            if nome == "botas":
                j.velocidade *= 1.12
            elif nome == "coracao":
                j.vida_max += 25
                j.vida = j.vida_max
            elif nome == "ima":
                j.ima *= 1.4
            elif nome == "furia":
                j.multiplicador_dano *= 1.15
        self.niveis_pendentes -= 1
        if self.niveis_pendentes > 0:
            self._sortear()
        else:
            self.escolhas = None
            self.motor.pausado = False

    def vencer(self):
        if not self.fim:
            self.fim = "vitoria"
            self.motor.pausado = True

    # --- HUD --------------------------------------------------------------------------
    def desenhar_ui(self, ui):
        j = self.jogador
        W = ui.largura
        ui.barra((0, 0, W, 14), j.xp / j.xp_proximo, cor=CORES["azul"], fundo=(20, 20, 30, 230))
        ui.texto(W - 10, 18, f"Nível {j.nivel}", 20, ancora="topright", negrito=True)
        m, s = divmod(int(self.tempo), 60)
        ui.texto(W / 2, 22, f"{m:02d}:{s:02d}", 26, ancora="midtop", negrito=True)
        ui.texto(10, 20, f"Abates: {self.abates}", 18)
        n_ini = len(self.cena.com_tag("inimigo"))
        ui.texto(10, 42, f"Inimigos: {n_ini}  ·  FPS {self.motor.fps_medio:.0f}", 14, cor=(200, 200, 200))
        armas = "  ".join(f"{DESCRICAO_ARMAS[a][0]} {self._nivel_arma(a)}" for a in DESCRICAO_ARMAS
                          if self._nivel_arma(a) > 0)
        ui.texto(10, 60, armas, 14, cor=(220, 220, 160))
        # barra de vida embaixo do jogador
        x, y = ui.mundo_para_tela(*self.jogador_go.transform.posicao_mundo)
        ui.barra((x - 28, y + 30, 56, 7), j.vida / j.vida_max, cor=CORES["vermelho"])

        if self.escolhas:
            ui.sobrepor(self._ui_escolhas)
        elif self.fim == "derrota":
            painel_fim(ui, self.motor, self.cena, "Você caiu!",
                       [f"Sobreviveu {m:02d}:{s:02d}", f"Abates: {self.abates}", f"Nível: {j.nivel}"],
                       cor=CORES["vermelho"])
        elif self.fim == "vitoria":
            painel_fim(ui, self.motor, self.cena, "Vitória!",
                       [f"Tempo {m:02d}:{s:02d}", f"Abates: {self.abates}", f"Nível: {j.nivel}"],
                       cor=CORES["verde"])

    def _ui_escolhas(self, ui):
        cx, cy = ui.largura // 2, ui.altura // 2
        ui.retangulo((0, 0, ui.largura, ui.altura), (0, 0, 0, 120), raio=0, bloquear=True)
        ui.texto(cx, cy - 170, "Subiu de nível! Escolha uma melhoria", 28, ancora="center", negrito=True)
        for i, op in enumerate(self.escolhas):
            tipo, nome, novo = op
            r = (cx - 390 + i * 265, cy - 120, 250, 230)
            if tipo == "arma":
                titulo, descs = DESCRICAO_ARMAS[nome]
                linha1 = f"{titulo} — nível {novo}" if novo > 1 else f"{titulo} (nova!)"
                linha2 = descs[novo]
                icone = {"pistola": td(272), "serras": td(134), "bomba": "anel.png"}[nome]
            else:
                titulo, desc = MELHORIAS_PASSIVAS[nome]
                linha1, linha2 = f"{titulo} {novo}", desc
                icone = {"botas": td(22), "coracao": td(250), "ima": td(135), "furia": td(296)}[nome]
            if ui.botao(r, "", imagem=None):
                self.escolher(op)
                return
            ui.desenhar_imagem(icone, r[0] + r[2] / 2, r[1] + 70, tamanho=72)
            ui.texto(r[0] + r[2] / 2, r[1] + 135, linha1, 18, ancora="center", negrito=True)
            ui.texto(r[0] + r[2] / 2, r[1] + 165, linha2, 15, ancora="center", cor=(210, 210, 220))
            ui.texto(r[0] + r[2] / 2, r[1] + 205, f"tecla {i + 1}", 12, ancora="center", cor=(150, 150, 160))
            if self.motor.entrada.tecla_baixou(str(i + 1)):
                self.escolher(op)
                return


# =============================================================================
# Ações do jogo chamadas pela DSL
# =============================================================================
def _gerente(corpo):
    from jogos.arena.arena import GerenteArena  # noqa: F401
    return _cena_atual.servicos["gerente"]


_cena_atual = None


def acao_ferir_jogador(corpo, agente, dano):
    _cena_atual.servicos["gerente"].jogador.ferir(float(dano))


def acao_soltar_xp(corpo, agente, n):
    if corpo is None:
        return
    x, y = corpo.transform.posicao_mundo
    n = int(n)
    valor = 5 if n >= 5 else 1
    for _ in range(max(1, n // valor)):
        _cena_atual.criar("cristal", x + random.uniform(-14, 14), y + random.uniform(-14, 14), escala=0.45,
                          componentes=[SpriteRenderer(imagem=td(137 if valor == 1 else 136), camada=1,
                                                      cor=(0.45, 0.85, 1.0, 1) if valor == 1 else (1, 0.5, 1, 1)),
                                       Gema(valor=valor)])


def _criar_projetil(x, y, ang, vel, dano, perfuracao, alvo, imagem, escala=1.0, camada_fisica="projetil"):
    rad = math.radians(ang)
    _cena_atual.criar("projétil", x, y, rotacao=ang, escala=escala, componentes=[
        SpriteRenderer(imagem=imagem, camada=4),
        CorpoRigido(vx=math.cos(rad) * vel, vy=math.sin(rad) * vel, cinematico=True),
        Colisor(raio=8, gatilho=True, camada_fisica=camada_fisica),
        Projetil(dano=dano, perfuracao=int(perfuracao), alvo=alvo),
        TempoDeVida(segundos=1.6)])


def acao_atirar_mais_proximo(corpo, agente, dano, vel, qtd, perfura):
    g = _cena_atual.servicos["gerente"]
    jx, jy = g.jogador_go.transform.posicao_mundo
    inimigos = []
    for c in _cena_atual.fisica.consultar_circulo(jx, jy, 650, camada="inimigo"):
        cx, cy = c.centro()
        inimigos.append(((cx - jx) ** 2 + (cy - jy) ** 2, cx, cy))
    if not inimigos:
        return
    inimigos.sort()
    qtd = max(1, int(qtd))
    for i in range(qtd):
        _, cx, cy = inimigos[i % len(inimigos)]
        ang = math.degrees(math.atan2(cy - jy, cx - jx)) + (0 if i < len(inimigos) else random.uniform(-12, 12))
        _criar_projetil(jx, jy, ang, vel, dano * g.jogador.multiplicador_dano, perfura, "inimigo", td(272), 0.9)


def acao_atirar_no_jogador(corpo, agente, dano, vel):
    if corpo is None:
        return
    g = _cena_atual.servicos["gerente"]
    x, y = corpo.transform.posicao_mundo
    jx, jy = g.jogador_go.transform.posicao_mundo
    ang = math.degrees(math.atan2(jy - y, jx - x))
    corpo.transform.rotacao = ang
    _criar_projetil(x, y, ang, vel, dano, 1, "jogador", td(296), 0.7, camada_fisica="projetil_inimigo")


def acao_serras(corpo, agente, qtd, dano, raio, vel):
    g = _cena_atual.servicos["gerente"]
    j = g.jogador_go
    antigo = _cena_atual.encontrar("Pivô das serras")
    if antigo is not None:
        antigo.destruir()
    pivo = _cena_atual.criar("Pivô das serras", 0, 0, pai=j, componentes=[Girar(velocidade=float(vel))])
    pivo.transform.rotacao = -j.transform.rotacao   # filho herda rotação do pai; compensado em Girar
    qtd = max(1, int(qtd))
    for i in range(qtd):
        a = 2 * math.pi * i / qtd
        _cena_atual.criar(f"serra {i + 1}", math.cos(a) * raio, math.sin(a) * raio, pai=pivo, escala=0.8,
                          componentes=[SpriteRenderer(imagem=td(134), camada=4),
                                       Colisor(raio=22, gatilho=True, camada_fisica="projetil"),
                                       Serra(dano=float(dano) * g.jogador.multiplicador_dano)])


def acao_onda_de_choque(corpo, agente, dano, raio):
    g = _cena_atual.servicos["gerente"]
    jx, jy = g.jogador_go.transform.posicao_mundo
    for c in _cena_atual.fisica.consultar_circulo(jx, jy, float(raio), camada="inimigo"):
        ini = c.gameobject.obter(Inimigo)
        if ini:
            ini.receber_dano(float(dano) * g.jogador.multiplicador_dano)
    _cena_atual.criar("onda", jx, jy, componentes=[SpriteRenderer(imagem="anel.png", camada=5), Anel(raio=float(raio))])


def acao_vencer(corpo, agente):
    _cena_atual.servicos["gerente"].vencer()


ACOES_JOGO = {
    "ferir_jogador": (Assinatura((NUM,), "tira vida do jogador"), acao_ferir_jogador),
    "soltar_xp": (Assinatura((NUM,), "solta cristais de experiência"), acao_soltar_xp),
    "atirar_no_jogador": (Assinatura((NUM, NUM), "projétil inimigo (dano, velocidade)"), acao_atirar_no_jogador),
    "atirar_mais_proximo": (Assinatura((NUM, NUM, NUM, NUM), "tiros nos inimigos mais próximos"),
                            acao_atirar_mais_proximo),
    "serras": (Assinatura((NUM, NUM, NUM, NUM), "serras orbitando o jogador"), acao_serras),
    "onda_de_choque": (Assinatura((NUM, NUM), "dano em área em volta do jogador"), acao_onda_de_choque),
    "vencer": (Assinatura((), "termina a partida com vitória"), acao_vencer),
}
PERCEPCOES = {
    ("atingido", 1): (NUM,),
    ("tocando_jogador", 0): (),
    ("jogador_perto", 0): (),
    ("segundo", 1): (NUM,),
    ("minuto", 1): (NUM,),
}
ALVOS = ("jogador",)


# =============================================================================
# Montagem da cena
# =============================================================================
def prefab_inimigo(img, raio, massa=1.0, escala=1.0):
    return {"nome": "inimigo", "tag": "inimigo", "transform": {"escala": escala},
            "componentes": [
                {"tipo": "SpriteRenderer", "campos": {"imagem": img, "camada": 2}},
                {"tipo": "CorpoRigido", "campos": {"massa": massa}},
                {"tipo": "Colisor", "campos": {"raio": raio, "camada_fisica": "inimigo"}},
                {"tipo": "Inimigo", "campos": {"raio_toque": raio}},
                {"tipo": "Piscar", "campos": {}}]}


def criar_cena(arquivo_agt: str | Path | None = None) -> Cena:
    global _cena_atual
    cena = Cena("Arena")
    _cena_atual = cena
    cena.servicos["fabrica"] = lambda: criar_cena(arquivo_agt)
    f = cena.fisica
    for a, b in [("projetil", "projetil"), ("projetil", "jogador"), ("projetil_inimigo", "inimigo"),
                 ("projetil_inimigo", "projetil"), ("projetil_inimigo", "projetil_inimigo"),
                 ("projetil", "obstaculo"), ("projetil_inimigo", "obstaculo")]:
        f.ignorar(a, b)

    for modelo, (raio, massa, esc) in {"zumbi": (20, 1, 1), "corredor": (18, 0.7, 0.9),
                                       "brutamontes": (24, 4, 1.35), "atirador": (20, 1, 1),
                                       "chefe": (26, 40, 2.4)}.items():
        cena.registrar_prefab(modelo, prefab_inimigo(IMG[modelo], raio, massa, esc))

    # chão (um objeto pai com os tiles como filhos: aparece recolhido no editor)
    chao = cena.criar("Chão")
    random.seed(7)
    for i in range(TAM_MUNDO // 64 + 1):
        for j in range(TAM_MUNDO // 64 + 1):
            var = random.random()
            tile = "tile_01.png" if var < 0.8 else ("tile_02.png" if var < 0.93 else "tile_03.png")
            cena.criar("t", i * 64, j * 64, pai=chao, componentes=[SpriteRenderer(imagem=SH + "Tiles/" + tile, camada=0, estatico=True)])
    obst = cena.criar("Obstáculos")
    for k in range(70):
        x, y = random.uniform(100, TAM_MUNDO - 100), random.uniform(100, TAM_MUNDO - 100)
        if math.hypot(x - TAM_MUNDO / 2, y - TAM_MUNDO / 2) < 250:
            continue
        if k % 3:
            cena.criar(f"árvore {k}", x, y, pai=obst, escala=random.uniform(1.0, 1.5), componentes=[
                SpriteRenderer(imagem=random.choice([SH + "Tiles/tile_180.png", td(130), td(133)]), camada=5,
                               estatico=True),
                Colisor(raio=20, camada_fisica="obstaculo")])
        else:
            cena.criar(f"caixa {k}", x, y, pai=obst, componentes=[
                SpriteRenderer(imagem=SH + f"Tiles/tile_{random.choice([129, 237, 238])}.png", camada=2,
                               estatico=True),
                Colisor(raio=24, camada_fisica="obstaculo")])

    cena.criar("jogador", TAM_MUNDO / 2, TAM_MUNDO / 2, tag="jogador", componentes=[
        SpriteRenderer(imagem=IMG["jogador"], camada=3), CorpoRigido(massa=5),
        Colisor(raio=18, camada_fisica="jogador"), Jogador(), Piscar(duracao=0.2),
        CameraSegue(limitar=True, min_x=0, min_y=0, max_x=TAM_MUNDO, max_y=TAM_MUNDO)])

    caminho = Path(arquivo_agt) if arquivo_agt else PASTA / "arena.agt"
    cena.criar("Agentes (DSL)", componentes=[ServicoAgentes(
        fonte=caminho.read_text(encoding="utf-8-sig"), acoes_jogo=ACOES_JOGO, percepcoes=PERCEPCOES,
        alvos=ALVOS, prefabs={m: m for m in IMG if m != "jogador"}, arquivo=str(caminho))])
    cena.criar("Gerente", componentes=[GerenteArena(), LogDSL(), Pausa()])
    return cena
