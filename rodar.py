"""Roda um projeto sem o editor (o "Player" / build do jogo).

    python rodar.py ProjetoExemplo
    python rodar.py ProjetoExemplo --cena Assets/Cenas/Fase2.cena
    python rodar.py ProjetoExemplo --janela      # numa janela em vez de tela cheia

O jogo abre em tela cheia (ampliado mantendo a proporção). O editor usa este mesmo arquivo
quando você aperta Play.
"""
import argparse
import os
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))


def main(argv=None, max_quadros=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("projeto")
    ap.add_argument("--cena", default=None)
    ap.add_argument("--janela", action="store_true", help="abre numa janela em vez de tela cheia")
    args = ap.parse_args(argv)

    import agentdsl.componente  # noqa: F401  (registra ServicoAgentes/ComportamentoAgente)
    from engine2d import Cena, Motor
    from engine2d.projeto import Projeto

    proj = Projeto(args.projeto)
    os.chdir(proj.raiz)          # caminhos das cenas são relativos à raiz do projeto
    proj.carregar_scripts()
    for erro in proj.erros_scripts:
        print("ERRO no script:", erro, flush=True)
    for info in proj.scripts.values():
        if info.get("detalhe"):
            print(info["detalhe"], file=sys.stderr, flush=True)

    caminho_cena = args.cena or proj.cena_inicial
    oculto = os.environ.get("ENGINE2D_OCULTO") == "1"        # testes: roda sem mostrar a janela
    motor = Motor(proj.largura, proj.altura, proj.nome, pasta_assets=proj.raiz, editor=False, visivel=not oculto,
                  tela_cheia=not args.janela and not oculto)
    motor.configurar_projeto(proj.configuracoes())
    cena = Cena(Path(caminho_cena).stem)
    try:
        try:
            cena.carregar(caminho_cena)
        except Exception:
            traceback.print_exc()
            return 1
        cena.servicos["fabrica"] = lambda: _recarregar(caminho_cena)
        print(f"Rodando '{proj.nome}' — cena {caminho_cena}", flush=True)
        motor.executar(cena, max_quadros=max_quadros)
        return 0
    finally:
        motor.encerrar()
        proj.descarregar()       # esquece scripts e ações da DSL deste projeto


def _recarregar(caminho):
    from engine2d import Cena
    c = Cena(Path(caminho).stem)
    c.carregar(caminho)
    c.servicos["fabrica"] = lambda: _recarregar(caminho)
    return c


if __name__ == "__main__":
    sys.exit(main())
