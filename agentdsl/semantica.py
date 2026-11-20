"""Análise semântica: tabela de símbolos, escopo de variáveis e verificação de tipos.

Escopos (aninhados):
    global  → nomes dos agentes
    agente  → assinaturas das crenças (nome/aridade → tipos dos argumentos)
    plano   → variáveis (ligadas no evento ou no contexto)

Tipos: num, atomo, texto, ? (desconhecido, ex.: variável cujo tipo não se infere).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import ast as A
from .erros import Diagnostico, Posicao

NUM, ATOMO, TEXTO, DESCONHECIDO = "num", "atomo", "texto", "?"


@dataclass(frozen=True)
class Assinatura:
    """Assinatura de uma ação: tipos dos parâmetros. ``variadica`` aceita N argumentos."""
    tipos: tuple = ()
    descricao: str = ""
    variadica: bool = False


# Ações que a ponte com a engine 2D sabe executar (ver ponte_engine.py).
ACOES_ENGINE: dict[str, Assinatura] = {
    "mover": Assinatura((NUM, NUM), "desloca o sprite (dx, dy) uma vez"),
    "posicionar": Assinatura((NUM, NUM), "coloca o sprite em (x, y)"),
    "rotacionar": Assinatura((NUM,), "gira o sprite N graus uma vez"),
    "girar": Assinatura((NUM,), "rotação contínua (graus por segundo)"),
    "escalar": Assinatura((NUM,), "multiplica a escala pelo fator"),
    "velocidade": Assinatura((NUM, NUM), "movimento contínuo (px/s em x e y)"),
    "inverter": Assinatura((), "inverte a velocidade atual"),
    "parar": Assinatura((), "zera velocidade e rotação contínua"),
    "perseguir": Assinatura((ATOMO, NUM), "anda em direção ao agente/objeto alvo"),
    "fugir": Assinatura((ATOMO, NUM), "anda para longe do alvo"),
    "mudar_camada": Assinatura((NUM,), "muda a camada de renderização"),
    "cor": Assinatura((NUM, NUM, NUM), "tinta RGB (0 a 1)"),
    "sumir": Assinatura((), "esconde o sprite"),
    "aparecer": Assinatura((), "mostra o sprite"),
    "imprimir": Assinatura((), "escreve no log", variadica=True),
}


@dataclass
class SimboloAgente:
    nome: str
    pos: Posicao | None
    crencas: dict = field(default_factory=dict)   # (nome, aridade) -> [tipos]


class TabelaSimbolos:
    def __init__(self):
        self.agentes: dict[str, SimboloAgente] = {}
        self.pilha: list[dict] = []   # escopos de variáveis (plano)

    def abrir_escopo(self):
        self.pilha.append({})

    def fechar_escopo(self):
        return self.pilha.pop()

    def declarar_var(self, nome: str, tipo: str, pos):
        esc = self.pilha[-1]
        if nome in esc:
            info = esc[nome]
            info["usos"] += 1
            if info["tipo"] == DESCONHECIDO:
                info["tipo"] = tipo
        else:
            esc[nome] = {"tipo": tipo, "pos": pos, "usos": 1}

    def buscar_var(self, nome: str):
        for esc in reversed(self.pilha):
            if nome in esc:
                return esc[nome]
        return None

    def descrever(self) -> str:
        linhas = ["Tabela de símbolos"]
        for ag in self.agentes.values():
            linhas.append(f"  agente {ag.nome} ({ag.pos})")
            for (n, ar), tipos in sorted(ag.crencas.items()):
                linhas.append(f"    crença {n}/{ar}: ({', '.join(tipos)})")
        return "\n".join(linhas)


class AnalisadorSemantico:
    def __init__(self, acoes: dict[str, Assinatura] | None = None,
                 percepcoes: dict[tuple, tuple] | None = None, alvos=()):
        """``percepcoes``: crenças que o AMBIENTE adiciona/remove, (nome, aridade) → tipos.
        Servem para não avisar "evento nunca acontece" e para inferir tipos.
        ``alvos``: nomes de objetos do ambiente que não são agentes (ex.: jogador)."""
        self.acoes = dict(ACOES_ENGINE if acoes is None else acoes)
        self.percepcoes = dict(percepcoes or {})
        self.alvos_extras = set(alvos)
        self.tabela = TabelaSimbolos()
        self.diags: list[Diagnostico] = []

    # --- diagnósticos -----------------------------------------------------
    def _erro(self, msg, pos):
        self.diags.append(Diagnostico("semantico", msg, pos))

    def _aviso(self, msg, pos):
        self.diags.append(Diagnostico("semantico", msg, pos, gravidade="aviso"))

    # --- herança -----------------------------------------------------------
    def _resolver_heranca(self, prog: A.Programa) -> None:
        """Copia crenças e planos do pai para o filho (planos do filho têm prioridade).

        Regras: o pai precisa existir e estar declarado ANTES do filho (o que também
        impede ciclos). Uma crença inicial do filho com mesmo nome/aridade substitui a do pai.
        """
        vistos: dict[str, A.Agente] = {}
        for ag in prog.agentes:
            if ag.pai is not None:
                pai = vistos.get(ag.pai)
                if pai is None:
                    existe = any(a.nome == ag.pai for a in prog.agentes)
                    self._erro(f"agente pai '{ag.pai}' " + ("deve ser declarado antes de " if existe
                               else "não existe (herança em ") + f"'{ag.nome}'" + ("" if existe else ")"),
                               ag.pai_pos)
                else:
                    proprias = {(c.nome, c.aridade) for c in ag.crencas}
                    ag.crencas = [c for c in pai.crencas if (c.nome, c.aridade) not in proprias] + ag.crencas
                    ag.planos = ag.planos + list(pai.planos)
                    if ag.sprite is None:
                        ag.sprite = pai.sprite
            vistos.setdefault(ag.nome, ag)

    # --- entrada ----------------------------------------------------------
    def analisar(self, prog: A.Programa) -> list[Diagnostico]:
        self._resolver_heranca(prog)
        diags_heranca = len(self.diags)
        nomes_alvo = set()
        for ag in prog.agentes:
            if ag.nome in self.tabela.agentes:
                ant = self.tabela.agentes[ag.nome].pos
                self._erro(f"agente '{ag.nome}' já foi definido (linha {ant.linha})", ag.pos)
                continue
            self.tabela.agentes[ag.nome] = SimboloAgente(ag.nome, ag.pos)
            nomes_alvo.add(ag.nome)
        self.nomes_agentes = nomes_alvo
        for ag in prog.agentes:
            if self.tabela.agentes.get(ag.nome) and self.tabela.agentes[ag.nome].pos is ag.pos:
                self._agente(ag, self.tabela.agentes[ag.nome])
        # Planos herdados são analisados em cada filho: remove diagnósticos repetidos.
        unicos, vistos = self.diags[:diags_heranca], set()
        for d in self.diags[diags_heranca:]:
            chave = (d.mensagem, d.pos, d.gravidade)
            if chave not in vistos:
                vistos.add(chave)
                unicos.append(d)
        self.diags = sorted(unicos, key=lambda d: (d.pos.linha, d.pos.coluna) if d.pos else (0, 0))
        return self.diags

    def _agente(self, ag: A.Agente, sim: SimboloAgente):
        # 1) crenças iniciais: devem ser fatos ("ground"), sem variáveis
        for c in ag.crencas:
            tipos = []
            for arg in c.args:
                if self._tem_variavel(arg):
                    self._erro(f"crença inicial '{c}' não pode conter variáveis", arg.pos or c.pos)
                    tipos.append(DESCONHECIDO)
                else:
                    tipos.append(self._tipo_expr(arg, contexto_tipos=False))
            self._registrar_crenca(sim, c, tipos)
        for chave, tipos in self.percepcoes.items():
            sim.crencas.setdefault(chave, list(tipos))
        # 2) crenças produzidas pelos próprios planos (+lit / -+lit)
        produzidas = {(c.nome, c.aridade) for c in ag.crencas} | set(self.percepcoes)
        for p in ag.planos:
            for a in p.acoes:
                if isinstance(a, A.AcaoCrenca) and a.op in ("+", "-+"):
                    produzidas.add((a.literal.nome, a.literal.aridade))
        # 3) planos
        for p in ag.planos:
            self._plano(p, sim, produzidas)

    def _registrar_crenca(self, sim, lit: A.Literal, tipos):
        chave = (lit.nome, lit.aridade)
        mesmas = [k for k in sim.crencas if k[0] == lit.nome and k[1] != lit.aridade]
        if mesmas:
            self._aviso(f"crença '{lit.nome}' usada com aridades diferentes "
                        f"({lit.aridade} e {mesmas[0][1]})", lit.pos)
        if chave not in sim.crencas:
            sim.crencas[chave] = list(tipos)
        else:
            antigo = sim.crencas[chave]
            for i, (t_old, t_new) in enumerate(zip(antigo, tipos)):
                if t_old == DESCONHECIDO:
                    antigo[i] = t_new
                elif t_new not in (DESCONHECIDO, t_old):
                    self._erro(f"argumento {i + 1} de '{lit.nome}' é {t_old} em outro lugar, mas aqui é {t_new}",
                               lit.pos)

    # --- planos -----------------------------------------------------------
    def _plano(self, p: A.Plano, sim: SimboloAgente, produzidas: set):
        t = self.tabela
        t.abrir_escopo()
        ev = p.evento.literal
        if (ev.nome, ev.aridade) not in produzidas:
            self._aviso(f"o evento '{p.evento}' nunca será gerado: a crença '{ev.nome}/{ev.aridade}' "
                        f"não é inicial, não é percepção do ambiente e nenhum plano a adiciona", p.evento.pos)
        # O evento liga as variáveis que aparecem nele.
        self._ligar_literal(ev, sim)

        for cond in p.contexto:
            if isinstance(cond, A.CondLiteral):
                if cond.negado:
                    # Negação por falha: só é segura com variáveis já ligadas.
                    self._usar_vars(cond.literal, "na negação 'nao'")
                    self._checar_tipos_literal(cond.literal, sim)
                else:
                    self._ligar_literal(cond.literal, sim)
            elif isinstance(cond, A.Comparacao):
                self._usar_vars(cond.esq, "na comparação")
                self._usar_vars(cond.dir, "na comparação")
                te, td = self._tipo_expr(cond.esq), self._tipo_expr(cond.dir)
                if cond.op not in ("==", "!="):
                    for lado, tp in ((cond.esq, te), (cond.dir, td)):
                        if tp not in (NUM, DESCONHECIDO):
                            self._erro(f"o operador '{cond.op}' exige números, mas '{lado}' é {tp}", cond.pos)
                elif DESCONHECIDO not in (te, td) and te != td:
                    self._aviso(f"comparação '{cond}' entre tipos diferentes ({te} e {td}) é sempre "
                                f"{'falsa' if cond.op == '==' else 'verdadeira'}", cond.pos)

        for a in p.acoes:
            if isinstance(a, A.AcaoCrenca):
                self._usar_vars(a.literal, f"em '{a.op}{a.literal.nome}'")
                tipos = [self._tipo_expr(x) for x in a.literal.args]
                self._registrar_crenca(sim, a.literal, tipos)
            else:
                self._acao(a)

        escopo = t.fechar_escopo()
        for nome, info in escopo.items():
            if info["usos"] == 1 and not nome.startswith("_"):
                self._aviso(f"variável '{nome}' aparece uma só vez no plano (use _{nome} se for proposital)",
                            info["pos"])

    def _ligar_literal(self, lit: A.Literal, sim):
        tipos_crenca = sim.crencas.get((lit.nome, lit.aridade))
        for i, arg in enumerate(lit.args):
            if isinstance(arg, A.Variavel):
                tipo = tipos_crenca[i] if tipos_crenca and i < len(tipos_crenca) else DESCONHECIDO
                self.tabela.declarar_var(arg.nome, tipo, arg.pos)
            else:
                self._usar_vars(arg, f"em '{lit.nome}'")
                self._tipo_expr(arg)
        self._checar_tipos_literal(lit, sim)

    def _checar_tipos_literal(self, lit, sim):
        tipos_crenca = sim.crencas.get((lit.nome, lit.aridade))
        if not tipos_crenca:
            return
        for i, arg in enumerate(lit.args):
            if isinstance(arg, A.Variavel):
                continue
            tp = self._tipo_expr(arg)
            esperado = tipos_crenca[i]
            if DESCONHECIDO not in (tp, esperado) and tp != esperado:
                self._erro(f"argumento {i + 1} de '{lit.nome}' deveria ser {esperado}, mas '{arg}' é {tp}", lit.pos)

    def _acao(self, a: A.AcaoExterna):
        sig = self.acoes.get(a.nome)
        if sig is None:
            sugestao = self._parecida(a.nome, self.acoes)
            self._erro(f"ação desconhecida '{a.nome}'" + (f" (quis dizer '{sugestao}'?)" if sugestao else ""), a.pos)
            for arg in a.args:
                self._usar_vars(arg, f"em '{a.nome}'")
            return
        for arg in a.args:
            self._usar_vars(arg, f"em '{a.nome}'")
        if not sig.variadica and len(a.args) != len(sig.tipos):
            self._erro(f"'{a.nome}' espera {len(sig.tipos)} argumento(s), recebeu {len(a.args)}", a.pos)
            return
        for i, (arg, esperado) in enumerate(zip(a.args, sig.tipos)):
            tp = self._tipo_expr(arg)
            if esperado == ATOMO and isinstance(arg, A.Atomo) and arg.nome not in self.nomes_agentes \
                    and arg.nome not in getattr(self, "alvos_extras", set()):
                self._aviso(f"alvo '{arg.nome}' em '{a.nome}' não é um agente declarado", arg.pos)
            if DESCONHECIDO not in (tp, esperado) and tp != esperado:
                self._erro(f"argumento {i + 1} de '{a.nome}' deveria ser {esperado}, mas '{arg}' é {tp}",
                           arg.pos or a.pos)

    # --- expressões ---------------------------------------------------------
    def _usar_vars(self, no, onde: str):
        """Toda variável usada precisa estar ligada antes (regra de escopo)."""
        for v in self._variaveis(no):
            info = self.tabela.buscar_var(v.nome)
            if info is None:
                self._erro(f"variável '{v.nome}' usada {onde} sem estar ligada no evento ou no contexto", v.pos)
                self.tabela.declarar_var(v.nome, DESCONHECIDO, v.pos)  # evita erro repetido
                self.tabela.pilha[-1][v.nome]["usos"] = 2
            else:
                info["usos"] += 1

    def _variaveis(self, no):
        if isinstance(no, A.Variavel):
            yield no
        elif isinstance(no, A.BinOp):
            yield from self._variaveis(no.esq)
            yield from self._variaveis(no.dir)
        elif isinstance(no, A.Negativo):
            yield from self._variaveis(no.expr)
        elif isinstance(no, A.Literal):
            for a in no.args:
                yield from self._variaveis(a)

    def _tem_variavel(self, no) -> bool:
        return any(True for _ in self._variaveis(no))

    def _tipo_expr(self, no, contexto_tipos: bool = True) -> str:
        if isinstance(no, A.Numero):
            return NUM
        if isinstance(no, A.Texto):
            return TEXTO
        if isinstance(no, A.Atomo):
            return ATOMO
        if isinstance(no, A.Variavel):
            info = self.tabela.buscar_var(no.nome) if contexto_tipos and self.tabela.pilha else None
            return info["tipo"] if info else DESCONHECIDO
        if isinstance(no, A.Negativo):
            t = self._tipo_expr(no.expr, contexto_tipos)
            if t not in (NUM, DESCONHECIDO):
                self._erro(f"'-' aplicado a um valor do tipo {t} ('{no.expr}')", no.pos)
            return NUM
        if isinstance(no, A.BinOp):
            for lado in (no.esq, no.dir):
                t = self._tipo_expr(lado, contexto_tipos)
                if t not in (NUM, DESCONHECIDO):
                    self._erro(f"operação aritmética '{no.op}' com valor do tipo {t} ('{lado}')", no.pos)
                if isinstance(lado, A.Variavel) and t == DESCONHECIDO and contexto_tipos and self.tabela.pilha:
                    info = self.tabela.buscar_var(lado.nome)
                    if info:
                        info["tipo"] = NUM   # inferência: usada em conta => número
            if no.op == "/" and isinstance(no.dir, A.Numero) and no.dir.valor == 0:
                self._erro("divisão por zero", no.pos)
            return NUM
        return DESCONHECIDO

    @staticmethod
    def _parecida(nome, opcoes):
        import difflib
        m = difflib.get_close_matches(nome, list(opcoes), n=1, cutoff=0.6)
        return m[0] if m else None
