"""Cenário experimental: jogo 2D cujos personagens são agentes da AgentDSL.

O jogador (azul) é controlado pelo teclado. Todos os outros sprites são
agentes cujo comportamento está SÓ no arquivo .agt — o Python apenas gera
percepções e executa ações.

Controles
  WASD / setas ... mover          ESPAÇO ... atacar guardas próximos
  TAB ............ inspecionar o próximo agente (crenças e eventos na HUD)
  R .............. recarregar o .agt e reiniciar     ESC ... sair

Uso:  python jogo.py [exemplos/jogo.agt]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

from agentdsl.semantica import ATOMO, NUM, Assinatura  # noqa: E402

# --- contrato entre o jogo e a DSL (usado também pela análise semântica) ------
PERCEPCOES = {                         # (nome, aridade) → tipos
    ("jogador_perto", 0): (),          # jogador dentro do raio de visão do agente
    ("tocando_jogador", 0): (),        # encostou no jogador
    ("borda", 0): (),                  # bateu na borda do mapa (pulso)
    ("recebeu_dano", 0): (),           # foi atingido pelo ataque do jogador (pulso)
}
# Crenças que o jogo LÊ mas não controla (parâmetros escritos no .agt, ex.: raio_visao(210)).
ACOES_JOGO = {
    "atacar": Assinatura((ATOMO, NUM), "tira N de vida do alvo (só 'jogador')"),
    "pontuar": Assinatura((NUM,), "soma pontos ao placar"),
}
ALVOS = ("jogador",)

LARGURA, ALTURA = 1280, 720
RAIO_PADRAO = 200
RAIO_TOQUE = 42
RAIO_ATAQUE = 95


class Jogo:
    def __init__(self, motor, arquivo: Path):
        self.motor = motor
        self.arquivo = arquivo
        self.selecionado = 0
        self.mensagens: list[str] = []
        self.carregar()

    def carregar(self):
        from agentdsl import ErroCompilacao, SistemaAgentes
        from agentdsl.ponte_engine import AmbienteEngine
        from agentdsl.semantica import ACOES_ENGINE
        from engine2d import Cena

        m = self.motor
        m.cena = Cena()
        for i in range(0, LARGURA + 256, 256):
            for j in range(0, ALTURA + 256, 256):
                m.criar_sprite("chao.png", x=i, y=j, camada=0, nome="chao")
        self.jogador = m.criar_sprite("jogador.png", x=LARGURA / 2, y=ALTURA / 2, camada=3, nome="jogador")
        self.marcador = m.criar_sprite("estrela.png", camada=9, sx=0.35, sy=0.35, nome="marcador")
        self.amb = AmbienteEngine(m, set(n for n, _ in PERCEPCOES), margem=28)
        self.amb.registrar_objeto("jogador", self.jogador)
        self.amb.registrar_acao("atacar", self._acao_atacar)
        self.amb.registrar_acao("pontuar", self._acao_pontuar)
        self.vida, self.pontos, self.fim = 5, 0, None
        self.recarga_ataque = 0.0
        self.recarga_dano: dict[str, float] = {}

        fonte = self.arquivo.read_text(encoding="utf-8-sig")
        try:
            self.sis = SistemaAgentes(fonte, ambiente=self.amb, acoes={**ACOES_ENGINE, **ACOES_JOGO},
                                      percepcoes=PERCEPCOES, alvos=ALVOS, arquivo=str(self.arquivo))
        except ErroCompilacao as e:
            print("\n".join(d.formatar(fonte, str(self.arquivo)) for d in e.diagnosticos))
            raise SystemExit(1)
        for aviso in self.sis.formatar_avisos():
            print(aviso)
        self.sis.ao_registrar = lambda linha, tipo: self._log(linha)

        for ag in self.sis.agentes.values():
            d = ag.decl.sprite
            if d is None:
                continue  # agente sem corpo (só lógica)
            sp = m.criar_sprite(d.imagem, x=d.x, y=d.y, camada=d.camada, nome=ag.nome)
            self.amb.vincular(ag, sp)
        self.com_sprite = [a for a in self.sis.agentes.values() if a.sprite is not None]
        self.sis.iniciar()
        self.havia_fugitivos = any(a.acredita("fugitivo") for a in self.com_sprite)
        self.hud = __import__("engine2d").TextoHUD(m, tamanho=16)
        self._log(f"programa carregado: {len(self.sis.agentes)} agentes")

    def _log(self, linha):
        self.mensagens.append(linha)
        del self.mensagens[:-7]

    # --- ações específicas do jogo -------------------------------------------
    def _acao_atacar(self, agente, alvo, dano):
        if str(alvo) != "jogador" or self.fim:
            return
        if self.recarga_dano.get(agente.nome, 0) > 0:
            return
        self.recarga_dano[agente.nome] = 1.0
        self.vida -= int(dano)
        self.jogador.cor = (1, 0.4, 0.4, 1)
        self._log(f"jogador atingido por {agente.nome}! vida={self.vida}")

    def _acao_pontuar(self, agente, n):
        self.pontos += int(n)

    # --- percepções: o que cada agente "vê" neste quadro -------------------------
    def perceber(self, ag) -> set:
        sp = ag.sprite
        if not sp.visivel or self.fim:
            return set()
        raio = next((args[0] for args in (c[1] for c in ag.crencas_com("raio_visao", 1))), RAIO_PADRAO)
        d = self.amb.distancia(sp, self.jogador)
        p = set()
        if d < raio:
            p.add(("jogador_perto", ()))
        if d < RAIO_TOQUE * max(sp.transformacao.sx, 1):
            p.add(("tocando_jogador", ()))
        return p

    # --- loop -----------------------------------------------------------------
    def atualizar(self, m, dt):
        import pygame
        t = pygame.key.get_pressed()
        if not self.fim:
            vx = (t[pygame.K_d] or t[pygame.K_RIGHT]) - (t[pygame.K_a] or t[pygame.K_LEFT])
            vy = (t[pygame.K_w] or t[pygame.K_UP]) - (t[pygame.K_s] or t[pygame.K_DOWN])
            n = math.hypot(vx, vy) or 1
            j = self.jogador.transformacao
            j.transladar(230 * dt * vx / n, 230 * dt * vy / n)
            j.x = min(max(j.x, 28), LARGURA - 28)
            j.y = min(max(j.y, 28), ALTURA - 28)
            if vx or vy:
                j.rotacao = math.degrees(math.atan2(vy, vx))
        self.recarga_ataque = max(0, self.recarga_ataque - dt)
        for k in self.recarga_dano:
            self.recarga_dano[k] = max(0, self.recarga_dano[k] - dt)
        if self.jogador.cor != (1, 1, 1, 1) and self.recarga_ataque == 0:
            self.jogador.cor = tuple(min(1, c + 2 * dt) for c in self.jogador.cor)

        # 1) engine move os sprites conforme as ações já recebidas
        self.amb.atualizar(dt)
        # 2) percepções → crenças → eventos
        for ag in self.com_sprite:
            self.amb.atualizar_percepcoes(ag, self.perceber(ag))
        # 3) ciclo de raciocínio dos agentes (eventos → planos → ações)
        self.sis.passo()

        if not self.fim:
            if self.vida <= 0:
                self.fim = "FIM DE JOGO — R para reiniciar"
            # Vitória definida pelas crenças: nenhum agente ainda acredita em "fugitivo".
            elif self.havia_fugitivos and not any(a.acredita("fugitivo") for a in self.com_sprite):
                self.fim = f"VITÓRIA! {self.pontos} pontos — R para reiniciar"
        self._hud(m)

    def atacar(self):
        if self.recarga_ataque > 0 or self.fim:
            return
        self.recarga_ataque = 0.35
        self.jogador.transformacao.escalar(1.25)
        for ag in self.com_sprite:
            if ag.sprite.visivel and self.amb.distancia(ag.sprite, self.jogador) < RAIO_ATAQUE:
                self.amb.pulsar(ag, "recebeu_dano")

    def ao_evento(self, m, ev):
        import pygame
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_SPACE:
                self.atacar()
            elif ev.key == pygame.K_TAB and self.com_sprite:
                self.selecionado = (self.selecionado + 1) % len(self.com_sprite)
            elif ev.key == pygame.K_r:
                self.carregar()
        elif ev.type == pygame.KEYUP and ev.key == pygame.K_SPACE:
            self.jogador.transformacao.sx = self.jogador.transformacao.sy = 1.0

    def _hud(self, m):
        ag = self.com_sprite[self.selecionado % len(self.com_sprite)] if self.com_sprite else None
        if ag:
            self.marcador.x, self.marcador.y = ag.sprite.x, ag.sprite.y + 40
            self.marcador.transformacao.rotacionar(3)
        if m.quadro % 6:
            return
        linhas = [f"vida {'♥' * max(self.vida, 0)}{' ' * (5 - max(self.vida, 0))}  pontos {self.pontos:4d}"
                  f"   FPS {m.fps_medio:5.1f}   eventos {self.sis.stats['eventos']}  planos {self.sis.stats['planos']}"]
        if self.fim:
            linhas.append(f">>> {self.fim}")
        if ag:
            linhas.append(f"[TAB] agente: {ag.nome}")
            linhas.append("  crenças: " + ", ".join(ag.descrever_crencas()))
        linhas.append("log:")
        linhas += [f"  {l[:90]}" for l in self.mensagens]
        self.hud.definir("\n".join(linhas))


def main(arquivo=None, max_quadros=None, captura=None):
    import gerar_assets
    from engine2d import Motor

    arquivo = Path(arquivo or RAIZ / "exemplos" / "jogo.agt")
    if not (RAIZ / "assets" / "fujao.png").exists():
        gerar_assets.gerar()
    motor = Motor(LARGURA, ALTURA, f"AgentDSL — {arquivo.name}", pasta_assets=RAIZ / "assets")
    jogo = Jogo(motor, arquivo)
    motor.executar(jogo.atualizar, jogo.ao_evento, max_quadros=max_quadros)
    if captura:
        motor.capturar_tela(captura)
    motor.encerrar()
    return 0


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
