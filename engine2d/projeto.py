"""Projetos: uma pasta com Assets/ e um projeto.json.

    MeuJogo/
      projeto.json          nome, cena inicial, tamanho da janela
      Assets/
        Cenas/              *.cena    (JSON com os GameObjects)
        Scripts/            *.py      (seus componentes: class X(Componente))
        Sprites/            *.png
        Prefabs/            *.prefab  (JSON de um GameObject)
        Agentes/            *.agt     (comportamentos na AgentDSL)

Os scripts são carregados (e recarregados quando você salva o arquivo) e as
classes que herdam de Componente aparecem no "Adicionar Componente" do editor.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path

from .objeto import REGISTRO_COMPONENTES, Componente

PASTAS = ["Cenas", "Scripts", "Sprites", "Prefabs", "Agentes"]
CAMADAS_PADRAO = ["Fundo", "Padrao", "Frente"]          # camadas de desenho: a primeira fica atrás
TAGS_PADRAO = ["jogador", "inimigo", "chao", "item"]

MODELO_SCRIPT = '''from engine2d import Componente


class {nome}(Componente):
    # Campos que aparecem no Inspector.
    # Tipos: "float", "int", "bool", "str", "cor"
    CAMPOS = {{"velocidade": "float"}}
    velocidade = 200.0

    def iniciar(self):
        # Roda uma vez, antes do primeiro quadro.
        pass

    def atualizar(self, dt):
        # Roda todo quadro. dt = segundos desde o último quadro.
        # Exemplo: mover com WASD
        # dx, dy = self.motor.entrada.direcao_wasd()
        # self.transform.x += dx * self.velocidade * dt
        # self.transform.y += dy * self.velocidade * dt
        pass
'''

MODELO_AGT = '''// Comportamento em AgentDSL. Use num objeto com o componente "ComportamentoAgente"
// (campo modelo = nome do modelo abaixo) e um objeto com "ServicoAgentes".
modelo {nome} {{
    nasceu.
    +nasceu <- girar(90).
}}
'''


# --- Ações da DSL definidas nos scripts do projeto ------------------------------
# Num script: @acao_dsl("pular", "num")  def pular(corpo, agente, forca): ...
ACOES_DSL: dict[str, tuple] = {}
PERCEPCOES_DSL: dict[tuple, tuple] = {}
ALVOS_DSL: set[str] = set()          # nomes (átomos) válidos como alvo, ex.: "jogador"


def acao_dsl(nome: str, *tipos: str, descricao: str = ""):
    """Registra uma função Python como ação da AgentDSL (tipos: "num", "atomo", "texto")."""
    def registrar(funcao):
        from agentdsl.semantica import Assinatura
        ACOES_DSL[nome] = (Assinatura(tuple(tipos), descricao), funcao)
        return funcao
    return registrar


def percepcao_dsl(nome: str, *tipos: str):
    """Declara uma crença que os scripts adicionam/removem nos agentes (percepção)."""
    PERCEPCOES_DSL[(nome, len(tipos))] = tuple(tipos)


def alvo_dsl(*nomes: str):
    """Declara nomes que podem ser usados como alvo/átomo nas ações (ex.: alvo_dsl("jogador"))."""
    ALVOS_DSL.update(nomes)


def limpar_registros_dsl():
    ACOES_DSL.clear()
    PERCEPCOES_DSL.clear()
    ALVOS_DSL.clear()


class Projeto:
    def __init__(self, raiz: str | Path):
        self.raiz = Path(raiz).resolve()
        dados = {}
        arq = self.raiz / "projeto.json"
        if arq.exists():
            dados = json.loads(arq.read_text(encoding="utf-8"))
        self.nome = dados.get("nome", self.raiz.name)
        self.cena_inicial = dados.get("cena_inicial", "Assets/Cenas/Principal.cena")
        self.largura = int(dados.get("largura", 1280))
        self.altura = int(dados.get("altura", 720))
        # Configurações do projeto (editáveis no editor em Editar → Configurações do projeto)
        self.camadas_desenho: list[str] = list(dados.get("camadas_desenho", CAMADAS_PADRAO))
        self.tags: list[str] = list(dados.get("tags", TAGS_PADRAO))
        self.gravidade: tuple[float, float] = tuple(dados.get("gravidade", (0.0, 0.0)))
        self.colisoes_ignoradas: list[str] = list(dados.get("colisoes_ignoradas", []))
        self.scripts: dict[str, dict] = {}      # caminho → {modulo, mtime, classes, erro}
        self.erros_scripts: list[str] = []

    # --- criação --------------------------------------------------------------
    @classmethod
    def criar(cls, raiz: str | Path, nome: str | None = None) -> "Projeto":
        raiz = Path(raiz)
        for p in PASTAS:
            (raiz / "Assets" / p).mkdir(parents=True, exist_ok=True)
        if not (raiz / "projeto.json").exists():
            (raiz / "projeto.json").write_text(json.dumps({
                "nome": nome or raiz.name, "cena_inicial": "Assets/Cenas/Principal.cena",
                "largura": 1280, "altura": 720, "camadas_desenho": CAMADAS_PADRAO, "tags": TAGS_PADRAO,
                "gravidade": [0.0, -1800.0], "colisoes_ignoradas": []},
                indent=2, ensure_ascii=False), encoding="utf-8")
        cena = raiz / "Assets/Cenas/Principal.cena"
        if not cena.exists():
            cena.write_text(json.dumps({"nome": "Principal", "objetos": [
                {"nome": "Câmera", "transform": {"x": 640, "y": 360},
                 "componentes": [{"tipo": "CameraPrincipal", "campos": {}}]}]}, indent=2), encoding="utf-8")
        return cls(raiz)

    def salvar_config(self):
        (self.raiz / "projeto.json").write_text(json.dumps({
            "nome": self.nome, "cena_inicial": self.cena_inicial,
            "largura": self.largura, "altura": self.altura, "camadas_desenho": self.camadas_desenho,
            "tags": self.tags, "gravidade": list(self.gravidade),
            "colisoes_ignoradas": self.colisoes_ignoradas}, indent=2, ensure_ascii=False), encoding="utf-8")

    def configuracoes(self) -> dict:
        """O que o motor precisa saber do projeto (aplicado em toda cena carregada)."""
        return {"camadas_desenho": self.camadas_desenho, "gravidade": self.gravidade,
                "colisoes_ignoradas": self.colisoes_ignoradas, "tags": self.tags}

    def relativo(self, caminho: str | Path) -> str:
        """Caminho como é salvo nas cenas: relativo à raiz do projeto, com '/'."""
        p = Path(caminho).resolve()
        try:
            return p.relative_to(self.raiz).as_posix()
        except ValueError:
            return p.as_posix()

    def criar_script(self, pasta: Path, nome: str) -> Path:
        # "meu jogador" → MeuJogador; "NaveInimiga" continua NaveInimiga (só a 1ª letra de cada palavra muda)
        import re
        partes = [p for p in re.split(r"[^0-9A-Za-zÀ-ÿ]+", nome) if p]
        nome = "".join(p[:1].upper() + p[1:] for p in partes) or "NovoScript"
        if nome[0].isdigit():
            nome = "Script" + nome
        arq = pasta / f"{nome}.py"
        k = 2
        while arq.exists():
            arq = pasta / f"{nome}{k}.py"
            k += 1
        arq.write_text(MODELO_SCRIPT.format(nome=arq.stem), encoding="utf-8")
        return arq

    def criar_agente(self, pasta: Path, nome: str) -> Path:
        nome = "".join(ch for ch in nome.lower() if ch.isalnum() or ch == "_") or "novo_agente"
        arq = pasta / f"{nome}.agt"
        k = 2
        while arq.exists():
            arq = pasta / f"{nome}{k}.agt"
            k += 1
        arq.write_text(MODELO_AGT.format(nome=arq.stem), encoding="utf-8")
        return arq

    # --- scripts -----------------------------------------------------------------
    def carregar_scripts(self) -> list[str]:
        """Importa (ou reimporta, se mudou) cada .py de Assets/. Devolve os que mudaram."""
        if str(self.raiz) not in sys.path:
            sys.path.insert(0, str(self.raiz))
        # As pastas com scripts entram no sys.path: um script pode fazer "from Comum import algo".
        for pasta in sorted({a.parent for a in (self.raiz / "Assets").rglob("*.py")}):
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
        # Módulos com o mesmo nome de um script deste projeto, mas vindos de OUTRO projeto
        # (ex.: dois projetos com Jogador.py), são esquecidos para o "import" achar o certo.
        for arq in (self.raiz / "Assets").rglob("*.py"):
            mod = sys.modules.get(arq.stem)
            arq_mod = getattr(mod, "__file__", None) if mod is not None else None
            if arq_mod and Path(arq_mod).resolve() != arq.resolve() and str(self.raiz) not in str(Path(arq_mod).resolve()):
                del sys.modules[arq.stem]
        if not self.scripts:
            # Primeira carga deste projeto: ações/percepções da DSL registradas por OUTRO projeto (no
            # mesmo processo) não podem valer aqui. Uma percepção alheia com o mesmo nome de uma
            # crença deste jogo faria a crença ser apagada a cada quadro.
            limpar_registros_dsl()
            for arq in (self.raiz / "Assets").rglob("*.py"):
                mod = sys.modules.get(arq.stem)
                arq_mod = getattr(mod, "__file__", None) if mod is not None else None
                if arq_mod and Path(arq_mod).resolve() == arq.resolve():
                    del sys.modules[arq.stem]      # executa de novo para registrar as ações outra vez
        mudaram = []
        self.erros_scripts = []
        vistos = set()
        for arq in sorted((self.raiz / "Assets").rglob("*.py")):
            chave = str(arq)
            vistos.add(chave)
            mtime = arq.stat().st_mtime
            info = self.scripts.get(chave)
            if info and info["mtime"] == mtime:
                if info["erro"]:
                    self.erros_scripts.append(info["erro"])
                continue
            nome_mod = arq.stem          # o mesmo nome que o "import" de outro script usaria
            antes = set(REGISTRO_COMPONENTES)
            try:
                existente = sys.modules.get(nome_mod)
                if (info is None and existente is not None and getattr(existente, "__file__", None)
                        and Path(existente.__file__).resolve() == arq.resolve()):
                    mod = existente      # já foi importado por outro script nesta carga: reaproveita
                else:
                    spec = importlib.util.spec_from_file_location(nome_mod, arq)
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[nome_mod] = mod
                    spec.loader.exec_module(mod)
                classes = [n for n, c in vars(mod).items()
                           if isinstance(c, type) and issubclass(c, Componente) and c.__module__ == nome_mod]
                self.scripts[chave] = {"modulo": mod, "mtime": mtime, "classes": classes, "erro": None}
            except Exception:
                erro = f"{arq.name}: " + traceback.format_exc(limit=3).strip().splitlines()[-1]
                detalhe = traceback.format_exc()
                self.scripts[chave] = {"modulo": None, "mtime": mtime, "classes": [], "erro": erro,
                                       "detalhe": detalhe}
                self.erros_scripts.append(erro)
                for n in set(REGISTRO_COMPONENTES) - antes:
                    REGISTRO_COMPONENTES.pop(n, None)
            mudaram.append(chave)
        for chave in list(self.scripts):
            if chave not in vistos:      # script apagado
                for n in self.scripts[chave]["classes"]:
                    REGISTRO_COMPONENTES.pop(n, None)
                del self.scripts[chave]
                mudaram.append(chave)
        return mudaram

    def descarregar(self) -> None:
        """Esquece os scripts deste projeto (ao abrir outro projeto no editor)."""
        for chave, info in self.scripts.items():
            for n in info["classes"]:
                REGISTRO_COMPONENTES.pop(n, None)
            mod = sys.modules.get(Path(chave).stem)
            if mod is not None and getattr(mod, "__file__", None) and Path(mod.__file__).resolve() == Path(chave):
                del sys.modules[Path(chave).stem]
        self.scripts.clear()
        limpar_registros_dsl()
        for p in list(sys.path):
            if p.startswith(str(self.raiz)):
                sys.path.remove(p)

    def classes_de_scripts(self) -> list[str]:
        saida = []
        for info in self.scripts.values():
            saida += info["classes"]
        return sorted(saida)
