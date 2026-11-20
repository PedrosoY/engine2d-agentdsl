"""Avaliação experimental da engine (Etapa 4 de Computação Gráfica).

Mede, para quantidades crescentes de sprites e diferentes resoluções:
  - tempo por quadro (ms) com glFinish (inclui a GPU) e FPS equivalente;
  - tempo de atualização (CPU) e de renderização (CPU: preparo + chamadas GL);
  - número de draw calls;
  - memória RAM do processo e estimativa de VRAM (texturas + buffers).

Configurações comparadas:
  individual        — 1 draw call por sprite (pipeline do artigo)
  lote              — instancing por grupos consecutivos de mesma textura
  lote_agrupado     — lote + ordenação (camada, textura) dentro da camada

Uso:
  python benchmark_engine.py            # completo (alguns minutos)
  python benchmark_engine.py --rapido   # poucos cenários, para conferir
Saída: resultados/benchmark.csv, resultados/resumo.csv e gráficos PNG.
"""
import argparse
import csv
import ctypes
import math
import platform
import random
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

import gerar_assets  # noqa: E402

PASTA_RES = RAIZ / "resultados"
CONFIGS = {
    "individual": dict(modo="individual", agrupar=False),
    "lote": dict(modo="lote", agrupar=False),
    "lote_agrupado": dict(modo="lote", agrupar=True),
    "lote_atlas": dict(modo="lote", agrupar=False, atlas=True),
}
TEXTURAS = ["bola.png", "estrela.png", "caixa.png", "guarda.png", "fujao.png"]


def memoria_rss_mb() -> float:
    """Memória residente do processo (Windows via psapi; fallback para resource)."""
    if platform.system() == "Windows":
        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
        psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.WorkingSetSize / 2**20
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def p95(v):
    v = sorted(v)
    return v[min(len(v) - 1, int(math.ceil(0.95 * len(v))) - 1)]


def rodar_cenario(motor, n, cfg, quadros, aquecimento, limite_s, semente=42):
    from OpenGL import GL
    from engine2d import Cena, Sprite

    random.seed(semente)
    motor.cena = Cena(agrupar_texturas=cfg["agrupar"])
    motor.renderizador.modo = cfg["modo"]
    w, h = motor.largura, motor.altura
    texs = [motor.carregar_textura(t) for t in TEXTURAS]
    atlas = None
    if cfg.get("atlas"):
        from engine2d.textura import AtlasTexturas
        if not hasattr(motor, "_atlas_bench"):
            motor._atlas_bench = AtlasTexturas([RAIZ / "assets" / t for t in TEXTURAS])
            motor.texturas.registrar("atlas_bench", motor._atlas_bench.textura)
        atlas = motor._atlas_bench
    sprites = []
    for _ in range(n):
        i = random.randrange(len(texs))
        s = Sprite(texs[i], x=random.uniform(0, w), y=random.uniform(0, h),
                   camada=random.randint(0, 3), rotacao=random.uniform(0, 360),
                   sx=0.5, sy=0.5)
        if atlas:
            atlas.configurar(s, TEXTURAS[i])
        s.dados["v"] = (random.uniform(-80, 80), random.uniform(-80, 80), random.uniform(-90, 90))
        motor.cena.adicionar(s)
        sprites.append(s)

    import pygame
    t_quadro, t_upd, t_rend, chamadas = [], [], [], 0
    dt = 1 / 60
    inicio = time.perf_counter()
    for q in range(aquecimento + quadros):
        pygame.event.pump()
        t0 = time.perf_counter()
        for s in sprites:                      # atualizar objetos
            vx, vy, vr = s.dados["v"]
            tr = s.transformacao
            tr.transladar(vx * dt, vy * dt)
            tr.rotacionar(vr * dt)
            if not 0 <= tr.x <= w:
                s.dados["v"] = (-vx, vy, vr)
            if not 0 <= tr.y <= h:
                s.dados["v"] = (vx, -vy, vr)
        t1 = time.perf_counter()
        motor.renderizador.limpar()
        motor.renderizador.desenhar(motor.cena, motor.camera)
        t2 = time.perf_counter()
        GL.glFinish()                          # espera a GPU terminar
        pygame.display.flip()
        t3 = time.perf_counter()
        if q >= aquecimento:
            t_quadro.append((t3 - t0) * 1000)
            t_upd.append((t1 - t0) * 1000)
            t_rend.append((t2 - t1) * 1000)
            chamadas = motor.renderizador.stats.chamadas_desenho
            if time.perf_counter() - inicio > limite_s and len(t_quadro) >= 20:
                break
    media = statistics.fmean(t_quadro)
    dp = statistics.stdev(t_quadro) if len(t_quadro) > 1 else 0.0
    return {
        "sprites": n,
        "config": next(k for k, v in CONFIGS.items() if v is cfg),
        "resolucao": f"{w}x{h}",
        "quadros_medidos": len(t_quadro),
        "ms_quadro_media": round(media, 3),
        "ms_quadro_dp": round(dp, 3),
        "ms_quadro_ic95": round(1.96 * dp / math.sqrt(len(t_quadro)), 3),
        "ms_quadro_p95": round(p95(t_quadro), 3),
        "fps_medio": round(1000 / media, 1),
        "ms_atualizacao": round(statistics.fmean(t_upd), 3),
        "ms_render_cpu": round(statistics.fmean(t_rend), 3),
        "draw_calls": chamadas,
        "ram_mb": round(memoria_rss_mb(), 1),
        "vram_estimada_kb": round((motor.texturas.bytes_vram + motor.renderizador.bytes_vram_buffers) / 1024, 1),
    }


def graficos(linhas):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    res_base = "1280x720"
    base = [l for l in linhas if l["resolucao"] == res_base]
    fig, eixos = plt.subplots(1, 2, figsize=(11, 4))
    for cfg in CONFIGS:
        pts = sorted((l["sprites"], l["ms_quadro_media"], l["ms_quadro_ic95"], l["fps_medio"])
                     for l in base if l["config"] == cfg)
        if not pts:
            continue
        xs = [p[0] for p in pts]
        eixos[0].errorbar(xs, [p[1] for p in pts], yerr=[p[2] for p in pts], marker="o", capsize=3, label=cfg)
        eixos[1].plot(xs, [p[3] for p in pts], marker="o", label=cfg)
    eixos[0].set(xscale="log", yscale="log", xlabel="sprites", ylabel="ms por quadro (média, IC95%)",
                 title=f"Tempo por quadro ({res_base})")
    eixos[1].set(xscale="log", yscale="log", xlabel="sprites", ylabel="FPS", title="Taxa de quadros")
    eixos[1].axhline(60, color="gray", ls="--", lw=0.8)
    for e in eixos:
        e.grid(True, which="both", alpha=0.3)
        e.legend()
    fig.tight_layout()
    fig.savefig(PASTA_RES / "tempo_quadro_fps.png", dpi=150)

    fig, ax = plt.subplots(figsize=(6, 4))
    for cfg in CONFIGS:
        pts = sorted((l["sprites"], l["draw_calls"]) for l in base if l["config"] == cfg)
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", label=cfg)
    ax.set(xscale="log", yscale="log", xlabel="sprites", ylabel="draw calls por quadro", title="Chamadas de desenho")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(PASTA_RES / "draw_calls.png", dpi=150)

    resol = [l for l in linhas if l["sprites"] == linhas[-1]["sprites"] and l.get("_sweep_res")]
    if resol:
        fig, ax = plt.subplots(figsize=(6, 4))
        for cfg in CONFIGS:
            pts = [(l["resolucao"], l["ms_quadro_media"]) for l in resol if l["config"] == cfg]
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", label=cfg)
        ax.set(xlabel="resolução", ylabel="ms por quadro", title=f"Efeito da resolução ({resol[0]['sprites']} sprites)")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(PASTA_RES / "resolucao.png", dpi=150)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    args = ap.parse_args()
    if not (RAIZ / "assets" / "bola.png").exists():
        gerar_assets.gerar()
    PASTA_RES.mkdir(exist_ok=True)

    from engine2d import Motor

    if args.rapido:
        qtds, quadros, limite, resolucoes, n_res = [100, 1000, 5000], 60, 3, [(1280, 720)], None
    else:
        qtds, quadros, limite = [100, 500, 1000, 2000, 5000, 10000, 20000, 50000], 300, 10
        resolucoes, n_res = [(800, 600), (1280, 720), (1920, 1080)], 5000

    linhas = []
    motor = Motor(1280, 720, "benchmark", vsync=False, pasta_assets=RAIZ / "assets")
    print("GPU:", motor.info_gl["renderer"], "| OpenGL", motor.info_gl["versao"])
    for n in qtds:
        for cfg in CONFIGS.values():
            r = rodar_cenario(motor, n, cfg, quadros, 30, limite)
            linhas.append(r)
            print(f"{r['config']:>14} n={n:>6}: {r['ms_quadro_media']:9.2f} ms ({r['fps_medio']:7.1f} FPS) "
                  f"draw calls={r['draw_calls']:>6}  RAM={r['ram_mb']} MB")
    motor.encerrar()

    if n_res:
        for (w, h) in resolucoes:
            motor = Motor(w, h, "benchmark", vsync=False, pasta_assets=RAIZ / "assets")
            for cfg in CONFIGS.values():
                r = rodar_cenario(motor, n_res, cfg, quadros, 30, limite)
                r["_sweep_res"] = True
                linhas.append(r)
                print(f"{r['config']:>14} {w}x{h} n={n_res}: {r['ms_quadro_media']:.2f} ms")
            motor.encerrar()

    campos = [k for k in linhas[0] if not k.startswith("_")]
    with open(PASTA_RES / "benchmark.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, campos + ["experimento"], extrasaction="ignore")
        wr.writeheader()
        for l in linhas:
            wr.writerow({**l, "experimento": "resolucao" if l.get("_sweep_res") else "quantidade"})
    with open(PASTA_RES / "ambiente.txt", "w", encoding="utf-8") as f:
        f.write(f"GPU: {motor.info_gl['renderer']}\nOpenGL: {motor.info_gl['versao']}\n"
                f"CPU: {platform.processor()}\nPython: {platform.python_version()}\nSO: {platform.platform()}\n")
    graficos(linhas)
    print("Resultados em", PASTA_RES)


if __name__ == "__main__":
    main()
