"""Demo interativa da engine 2D (parte de Computação Gráfica).

Controles
  WASD / setas ..... mover câmera          roda do mouse ... zoom
  clique esquerdo .. selecionar e arrastar um sprite
  Q / E ............ rotacionar selecionado  Z / X ......... escala - / +
  PgUp / PgDn ...... camada do selecionado + / -
  + / - ............ adicionar / remover 200 sprites animados
  M ................ alternar modo de renderização (individual / lote)
  ESPAÇO ........... pausar animação          ESC ........... sair
"""
import math
import random
import sys
from pathlib import Path

import pygame

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

import gerar_assets  # noqa: E402
from engine2d import Motor, TextoHUD  # noqa: E402


def main(max_quadros=None, captura=None):
    if not (RAIZ / "assets" / "chao.png").exists():
        gerar_assets.gerar()
    motor = Motor(1280, 720, "Engine2D — demo", pasta_assets=RAIZ / "assets")
    cena = motor.cena

    # Camada 0: chão (fundo); 1-3: objetos; 5: nuvens semitransparentes (primeiro plano)
    for i in range(-2, 7):
        for j in range(-2, 5):
            motor.criar_sprite("chao.png", x=i * 256, y=j * 256, camada=0, nome="chao")
    texturas = ["bola.png", "estrela.png", "caixa.png", "guarda.png", "fujao.png"]
    animados = []

    def adicionar(qtd):
        for _ in range(qtd):
            s = motor.criar_sprite(random.choice(texturas), x=random.uniform(0, 1280),
                                   y=random.uniform(0, 720), camada=random.randint(1, 3),
                                   rotacao=random.uniform(0, 360), sx=random.uniform(0.4, 1.0))
            s.transformacao.sy = s.transformacao.sx
            s.dados["vel"] = (random.uniform(-60, 60), random.uniform(-60, 60), random.uniform(-90, 90))
            animados.append(s)

    adicionar(200)
    # Três sprites fixos sobrepostos para mostrar a ordem das camadas
    a = motor.criar_sprite("caixa.png", x=640, y=360, camada=4, sx=2, sy=2, nome="caixa_L4")
    motor.criar_sprite("jogador.png", x=680, y=380, camada=6, sx=2, sy=2, nome="jogador_L6")
    motor.criar_sprite("estrela.png", x=610, y=400, camada=2, sx=2, sy=2, nome="estrela_L2")
    for k in range(6):
        motor.criar_sprite("nuvem.png", x=k * 230, y=600 + 40 * math.sin(k), camada=5, nome="nuvem")

    hud = TextoHUD(motor)
    estado = {"sel": a, "arrastando": False, "pausado": False}

    def ao_evento(m, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            wx, wy = m.camera.tela_para_mundo(*ev.pos)
            s = cena.sprite_em(wx, wy)
            if s is not None and s.nome != "chao":
                estado["sel"] = s
                estado["arrastando"] = True
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            estado["arrastando"] = False
        elif ev.type == pygame.MOUSEMOTION and estado["arrastando"]:
            estado["sel"].x, estado["sel"].y = m.camera.tela_para_mundo(*ev.pos)
        elif ev.type == pygame.MOUSEWHEEL:
            m.camera.zoom = max(0.1, min(8.0, m.camera.zoom * (1.1 ** ev.y)))
        elif ev.type == pygame.KEYDOWN:
            sel = estado["sel"]
            if ev.key == pygame.K_m:
                r = m.renderizador
                r.modo = "individual" if r.modo == "lote" else "lote"
            elif ev.key == pygame.K_SPACE:
                estado["pausado"] = not estado["pausado"]
            elif ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                adicionar(200)
            elif ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                for _ in range(min(200, len(animados))):
                    cena.remover(animados.pop())
            elif ev.key == pygame.K_PAGEUP and sel:
                sel.camada += 1
            elif ev.key == pygame.K_PAGEDOWN and sel:
                sel.camada -= 1

    def atualizar(m, dt):
        teclas = pygame.key.get_pressed()
        v = 400 * dt / m.camera.zoom
        m.camera.x += v * ((teclas[pygame.K_d] or teclas[pygame.K_RIGHT]) - (teclas[pygame.K_a] or teclas[pygame.K_LEFT]))
        m.camera.y += v * ((teclas[pygame.K_w] or teclas[pygame.K_UP]) - (teclas[pygame.K_s] or teclas[pygame.K_DOWN]))
        sel = estado["sel"]
        if sel:
            if teclas[pygame.K_q]:
                sel.transformacao.rotacionar(120 * dt)
            if teclas[pygame.K_e]:
                sel.transformacao.rotacionar(-120 * dt)
            if teclas[pygame.K_z]:
                sel.transformacao.escalar(1 - 1.5 * dt)
            if teclas[pygame.K_x]:
                sel.transformacao.escalar(1 + 1.5 * dt)
        if not estado["pausado"]:
            for s in animados:
                vx, vy, vr = s.dados["vel"]
                t = s.transformacao
                t.transladar(vx * dt, vy * dt)
                t.rotacionar(vr * dt)
                if not 0 <= t.x <= 1280:
                    s.dados["vel"] = (-vx, vy, vr)
                if not 0 <= t.y <= 720:
                    s.dados["vel"] = (vx, -vy, vr)
        if m.quadro % 15 == 0:
            st = m.renderizador.stats
            hud.definir(
                f"FPS {m.fps_medio:6.1f}  |  {m.ms_quadro_medio:5.2f} ms/quadro\n"
                f"modo [M]: {m.renderizador.modo}   sprites: {len(cena)}   draw calls: {st.chamadas_desenho}\n"
                f"selecionado: {sel.nome if sel else '-'}  camada={sel.camada if sel else '-'}\n"
                f"  {sel.transformacao if sel else ''}\n"
                f"GPU: {m.info_gl['renderer'][:48]}"
            )

    motor.executar(atualizar, ao_evento, max_quadros=max_quadros)
    if captura:
        motor.capturar_tela(captura)
    motor.encerrar()


if __name__ == "__main__":
    main()
