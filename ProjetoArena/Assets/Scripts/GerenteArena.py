"""Relógio da partida, ondas (via DSL), subida de nível, HUD e fim de jogo."""
import math
import random

from Comum import painel_fim
from engine2d import Componente
from engine2d.projeto import acao_dsl, alvo_dsl, percepcao_dsl
from engine2d.ui import CORES
from Jogador import TAM_MUNDO

percepcao_dsl("segundo", "num")     # o diretor de ondas recebe o relógio da partida
percepcao_dsl("minuto", "num")
alvo_dsl("jogador")

LIMITE_INIMIGOS = 260
ICONES = "Assets/Sprites/Icones/"
MELHORIAS_PASSIVAS = {
    "botas": ("Botas", "+12% de velocidade", ICONES + "estrela.png"),
    "coracao": ("Coração", "+25 de vida máxima e cura", ICONES + "coracao.png"),
    "ima": ("Ímã", "+40% de alcance de coleta", ICONES + "ima.png"),
    "furia": ("Fúria", "+15% de dano em tudo", ICONES + "furia.png"),
}
DESCRICAO_ARMAS = {
    "pistola": ("Pistola", "Assets/Sprites/Efeitos/bala.png",
                ["", "", "mais dano e cadência", "+1 tiro por rajada", "perfura +1 inimigo", "rajada dupla"]),
    "serras": ("Serras", "Assets/Sprites/Efeitos/serra.png",
               ["", "1 serra orbitando", "mais dano e alcance", "+1 serra", "mais rápida", "+1 serra"]),
    "bomba": ("Onda de choque", "Assets/Sprites/Efeitos/anel.png",
              ["", "explode em volta de você", "mais dano", "raio maior", "mais frequente", "devastadora"]),
}
NIVEL_MAX_ARMA = 5


class GerenteArena(Componente):
    def iniciar(self):
        self.cena.servicos["gerente"] = self
        self.jogador_go = self.cena.encontrar("jogador")
        self.jogador = self.jogador_go.obter("Jogador")
        self.srv = self.cena.servicos["agentes"]
        self.tempo = 0.0
        self.segundo = -1
        self.abates = 0
        self.escolhas = None
        self.niveis_pendentes = 0
        self.fim = None
        self.passivas = {k: 0 for k in MELHORIAS_PASSIVAS}
        self.srv.ponto_de_invocacao = self.ponto_de_invocacao
        self.srv.pode_invocar = lambda modelo: len(self.cena.com_tag("inimigo")) < LIMITE_INIMIGOS or modelo == "chefe"

    def ponto_de_invocacao(self, modelo):
        """Inimigos nascem num anel fora da tela, em volta do jogador."""
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
            for nome in ("diretor", "elite"):      # relógio → percepções dos diretores de onda
                corpo = self.srv.sis.agentes[nome].corpo
                if corpo is not None:
                    corpo.perceber({("segundo", (s,)), ("minuto", (s // 60,))})
        if self.jogador.vida <= 0:
            self.fim = "derrota"
            self.motor.pausado = True

    # --- nível ----------------------------------------------------------------------
    def subir_nivel(self):
        self.niveis_pendentes += 1
        if self.escolhas is None:
            self._sortear()

    def _sortear(self):
        opcoes = [("arma", n, self._nivel_arma(n) + 1) for n in DESCRICAO_ARMAS if self._nivel_arma(n) < NIVEL_MAX_ARMA]
        opcoes += [("passiva", k, self.passivas[k] + 1) for k in MELHORIAS_PASSIVAS if self.passivas[k] < 5]
        random.shuffle(opcoes)
        self.escolhas = opcoes[:3]
        self.motor.pausado = True

    def _nivel_arma(self, nome):
        return int(self.srv.sis.agentes[nome].corpo.crenca_num("nivel", 0)) if self.srv.sis.agentes[nome].corpo else 0

    def escolher(self, opcao):
        tipo, nome, novo = opcao
        if tipo == "arma":
            ag = self.srv.sis.agentes[nome]
            ag.remover("nivel", (novo - 1,))
            ag.adicionar("nivel", (novo,))         # evento +nivel(N): a DSL aplica a melhoria
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

    # --- HUD -----------------------------------------------------------------------
    def desenhar_ui(self, ui):
        j = self.jogador
        W = ui.largura
        ui.barra((0, 0, W, 14), j.xp / j.xp_proximo, cor=CORES["azul"], fundo=(20, 20, 30, 230))
        ui.texto(W - 10, 18, f"Nível {j.nivel}", 20, ancora="topright", negrito=True)
        m, s = divmod(int(self.tempo), 60)
        ui.texto(W / 2, 22, f"{m:02d}:{s:02d}", 26, ancora="midtop", negrito=True)
        ui.texto(10, 20, f"Abates: {self.abates}", 18)
        ui.texto(10, 42, f"Inimigos: {len(self.cena.com_tag('inimigo'))}  ·  FPS {self.motor.fps_medio:.0f}", 14,
                 cor=(200, 200, 200))
        armas = "  ".join(f"{DESCRICAO_ARMAS[a][0]} {self._nivel_arma(a)}" for a in DESCRICAO_ARMAS
                          if self._nivel_arma(a) > 0)
        ui.texto(10, 60, armas, 14, cor=(220, 220, 160))
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
                       [f"Tempo {m:02d}:{s:02d}", f"Abates: {self.abates}", f"Nível: {j.nivel}"], cor=CORES["verde"])

    def _ui_escolhas(self, ui):
        cx, cy = ui.largura // 2, ui.altura // 2
        ui.retangulo((0, 0, ui.largura, ui.altura), (0, 0, 0, 120), raio=0, bloquear=True)
        ui.texto(cx, cy - 170, "Subiu de nível! Escolha uma melhoria", 28, ancora="center", negrito=True)
        for i, op in enumerate(self.escolhas):
            tipo, nome, novo = op
            r = (cx - 390 + i * 265, cy - 120, 250, 230)
            if tipo == "arma":
                titulo, icone, descs = DESCRICAO_ARMAS[nome]
                linha1 = f"{titulo} — nível {novo}" if novo > 1 else f"{titulo} (nova!)"
                linha2 = descs[novo]
            else:
                titulo, linha2, icone = MELHORIAS_PASSIVAS[nome]
                linha1 = f"{titulo} {novo}"
            if ui.botao(r, ""):
                self.escolher(op)
                return
            ui.desenhar_imagem(icone, r[0] + r[2] / 2, r[1] + 70, tamanho=72)
            ui.texto(r[0] + r[2] / 2, r[1] + 135, linha1, 18, ancora="center", negrito=True)
            ui.texto(r[0] + r[2] / 2, r[1] + 165, linha2, 15, ancora="center", cor=(210, 210, 220))
            ui.texto(r[0] + r[2] / 2, r[1] + 205, f"tecla {i + 1}", 12, ancora="center", cor=(150, 150, 160))
            if self.motor.entrada.tecla_baixou(str(i + 1)):
                self.escolher(op)
                return


@acao_dsl("ferir_jogador", "num", descricao="tira vida do jogador")
def ferir_jogador(corpo, agente, dano):
    corpo.cena.servicos["gerente"].jogador.ferir(float(dano))


@acao_dsl("vencer", descricao="termina a partida com vitória")
def vencer(corpo, agente):
    corpo.cena.servicos["gerente"].vencer()
