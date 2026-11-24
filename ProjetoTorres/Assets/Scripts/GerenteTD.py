"""Loja, construção/melhoria/venda de torres, ondas (via DSL), dinheiro, vidas e painel."""
import random

from Comum import criar_texto_flutuante, painel_fim
from engine2d import Componente, SpriteRenderer
from engine2d.projeto import acao_dsl, percepcao_dsl
from engine2d.ui import CORES
from Mapa import COLS, LARGURA_MAPA, LINHAS, PONTOS, TILE, Y0, celulas_do_caminho, centro_celula, ponto_no_caminho

percepcao_dsl("onda", "num")         # o agente "ondas" recebe +onda(N) ao iniciar cada onda

ONDA_FINAL = 15
T = "Assets/Sprites/Torres/"
TORRES = {
    # nome: (título, preço, base, torreta, [custo nível 2, custo nível 3], descrição, alcance inicial)
    "metralhadora": ("Metralhadora", 120, T + "base_metralhadora.png", T + "torreta_metralhadora.png", [100, 260],
                     "rápida, dano baixo", 150),
    "canhao": ("Canhão", 280, T + "base_canhao.png", T + "torreta_canhao.png", [220, 450], "dano em área", 170),
    "missil": ("Lança-mísseis", 450, T + "base_missil.png", T + "torreta_missil.png", [350, 700],
               "alcance longo, mira no mais forte", 260),
    "gelo": ("Torre de gelo", 200, T + "base_gelo.png", T + "torreta_gelo.png", [150, 300],
             "deixa os inimigos lentos", 120),
}


class GerenteTD(Componente):
    CAMPOS = {"dinheiro_inicial": "int", "vidas_iniciais": "int"}
    dinheiro_inicial = 700
    vidas_iniciais = 100

    def iniciar(self):
        self.cena.servicos["gerente"] = self
        self.srv = self.cena.servicos["agentes"]
        self.srv.ponto_de_invocacao = lambda modelo: PONTOS[0]
        self.srv.ao_invocar = self.ao_invocar
        self.dinheiro = self.dinheiro_inicial
        self.vidas = self.vidas_iniciais
        self.onda = 0
        self.onda_ativa = False
        self.tempo_onda = 0.0
        self.fim = None
        self.modo_infinito = False
        self.colocando = None
        self.selecionada = None
        self.ocupadas = {}
        self.caminho = celulas_do_caminho()
        self.fantasma = self.cena.criar("fantasma", -500, -500, componentes=[
            SpriteRenderer(imagem=TORRES["metralhadora"][2], camada=8, cor=(1, 1, 1, 0.6))])
        self.fantasma_torreta = self.cena.criar("fantasma torreta", 0, 0, pai=self.fantasma, componentes=[
            SpriteRenderer(imagem=TORRES["metralhadora"][3], camada=9, cor=(1, 1, 1, 0.6))])

    # --- inimigos ------------------------------------------------------------------
    def ao_invocar(self, go, origem):
        """Inimigos criados por invocar_aqui continuam do mesmo ponto do caminho de quem os criou."""
        seg = go.obter("SeguirCaminho")
        if seg is None:
            return
        if origem is not None and origem.gameobject is not None:
            o = origem.obter("SeguirCaminho")
            if o is not None:
                seg.progresso = max(0.0, o.progresso - random.uniform(0, 30))
        x, y, ang = ponto_no_caminho(seg.progresso)
        go.transform.x, go.transform.y, go.transform.rotacao = x, y, ang

    def inimigos(self):
        return self.cena.com_tag("inimigo")

    # --- ondas ------------------------------------------------------------------------
    def iniciar_onda(self):
        if self.onda_ativa or self.fim:
            return
        self.onda += 1
        self.onda_ativa = True
        self.tempo_onda = 0.0
        self.srv.sis.agentes["ondas"].corpo.perceber({("onda", (self.onda,))})   # evento +onda(N)

    def atualizar(self, dt):
        if self.fim:
            return
        if self.onda_ativa:
            self.tempo_onda += dt
        if self.onda_ativa and self.tempo_onda > 0.5 and not self.srv.series and not self.inimigos():
            self.onda_ativa = False
            bonus = 60 + 12 * self.onda
            self.dinheiro += bonus
            criar_texto_flutuante(self.cena, LARGURA_MAPA / 2, 380, f"Onda {self.onda} concluída! +${bonus}")
            if self.onda >= ONDA_FINAL and not self.modo_infinito:
                self.fim = "vitoria"
        if self.vidas <= 0:
            self.vidas = 0
            self.fim = "derrota"
        self._entrada_mapa()

    # --- mouse no mapa -------------------------------------------------------------------
    def _celula_mouse(self):
        mx, my = self.motor.entrada.mouse_mundo
        c, r = int(mx // TILE), int((my - Y0) // TILE)
        if 0 <= c < COLS and 0 <= r < LINHAS and mx < LARGURA_MAPA:
            return c, r
        return None

    def _pode_colocar(self, cel):
        return cel is not None and cel not in self.caminho and cel not in self.ocupadas

    def _entrada_mapa(self):
        ent = self.motor.entrada
        for i, nome in enumerate(TORRES):
            if ent.tecla_baixou(str(i + 1)):
                self.selecionar_compra(nome)
        if ent.tecla_baixou("space"):
            self.iniciar_onda()
        cel = self._celula_mouse()
        if self.colocando:
            if cel is not None:
                x, y = centro_celula(*cel)
                self.fantasma.transform.x, self.fantasma.transform.y = x, y
                ok = self._pode_colocar(cel) and self.dinheiro >= TORRES[self.colocando][1]
                for r in self.fantasma.obter_nos_filhos("SpriteRenderer"):
                    r.cor = (1, 1, 1, 0.65) if ok else (1, 0.4, 0.4, 0.65)
                if ent.clicou(1) and ok and not self.motor.ui.mouse_sobre_ui():
                    self.construir(self.colocando, cel)
                    if not (ent.tecla("left shift") or ent.tecla("right shift")):
                        self.colocando = None
            if ent.clicou(3) or ent.tecla_baixou("escape"):
                self.colocando = None
                ent._baixou.discard("escape")       # não abre o menu de pausa
        elif ent.clicou(1) and cel is not None and not self.motor.ui.mouse_sobre_ui():
            self.selecionada = self.ocupadas.get(cel)
        if not self.colocando:
            self.fantasma.transform.x = -500

    def selecionar_compra(self, nome):
        self.colocando = nome
        self.selecionada = None
        self.fantasma.obter("SpriteRenderer").trocar_imagem(TORRES[nome][2])
        self.fantasma_torreta.obter("SpriteRenderer").trocar_imagem(TORRES[nome][3])

    # --- torres -----------------------------------------------------------------------------
    def construir(self, nome, cel):
        self.dinheiro -= TORRES[nome][1]
        x, y = centro_celula(*cel)
        go = self.srv.criar_corpo(nome, x, y)      # usa Assets/Prefabs/<nome>.prefab + ComportamentoAgente
        go.obter("Torre").investido = TORRES[nome][1]
        go.nome = nome
        self.ocupadas[cel] = go
        self.selecionada = go

    def melhorar(self, go):
        torre = go.obter("Torre")
        n = torre.nivel()
        if n >= 3:
            return
        custo = TORRES[torre.tipo][4][n - 1]
        if self.dinheiro < custo:
            return
        self.dinheiro -= custo
        torre.investido += custo
        ag = go.obter("ComportamentoAgente").ag
        ag.remover("nivel", (n,))
        ag.adicionar("nivel", (n + 1,))      # evento +nivel(N+1): a DSL aplica a melhoria
        criar_texto_flutuante(self.cena, *go.transform.posicao_mundo, f"nível {n + 1}!")

    def vender(self, go):
        torre = go.obter("Torre")
        self.dinheiro += int(torre.investido * 0.7)
        for cel, g in list(self.ocupadas.items()):
            if g is go:
                del self.ocupadas[cel]
        go.destruir()
        self.selecionada = None

    # --- painel -----------------------------------------------------------------------------
    def desenhar_ui(self, ui):
        alvo = None
        if self.colocando and self.fantasma.transform.x > 0:
            alvo = (self.fantasma.transform.posicao_mundo, TORRES[self.colocando][6])
        elif self.selecionada is not None and not self.selecionada.destruido:
            alvo = (self.selecionada.transform.posicao_mundo, self.selecionada.obter("Torre").alcance())
        if alvo:
            (x, y), r = alvo
            sx, sy = ui.mundo_para_tela(x, y)
            ui.circulo((sx, sy), r, (255, 255, 255, 40))
            ui.circulo((sx, sy), r, (255, 255, 255, 140), 2)

        x0 = LARGURA_MAPA
        ui.retangulo((x0, 0, ui.largura - x0, ui.altura), (24, 28, 38, 245), raio=0, bloquear=True)
        ui.texto(x0 + 128, 26, "Defesa da Base", 24, ancora="center", negrito=True)
        ui.texto(x0 + 16, 56, f"Vidas: {self.vidas}", 19, cor=(255, 120, 120), negrito=True)
        ui.texto(x0 + 140, 56, f"$ {self.dinheiro}", 19, cor=(255, 220, 90), negrito=True)
        ui.texto(x0 + 16, 84, f"Onda {self.onda} / {ONDA_FINAL}" + ("  (em andamento)" if self.onda_ativa else ""), 16)
        if ui.botao((x0 + 12, 110, 232, 38), "Onda em andamento..." if self.onda_ativa else
                    f"Iniciar onda {self.onda + 1}  [espaço]", ativo=not self.onda_ativa and not self.fim):
            self.iniciar_onda()
        vel = self.motor.escala_tempo
        if ui.botao((x0 + 12, 154, 113, 30), f"Velocidade x{vel:g}", tamanho_texto=14):
            self.motor.escala_tempo = {1.0: 2.0, 2.0: 3.0}.get(vel, 1.0)
        ui.texto(x0 + 133, 160, f"inimigos: {len(self.inimigos())}", 14, cor=(190, 190, 200))
        ui.texto(x0 + 16, 196, "Torres", 17, negrito=True)
        for i, (nome, (titulo, preco, base, torreta, _, desc, _)) in enumerate(TORRES.items()):
            r = (x0 + 12 + (i % 2) * 118, 220 + (i // 2) * 112, 112, 106)
            pode = self.dinheiro >= preco
            if ui.botao(r, "", ativo=pode, selecionado=self.colocando == nome, dica=f"{titulo} [{i + 1}]\n{desc}"):
                self.selecionar_compra(nome)
            ui.desenhar_imagem(base, r[0] + 56, r[1] + 42, tamanho=50, alfa=255 if pode else 120)
            ui.desenhar_imagem(torreta, r[0] + 56, r[1] + 42, tamanho=50, alfa=255 if pode else 120)
            ui.texto(r[0] + 56, r[1] + 78, titulo, 13, ancora="center")
            ui.texto(r[0] + 56, r[1] + 95, f"$ {preco}", 13, ancora="center", cor=(255, 220, 90))

        sel = self.selecionada
        if sel is not None and not sel.destruido:
            torre = sel.obter("Torre")
            ag = sel.obter("ComportamentoAgente")
            y = 460
            ui.retangulo((x0 + 8, y, 240, 200), (34, 40, 54), borda=CORES["borda"])
            ui.texto(x0 + 18, y + 8, f"{TORRES[torre.tipo][0]} — nível {torre.nivel()}", 16, negrito=True)
            atributos = [f"{n}: {ag.crenca_num(n):g}" for n in ("alcance", "dano", "cadencia", "area", "lentidao")
                         if ag._iniciado and ag.ag.crencas_com(n, 1)]
            for k, a in enumerate(atributos):
                ui.texto(x0 + 22, y + 34 + 18 * k, a, 14, cor=(200, 210, 220))
            n = torre.nivel()
            if n < 3:
                custo = TORRES[torre.tipo][4][n - 1]
                if ui.botao((x0 + 16, y + 130, 224, 30), f"Melhorar para nível {n + 1}  ($ {custo})",
                            ativo=self.dinheiro >= custo, tamanho_texto=14):
                    self.melhorar(sel)
            else:
                ui.texto(x0 + 128, y + 145, "nível máximo", 14, ancora="center", cor=CORES["destaque"])
            if ui.botao((x0 + 16, y + 164, 224, 28), f"Vender ($ {int(torre.investido * 0.7)})", tamanho_texto=14):
                self.vender(sel)
        else:
            ui.texto(x0 + 16, 470, "Clique numa torre do mapa", 14, cor=(160, 160, 170))
            ui.texto(x0 + 16, 488, "para melhorar ou vender.", 14, cor=(160, 160, 170))
            ui.texto(x0 + 16, 516, "Shift+clique: várias torres.", 14, cor=(160, 160, 170))

        if self.fim == "derrota":
            painel_fim(ui, self.motor, self.cena, "A base caiu!", [f"Você chegou à onda {self.onda}"],
                       cor=CORES["vermelho"])
        elif self.fim == "vitoria":
            painel_fim(ui, self.motor, self.cena, "Vitória!",
                       [f"{ONDA_FINAL} ondas defendidas", f"Vidas restantes: {self.vidas}"], cor=CORES["verde"],
                       extra=("Continuar (modo infinito)", self._continuar))

    def _continuar(self):
        self.fim = None
        self.modo_infinito = True


@acao_dsl("pagar", "num", descricao="dá dinheiro ao jogador")
def pagar(corpo, agente, n):
    corpo.cena.servicos["gerente"].dinheiro += int(n)
    criar_texto_flutuante(corpo.cena, *corpo.transform.posicao_mundo, f"+{int(n)}", cor=(255, 220, 90))


@acao_dsl("ferir_base", "num", descricao="tira vidas da base")
def ferir_base(corpo, agente, n):
    corpo.cena.servicos["gerente"].vidas -= int(n)
