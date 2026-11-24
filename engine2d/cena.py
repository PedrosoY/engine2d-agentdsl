"""Cena: o conjunto de GameObjects, o ciclo de vida dos componentes e prefabs/JSON."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .fisica import Fisica
from .lista_render import ListaRenderizacao
from .objeto import REGISTRO_COMPONENTES, Componente, ComponenteAusente, GameObject

_tardio_base = Componente.atualizar_tardio


class Cena:
    """Ordem de um quadro (``atualizar``):
      1. ``iniciar()`` dos componentes recém-adicionados (Start);
      2. ``atualizar(dt)`` de todos os componentes ativos (Update), depois
         ``atualizar_tardio(dt)``;
      3. física: integra velocidades, resolve colisões, dispara eventos;
      4. destruições pendentes (o objeto some no fim do quadro).
    """

    def __init__(self, nome: str = "Cena", agrupar_texturas: bool = True, modo_edicao: bool = False):
        self.nome = nome
        # Modo de edição (editor fora do Play): só componentes com EXECUTA_NO_EDITOR iniciam.
        self.modo_edicao = modo_edicao
        self.motor = None
        self.objetos: list[GameObject] = []
        self.lista = ListaRenderizacao(agrupar_texturas=agrupar_texturas)
        self.fisica = Fisica()
        self.prefabs: dict[str, dict] = {}
        self.servicos: dict[str, object] = {}     # sistemas globais (ex.: agentes da DSL)
        self._a_iniciar: list = []
        self._a_destruir: list[tuple[GameObject, float]] = []
        self.tempo = 0.0
        self._cache_nomes: dict[str, GameObject] = {}
        self.arquivo = None
        self.luzes: list = []                # componentes Luz2D (iluminação 2D)
        self.projetores_sombra: list = []    # componentes ProjetorSombra2D

    # --- criação / remoção --------------------------------------------------------
    def criar(self, nome="GameObject", x=0.0, y=0.0, componentes=(), pai=None, **kw) -> GameObject:
        go = GameObject(nome, x, y, pai=pai, **kw)
        for c in componentes:
            go.adicionar(c)
        return self.adicionar(go)

    def adicionar(self, go: GameObject) -> GameObject:
        if go.cena is self:
            return go
        go.cena = self
        self.objetos.append(go)
        for c in go.componentes:
            self._agendar_inicio(c)
        for f in go.filhos:
            self.adicionar(f)
        return go

    def _agendar_inicio(self, comp) -> None:
        self._a_iniciar.append(comp)

    def destruir(self, go: GameObject, atraso: float = 0.0) -> None:
        if not go.destruido:
            self._a_destruir.append((go, atraso))

    def _destruir_agora(self, go: GameObject) -> None:
        if go.destruido:
            return
        for f in list(go.filhos):
            self._destruir_agora(f)
        go.destruido = True
        for c in list(go.componentes):
            try:
                c.ao_destruir()
            except Exception as e:  # um componente com erro não pode travar a cena
                print(f"[cena] erro em {type(c).__name__}.ao_destruir: {e}")
        go.transform.definir_pai(None)
        if go in self.objetos:
            self.objetos.remove(go)
        go.cena = None

    # --- consultas ------------------------------------------------------------------
    def encontrar(self, nome: str) -> GameObject | None:
        """Busca por nome. Usa cache: centenas de inimigos procuram
        o jogador todo quadro, e a busca linear seria O(n) para cada um."""
        go = self._cache_nomes.get(nome)
        if go is not None and not go.destruido and go.nome == nome and go.cena is self:
            return go
        for go in self.objetos:
            if go.nome == nome and not go.destruido:
                self._cache_nomes[nome] = go
                return go
        self._cache_nomes.pop(nome, None)
        return None

    def com_tag(self, tag: str) -> list[GameObject]:
        return [g for g in self.objetos if g.tag == tag and not g.destruido]

    def componentes_do_tipo(self, tipo) -> list:
        saida = []
        for g in self.objetos:
            saida += g.obter_todos(tipo)
        return saida

    def raizes(self) -> list[GameObject]:
        return [g for g in self.objetos if g.transform.pai is None]

    # --- ciclo do quadro --------------------------------------------------------------
    def iniciar_pendentes(self) -> None:
        while self._a_iniciar:
            pend, self._a_iniciar = self._a_iniciar, []
            for c in pend:
                if self.modo_edicao and not type(c).EXECUTA_NO_EDITOR:
                    continue
                if not c._iniciado and c.gameobject is not None and not c.gameobject.destruido:
                    c._iniciado = True
                    c.iniciar()

    def atualizar(self, dt: float) -> None:
        self.tempo += dt
        self.iniciar_pendentes()
        for go in list(self.objetos):
            if go.destruido or not go.ativo_na_hierarquia:
                continue
            for c in list(go.componentes):
                if c.habilitado and c._iniciado:
                    c.atualizar(dt)
        for go in list(self.objetos):
            if go.destruido or not go.ativo_na_hierarquia:
                continue
            for c in go.componentes:
                if c.habilitado and c._iniciado and type(c).atualizar_tardio is not _tardio_base:
                    c.atualizar_tardio(dt)
        self.fisica.passo(dt)
        self.processar_destruicoes(dt)

    def processar_destruicoes(self, dt: float = 0.0) -> None:
        restantes = []
        for go, atraso in self._a_destruir:
            atraso -= dt
            if atraso <= 0:
                self._destruir_agora(go)
            else:
                restantes.append((go, atraso))
        self._a_destruir = restantes

    def numerar_hierarquia(self) -> None:
        """Dá a cada objeto a posição dele na Hierarchy (de cima para baixo, filhos logo depois do
        pai). É o desempate da ordem de desenho: mais embaixo na lista = desenhado por cima."""
        n = 0
        pilha = list(reversed(self.raizes()))
        while pilha:
            go = pilha.pop()
            go.indice_hierarquia = n
            n += 1
            pilha.extend(reversed(go.filhos))

    def mover_na_hierarquia(self, go: GameObject, pai: GameObject | None, posicao: int) -> None:
        """Muda o pai e a posição de ``go`` entre os irmãos (arrastar na Hierarchy)."""
        go.transform.definir_pai(pai.transform if pai else None, manter_mundo=True)
        if pai is not None:
            irmaos = pai.transform.filhos
            irmaos.remove(go.transform)
            irmaos.insert(max(0, min(posicao, len(irmaos))), go.transform)
        else:
            raizes = [g for g in self.raizes() if g is not go]
            posicao = max(0, min(posicao, len(raizes)))
            self.objetos.remove(go)
            if posicao < len(raizes):
                self.objetos.insert(self.objetos.index(raizes[posicao]), go)
            else:
                self.objetos.append(go)

    def sincronizar_render(self) -> None:
        """Copia as poses dos GameObjects para os sprites (antes de desenhar)."""
        self.iniciar_pendentes()
        self.numerar_hierarquia()
        for go in self.objetos:
            for c in go.componentes:
                sinc = getattr(c, "sincronizar", None)
                if sinc is not None and c._iniciado:
                    sinc()

    def iluminacao(self) -> dict | None:
        """Dados das luzes para o renderizador, ou None se a cena não tem nenhuma Luz2D ligada
        (aí tudo aparece com a cor normal). Luz ambiente = soma das luzes globais."""
        ativas = [l for l in self.luzes if l.habilitado and l.gameobject is not None
                  and l.gameobject.ativo_na_hierarquia and not l.gameobject.destruido]
        if not ativas:
            return None
        amb = [0.0, 0.0, 0.0]
        pontos = []
        for l in ativas:
            if l.tipo == "global":
                i = l.intensidade_atual()
                for k in range(3):
                    amb[k] += l.cor[k] * i
            else:
                pontos.append(l.dados())
        sombras = [d for d in (p.dados() for p in self.projetores_sombra) if d is not None]
        return {"ambiente": tuple(amb), "pontos": pontos, "sombras": sombras}

    def desenhar_ui(self, ui) -> None:
        for go in self.objetos:
            if go.destruido or not go.ativo_na_hierarquia:
                continue
            for c in go.componentes:
                if c.habilitado and c._iniciado:
                    c.desenhar_ui(ui)

    # --- prefabs e serialização ------------------------------------------------------------
    def registrar_prefab(self, nome: str, dados: dict) -> None:
        self.prefabs[nome] = dados

    def instanciar(self, prefab: str | dict, x: float = 0.0, y: float = 0.0, pai=None, **substituir) -> GameObject:
        """Cria um GameObject a partir de um prefab (dict, nome registrado ou "Assets/Prefabs/x.prefab").

        ``substituir`` troca campos de componentes: ``SpriteRenderer__imagem="x.png"``.
        """
        if isinstance(prefab, str) and prefab.endswith(".prefab") and prefab not in self.prefabs:
            self.prefabs[prefab] = json.loads(Path(prefab).read_text(encoding="utf-8"))
        dados = copy.deepcopy(self.prefabs[prefab] if isinstance(prefab, str) else prefab)
        for chave, valor in substituir.items():
            tipo, campo = chave.split("__", 1)
            for c in dados.get("componentes", []):
                if c["tipo"] == tipo:
                    c.setdefault("campos", {})[campo] = valor
        go = objeto_de_dict(dados)
        go.transform.x, go.transform.y = float(x), float(y)
        if pai is not None:
            go.transform.definir_pai(pai.transform)
        return self.adicionar(go)

    def para_dict(self) -> dict:
        return {"nome": self.nome, "objetos": [objeto_para_dict(g) for g in self.raizes() if not g.destruido and not g.oculto]}

    def salvar(self, caminho) -> None:
        Path(caminho).write_text(json.dumps(self.para_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def carregar_dict(self, dados: dict) -> None:
        for g in list(self.objetos):
            self._destruir_agora(g)
        self.nome = dados.get("nome", self.nome)
        for od in dados.get("objetos", []):
            self.adicionar(objeto_de_dict(od))

    def carregar(self, caminho) -> None:
        self.carregar_dict(json.loads(Path(caminho).read_text(encoding="utf-8")))
        self.arquivo = str(caminho)       # motor.reiniciar_cena() usa para recarregar


def objeto_para_dict(go: GameObject) -> dict:
    t = go.transform
    return {
        "nome": go.nome, "tag": go.tag, "ativo": go.ativo,
        "transform": {"x": t.x, "y": t.y, "rotacao": t.rotacao, "escala_x": t.escala_x, "escala_y": t.escala_y},
        "componentes": [c.para_dict() for c in go.componentes],
        "filhos": [objeto_para_dict(f) for f in go.filhos if not f.oculto],
    }


def objeto_de_dict(d: dict) -> GameObject:
    go = GameObject(d.get("nome", "GameObject"), tag=d.get("tag", ""))
    go.ativo = d.get("ativo", True)
    t = d.get("transform", {})
    tr = go.transform
    tr.x, tr.y = float(t.get("x", 0)), float(t.get("y", 0))
    tr.rotacao = float(t.get("rotacao", 0))
    tr.escala_x = float(t.get("escala_x", t.get("escala", 1)))
    tr.escala_y = float(t.get("escala_y", t.get("escala", 1)))
    for cd in d.get("componentes", []):
        cls = REGISTRO_COMPONENTES.get(cd["tipo"])
        campos = {k: (tuple(v) if isinstance(v, list) else v) for k, v in cd.get("campos", {}).items()}
        if cls is None:
            go.adicionar(ComponenteAusente(cd["tipo"], cd.get("campos", {})))
            continue
        validos = cls._todos_campos()
        go.adicionar(cls(**{k: v for k, v in campos.items() if k in validos or hasattr(cls, k)}))
    for fd in d.get("filhos", []):
        filho = objeto_de_dict(fd)
        filho.transform.definir_pai(tr)
    return go
