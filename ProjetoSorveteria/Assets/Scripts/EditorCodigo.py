"""Editor de texto para escrever AgentDSL dentro do jogo, com os atalhos do VS Code.

- cores, números de linha e quebra de linha automática (o código nunca sai da janela);
- autocompletar (setas escolhem, Tab/Enter completa, Ctrl+Espaço abre, Esc fecha);
- seleção com o mouse (arrastar, Shift+clique, duplo clique = palavra, triplo = linha) e com o teclado
  (Shift+setas, Ctrl+Shift+setas, Shift+Home/End, Ctrl+A, Ctrl+L, Ctrl+D);
- Ctrl+C / Ctrl+X / Ctrl+V (sem seleção copiam/recortam a linha inteira), Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z;
- Ctrl+setas pulam palavras, Ctrl+Backspace/Delete apagam palavras, Ctrl+Home/End vão ao início/fim;
- Alt+setas movem a linha, Shift+Alt+setas duplicam, Ctrl+Shift+K apaga a linha,
  Tab/Shift+Tab indentam a seleção, Ctrl+/ (ou Ctrl+;) comenta, Ctrl+F procura.
"""
import re
import time

import pygame

PALAVRAS = {"agente", "modelo", "nao", "verdadeiro", "sprite", "em", "camada"}
CORES = {
    "texto": (220, 220, 225), "palavra": (198, 120, 221), "comentario": (110, 140, 110),
    "texto_str": (152, 195, 121), "numero": (209, 154, 102), "variavel": (97, 175, 239),
    "evento": (229, 192, 123), "simbolo": (171, 178, 191), "fundo": (30, 32, 40), "gutter": (38, 40, 50),
    "num_linha": (100, 105, 120), "cursor": (255, 255, 255), "linha_atual": (40, 44, 56),
    "erro": (110, 40, 45), "aviso": (95, 80, 30), "executou": (40, 105, 60), "selecao": (52, 86, 140),
    "achado": (120, 100, 40),
}
TOKEN = re.compile(r'(//.*$)|("(?:[^"\\]|\\.)*"?)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)|(<-|-\+|[+\-]!?|!)|(\s+)|(.)')
GUTTER = 40
RECUO_QUEBRA = 4          # as linhas quebradas continuam um pouco mais para dentro
PALAVRA = re.compile(r"\w")
_area_interna = {"texto": "", "linha": False}   # se pygame.scrap não funcionar, usa esta


class EditorCodigo:
    def __init__(self, texto: str):
        self.definir_texto(texto)
        self.focado = False
        self.marcas: dict[int, str] = {}       # linha (0-based) -> "erro" | "aviso"
        self.destaques: dict[int, float] = {}  # linha -> brilho (1 = acabou de executar), vai sumindo
        self._fonte = None
        self.mudou = False
        self.fonte_sugestoes = None            # função(prefixo, editor) -> [(inserir, rótulo, descrição)]
        self.sugestoes = []
        self.sel_sugestao = 0
        self._linhas_visuais = []              # [(linha, início, fim)] da última vez que desenhou
        self._cabe = 80
        self._col_desejada = None
        self.mouse_sobre = False
        self.arrastando = False
        self._cliques = (0.0, None, 0)         # (hora, posição, quantos) para duplo/triplo clique
        self.busca = None                      # texto da busca (Ctrl+F) ou None

    def definir_texto(self, texto: str):
        self.linhas = texto.replace("\r\n", "\n").replace("\t", "    ").split("\n") or [""]
        self.lin, self.col = 0, 0
        self.ancora = None                     # outra ponta da seleção (lin, col) ou None
        self.rolagem = 0
        self.desfazer = []
        self.refazer = []
        self.sugestoes = []

    @property
    def texto(self) -> str:
        return "\n".join(self.linhas)

    def fonte(self):
        if self._fonte is None:
            self._fonte = pygame.font.SysFont("consolas,couriernew,monospace", 14)
        return self._fonte

    def ir_para(self, linha: int, coluna: int = 0):
        self.lin = max(0, min(linha, len(self.linhas) - 1))
        self.col = max(0, min(coluna, len(self.linhas[self.lin])))
        self.ancora = None
        self.focado = True

    def destacar(self, linha: int):
        self.destaques[linha] = 1.0

    # --- seleção ----------------------------------------------------------------------------
    def selecao(self):
        """((lin, col) início, (lin, col) fim) em ordem, ou None se não houver seleção."""
        if self.ancora is None or self.ancora == (self.lin, self.col):
            return None
        return tuple(sorted((self.ancora, (self.lin, self.col))))

    def texto_selecionado(self):
        sel = self.selecao()
        if sel is None:
            return ""
        (l1, c1), (l2, c2) = sel
        if l1 == l2:
            return self.linhas[l1][c1:c2]
        return "\n".join([self.linhas[l1][c1:]] + self.linhas[l1 + 1:l2] + [self.linhas[l2][:c2]])

    def _apagar_selecao(self):
        sel = self.selecao()
        if sel is None:
            self.ancora = None
            return False
        (l1, c1), (l2, c2) = sel
        self.linhas[l1:l2 + 1] = [self.linhas[l1][:c1] + self.linhas[l2][c2:]]
        self.lin, self.col, self.ancora = l1, c1, None
        return True

    def selecionar_tudo(self):
        self.ancora = (0, 0)
        self.lin = len(self.linhas) - 1
        self.col = len(self.linhas[-1])

    def _linhas_da_selecao(self):
        sel = self.selecao()
        if sel is None:
            return self.lin, self.lin
        (l1, _), (l2, c2) = sel
        return l1, (l2 - 1 if c2 == 0 and l2 > l1 else l2)

    def _mover(self, shift, lin, col):
        """Move o cursor; com Shift a seleção estica, sem Shift ela some."""
        if shift and self.ancora is None:
            self.ancora = (self.lin, self.col)
        elif not shift:
            self.ancora = None
        self.lin, self.col = lin, col

    # --- palavras ------------------------------------------------------------------------------
    def _palavra_esq(self, lin, col):
        if col == 0:
            return (lin - 1, len(self.linhas[lin - 1])) if lin > 0 else (lin, col)
        s = self.linhas[lin]
        while col > 0 and s[col - 1] == " ":
            col -= 1
        tipo = bool(PALAVRA.match(s[col - 1])) if col > 0 else False
        while col > 0 and s[col - 1] != " " and bool(PALAVRA.match(s[col - 1])) == tipo:
            col -= 1
        return lin, col

    def _palavra_dir(self, lin, col):
        s = self.linhas[lin]
        if col >= len(s):
            return (lin + 1, 0) if lin < len(self.linhas) - 1 else (lin, col)
        while col < len(s) and s[col] == " ":
            col += 1
        tipo = bool(PALAVRA.match(s[col])) if col < len(s) else False
        while col < len(s) and s[col] != " " and bool(PALAVRA.match(s[col])) == tipo:
            col += 1
        return lin, col

    def _palavra_em(self, lin, col):
        s = self.linhas[lin]
        a = b = col
        while a > 0 and PALAVRA.match(s[a - 1]):
            a -= 1
        while b < len(s) and PALAVRA.match(s[b]):
            b += 1
        return a, b

    # --- quebra de linha ---------------------------------------------------------------------
    def _quebrar(self, s: str, cabe: int):
        """Divide uma linha em pedaços que cabem na largura (quebra nos espaços quando dá)."""
        if len(s) <= cabe:
            return [(0, len(s))]
        partes, ini, primeira = [], 0, True
        while ini < len(s):
            largura = cabe if primeira else max(8, cabe - RECUO_QUEBRA)
            if len(s) - ini <= largura:
                partes.append((ini, len(s)))
                break
            corte = s.rfind(" ", ini + 1, ini + largura + 1)
            fim = corte + 1 if corte > ini + largura // 3 else ini + largura
            partes.append((ini, fim))
            ini, primeira = fim, False
        return partes

    def _montar_visual(self, cabe: int):
        self._cabe = cabe
        self._linhas_visuais = [(i, a, b) for i, l in enumerate(self.linhas) for a, b in self._quebrar(l, cabe)]

    def _linha_visual(self, lin, col):
        for k, (i, a, b) in enumerate(self._linhas_visuais):
            if i == lin and a <= col and (col < b or b == len(self.linhas[i])):
                return k
        return 0

    def _linha_visual_do_cursor(self):
        return self._linha_visual(self.lin, self.col)

    def _x_visual(self, k, col):
        i, a, b = self._linhas_visuais[k]
        return col - a + (RECUO_QUEBRA if a > 0 else 0)

    def _col_na_linha_visual(self, k, x):
        i, a, b = self._linhas_visuais[k]
        x -= RECUO_QUEBRA if a > 0 else 0
        ultima = b == len(self.linhas[i])
        return max(a, min(a + max(0, x), b if ultima else max(a, b - 1)))

    # --- edição --------------------------------------------------------------------
    def _guardar(self):
        self.desfazer.append(("\n".join(self.linhas), self.lin, self.col))
        del self.desfazer[:-300]
        self.refazer.clear()
        self.mudou = True

    def _inserir(self, s: str, guardar=True):
        if guardar:
            self._guardar()
        self._apagar_selecao()
        linha = self.linhas[self.lin]
        partes = (linha[:self.col] + s + linha[self.col:]).split("\n")
        self.linhas[self.lin:self.lin + 1] = partes
        self.lin += len(partes) - 1
        self.col = len(partes[-1]) - len(linha[self.col:]) if len(partes) > 1 else self.col + len(s)

    def _prefixo(self):
        """O nome que está sendo digitado antes do cursor (para o autocompletar)."""
        m = re.search(r"[A-Za-z_][A-Za-z0-9_]*$", self.linhas[self.lin][:self.col])
        return m.group(0) if m else ""

    def _atualizar_sugestoes(self):
        prefixo = self._prefixo()
        antes = self.linhas[self.lin][:self.col - len(prefixo)]
        if not prefixo or self.fonte_sugestoes is None or "//" in antes or antes.count('"') % 2:
            self.sugestoes = []
            return
        sug = [s for s in self.fonte_sugestoes(prefixo, self) if s[0].rstrip("(") != prefixo]
        if sug != self.sugestoes:
            self.sel_sugestao = 0
        self.sugestoes = sug[:8]

    def _aceitar_sugestao(self):
        inserir = self.sugestoes[self.sel_sugestao][0]
        prefixo = self._prefixo()
        self._guardar()
        linha = self.linhas[self.lin]
        ini = self.col - len(prefixo)
        resto = linha[self.col:]
        if inserir.endswith("(") and resto.startswith("("):
            inserir = inserir[:-1]
        self.linhas[self.lin] = linha[:ini] + inserir + resto
        self.col = ini + len(inserir)
        self.ancora = None
        self.sugestoes = []

    def _desfazer(self, de, para):
        if de:
            para.append(("\n".join(self.linhas), self.lin, self.col))
            t, self.lin, self.col = de.pop()
            self.linhas = t.split("\n")
            self.lin = min(self.lin, len(self.linhas) - 1)
            self.col = min(self.col, len(self.linhas[self.lin]))
            self.ancora = None
            self.mudou = True

    def _indentar(self, menos):
        l1, l2 = self._linhas_da_selecao()
        self._guardar()
        for i in range(l1, l2 + 1):
            if menos:
                tirar = min(4, len(self.linhas[i]) - len(self.linhas[i].lstrip(" ")))
                self.linhas[i] = self.linhas[i][tirar:]
                if i == self.lin:
                    self.col = max(0, self.col - tirar)
                if self.ancora and self.ancora[0] == i:
                    self.ancora = (i, max(0, self.ancora[1] - tirar))
            else:
                self.linhas[i] = "    " + self.linhas[i]
                if i == self.lin:
                    self.col += 4
                if self.ancora and self.ancora[0] == i:
                    self.ancora = (i, self.ancora[1] + 4)

    def _comentar(self):
        l1, l2 = self._linhas_da_selecao()
        self._guardar()
        alvo = [i for i in range(l1, l2 + 1) if self.linhas[i].strip()] or [self.lin]
        tirar = all(self.linhas[i].lstrip().startswith("//") for i in alvo)
        recuo = min(len(self.linhas[i]) - len(self.linhas[i].lstrip()) for i in alvo)
        for i in alvo:
            s = self.linhas[i]
            if tirar:
                p = s.index("//")
                fim = p + 3 if s[p + 2:p + 3] == " " else p + 2
                self.linhas[i] = s[:p] + s[fim:]
            else:
                self.linhas[i] = s[:recuo] + "// " + s[recuo:]
        self.col = min(self.col, len(self.linhas[self.lin]))
        if self.ancora:
            self.ancora = (self.ancora[0], min(self.ancora[1], len(self.linhas[self.ancora[0]])))

    def _mover_linhas(self, d, copiar):
        l1, l2 = self._linhas_da_selecao()
        if not copiar and (l1 + d < 0 or l2 + d >= len(self.linhas)):
            return
        self._guardar()
        bloco = self.linhas[l1:l2 + 1]
        if copiar:
            self.linhas[l2 + 1:l2 + 1] = bloco
            if d > 0:
                self.lin += len(bloco)
                if self.ancora:
                    self.ancora = (self.ancora[0] + len(bloco), self.ancora[1])
            return
        del self.linhas[l1:l2 + 1]
        self.linhas[l1 + d:l1 + d] = bloco
        self.lin += d
        if self.ancora:
            self.ancora = (self.ancora[0] + d, self.ancora[1])

    def _copiar(self, recortar):
        if self.selecao():
            _area_transferencia(self.texto_selecionado(), linha=False)
            if recortar:
                self._guardar()
                self._apagar_selecao()
        else:                                    # sem seleção: a linha inteira (como no VS Code)
            _area_transferencia(self.linhas[self.lin] + "\n", linha=True)
            if recortar:
                self._guardar()
                if len(self.linhas) > 1:
                    del self.linhas[self.lin]
                    self.lin = min(self.lin, len(self.linhas) - 1)
                else:
                    self.linhas = [""]
                self.col = min(self.col, len(self.linhas[self.lin]))

    def _colar(self):
        texto, de_linha = _ler_area()
        if not texto:
            return
        texto = texto.replace("\r\n", "\n").replace("\t", "    ")
        if de_linha and not self.selecao():      # linha copiada sem seleção: entra acima da linha atual
            self._guardar()
            novas = texto.rstrip("\n").split("\n")
            self.linhas[self.lin:self.lin] = novas
            self.lin += len(novas)
            return
        self._inserir(texto)

    def _selecionar_proxima(self):
        """Ctrl+D: seleciona a palavra; com seleção, pula para a próxima ocorrência."""
        sel = self.selecao()
        if sel is None:
            a, b = self._palavra_em(self.lin, self.col)
            if a < b:
                self.ancora, self.col = (self.lin, a), b
            return
        self._procurar(self.texto_selecionado(), depois=sel[1])

    def _procurar(self, alvo, depois=None, para_tras=False):
        if not alvo or "\n" in alvo:
            return False
        lin, col = depois if depois else (self.lin, self.col)
        n = len(self.linhas)
        ordem = list(range(n))
        ordem = ordem[lin:] + ordem[:lin] + [lin] if not para_tras else (ordem[:lin + 1][::-1] + ordem[lin + 1:][::-1])
        for k, i in enumerate(ordem):
            s = self.linhas[i]
            if not para_tras:
                p = s.find(alvo, col if k == 0 else 0)
                if k == len(ordem) - 1 and p >= col:
                    p = -1
            else:
                p = s.rfind(alvo, 0, max(0, col - len(alvo) - 1) if k == 0 else len(s))
            if p >= 0:
                self.ancora, self.lin, self.col = (i, p), i, p + len(alvo)
                return True
        return False

    # --- teclado ---------------------------------------------------------------------------------
    def teclado(self, ent):
        """Trata as teclas. Devolve "compilar" quando o usuário pede Ctrl+Enter / Ctrl+S."""
        if not self.focado:
            self.sugestoes = []
            return None
        ctrl = (ent.tecla("left ctrl") or ent.tecla("right ctrl"))
        alt = ent.tecla("left alt") or ent.tecla("right alt")
        if ctrl and alt:                     # AltGr (Ctrl+Alt no Windows) digita caracteres
            ctrl = alt = False
        shift = ent.tecla("left shift") or ent.tecla("right shift")
        b = ent.tecla_baixou
        if ctrl and (b("return") or b("s")):
            self.sugestoes = []
            return "compilar"
        # --- busca (Ctrl+F) -----------------------------------------------------------------
        if self.busca is not None:
            if b("escape"):
                self.busca = None
                ent._baixou.discard("escape")
                return None
            if b("return") or b("enter") or b("f3"):
                self._procurar(self.busca, para_tras=shift)
                return None
            if b("backspace"):
                self.busca = self.busca[:-1]
                return None
            if ent.texto_digitado and not ctrl:
                self.busca += ent.texto_digitado
                if not self._procurar(self.busca, depois=self.selecao()[0] if self.selecao() else None):
                    pass
                return None
            if not (ctrl and b("f")):
                if not any(b(k) for k in ("left", "right", "up", "down")):
                    return None
        # --- lista do autocompletar aberta: setas, Tab/Enter e Esc são dela -----------------
        if self.sugestoes and not ctrl and not shift:
            if b("down"):
                self.sel_sugestao = (self.sel_sugestao + 1) % len(self.sugestoes)
                return None
            if b("up"):
                self.sel_sugestao = (self.sel_sugestao - 1) % len(self.sugestoes)
                return None
            if b("tab") or b("return") or b("enter"):
                self._aceitar_sugestao()
                return None
        if b("escape"):
            if self.sugestoes or self.selecao():
                self.sugestoes = []
                self.ancora = None
            else:
                self.focado = False
            ent._baixou.discard("escape")
            return None
        # --- atalhos com Ctrl -----------------------------------------------------------------
        if ctrl:
            if b("space"):
                self._atualizar_sugestoes()
            elif b("a"):
                self.selecionar_tudo()
            elif b("z") and not shift:
                self._desfazer(self.desfazer, self.refazer)
            elif b("y") or (b("z") and shift):
                self._desfazer(self.refazer, self.desfazer)
            elif b("c"):
                self._copiar(recortar=False)
            elif b("x"):
                self._copiar(recortar=True)
            elif b("v"):
                self._colar()
            elif b("l"):
                self.ancora = (self.lin, 0)
                if self.lin < len(self.linhas) - 1:
                    self.lin, self.col = self.lin + 1, 0
                else:
                    self.col = len(self.linhas[self.lin])
            elif b("d"):
                self._selecionar_proxima()
            elif b("k") and shift:
                self._guardar()
                l1, l2 = self._linhas_da_selecao()
                del self.linhas[l1:l2 + 1]
                if not self.linhas:
                    self.linhas = [""]
                self.lin = min(l1, len(self.linhas) - 1)
                self.col, self.ancora = min(self.col, len(self.linhas[self.lin])), None
            elif b("/") or b(";") or b("[/]") or b("'"):
                self._comentar()
            elif b("f"):
                self.busca = self.texto_selecionado() if self.selecao() and "\n" not in self.texto_selecionado() else ""
            elif b("home"):
                self._mover(shift, 0, 0)
            elif b("end"):
                self._mover(shift, len(self.linhas) - 1, len(self.linhas[-1]))
            elif b("left"):
                self._mover(shift, *self._palavra_esq(self.lin, self.col))
            elif b("right"):
                self._mover(shift, *self._palavra_dir(self.lin, self.col))
            elif b("up"):
                self.rolagem = max(0, self.rolagem - 1)
            elif b("down"):
                self.rolagem += 1
            elif b("backspace"):
                self._guardar()
                if not self._apagar_selecao():
                    self.ancora = self._palavra_esq(self.lin, self.col)
                    self._apagar_selecao()
            elif b("delete"):
                self._guardar()
                if not self._apagar_selecao():
                    self.ancora = self._palavra_dir(self.lin, self.col)
                    self._apagar_selecao()
            self.sugestoes = [] if not b("space") else self.sugestoes
            return None
        # --- Alt+setas: move a linha; Shift+Alt+setas: duplica -----------------------------------
        if alt:
            if b("up") or b("down"):
                self._mover_linhas(-1 if b("up") else 1, copiar=shift)
            return None
        # --- teclas sem Ctrl ---------------------------------------------------------------------
        digitou = False
        linha = self.linhas[self.lin]
        sel = self.selecao()
        if b("left"):
            if sel and not shift:
                self._mover(False, *sel[0])
            elif self.col > 0:
                self._mover(shift, self.lin, self.col - 1)
            elif self.lin > 0:
                self._mover(shift, self.lin - 1, len(self.linhas[self.lin - 1]))
        if b("right"):
            if sel and not shift:
                self._mover(False, *sel[1])
            elif self.col < len(linha):
                self._mover(shift, self.lin, self.col + 1)
            elif self.lin < len(self.linhas) - 1:
                self._mover(shift, self.lin + 1, 0)
        if b("up") or b("down"):
            self._mover_vertical(-1 if b("up") else 1, shift)
        else:
            self._col_desejada = None
        if b("page up") or b("page down"):
            d = -20 if b("page up") else 20
            l = max(0, min(len(self.linhas) - 1, self.lin + d))
            self._mover(shift, l, min(self.col, len(self.linhas[l])))
        if b("home"):
            recuo = len(linha) - len(linha.lstrip())
            self._mover(shift, self.lin, recuo if self.col != recuo else 0)
        if b("end"):
            self._mover(shift, self.lin, len(self.linhas[self.lin]))
        if b("backspace"):
            self._guardar()
            if not self._apagar_selecao():
                linha = self.linhas[self.lin]
                if self.col > 0:
                    apagar = 4 if linha[:self.col].endswith("    ") and not linha[:self.col].strip() else 1
                    self.linhas[self.lin] = linha[:self.col - apagar] + linha[self.col:]
                    self.col -= apagar
                elif self.lin > 0:
                    anterior = self.linhas[self.lin - 1]
                    self.col = len(anterior)
                    self.linhas[self.lin - 1] = anterior + linha
                    del self.linhas[self.lin]
                    self.lin -= 1
            digitou = True
        if b("delete"):
            self._guardar()
            if not self._apagar_selecao():
                linha = self.linhas[self.lin]
                if self.col < len(linha):
                    self.linhas[self.lin] = linha[:self.col] + linha[self.col + 1:]
                elif self.lin < len(self.linhas) - 1:
                    self.linhas[self.lin] = linha + self.linhas.pop(self.lin + 1)
        if b("return") or b("enter"):
            self._guardar()
            self._apagar_selecao()
            linha = self.linhas[self.lin]
            recuo = len(linha) - len(linha.lstrip())
            if linha[:self.col].rstrip().endswith(("{", "<-")):
                recuo += 4
            self._inserir("\n" + " " * recuo, guardar=False)
        if b("tab"):
            sel = self.selecao()
            if shift or (sel and sel[0][0] != sel[1][0]):
                self._indentar(menos=shift)
            else:
                self._inserir(" " * (4 - self.col % 4))
        if ent.texto_digitado:
            self._inserir(ent.texto_digitado)
            digitou = True
        if digitou:
            self._atualizar_sugestoes()
        elif any(b(k) for k in ("left", "right", "up", "down", "home", "end", "return", "page up", "page down",
                                 "delete", "tab")):
            self.sugestoes = []
        return None

    def _mover_vertical(self, d, shift=False):
        """Sobe/desce uma linha VISUAL (respeita a quebra de linha)."""
        if not self._linhas_visuais:
            l = max(0, min(len(self.linhas) - 1, self.lin + d))
            self._mover(shift, l, min(self.col, len(self.linhas[l])))
            return
        k = self._linha_visual_do_cursor()
        if self._col_desejada is None:
            self._col_desejada = self._x_visual(k, self.col)
        k2 = max(0, min(len(self._linhas_visuais) - 1, k + d))
        if k2 != k:
            self._mover(shift, self._linhas_visuais[k2][0], self._col_na_linha_visual(k2, self._col_desejada))
        elif not shift:
            self.ancora = None

    # --- desenho -------------------------------------------------------------------------
    def _pos_do_mouse(self, r, mx, my, alt_l, cw):
        vis = self._linhas_visuais
        k = max(0, min(self.rolagem + (my - r.y - 4) // alt_l, len(vis) - 1))
        return vis[k][0], self._col_na_linha_visual(k, round((mx - r.x - GUTTER - 6) / cw))

    def desenhar(self, ui, rect, ent, livre=True, dt=0.016):
        for k in list(self.destaques):
            self.destaques[k] -= dt * 1.6
            if self.destaques[k] <= 0:
                del self.destaques[k]
        r = pygame.Rect(rect)
        alto_busca = 24 if self.busca is not None else 0
        r_texto = pygame.Rect(r.x, r.y + alto_busca, r.w, r.h - alto_busca)
        f = self.fonte()
        alt_l = f.get_linesize() + 1
        cw = f.size("M")[0]
        cabe_lin = max(1, (r_texto.h - 8) // alt_l)
        self._montar_visual(max(10, (r.w - GUTTER - 18) // cw))
        vis = self._linhas_visuais
        mx, my = ent.mouse_tela
        # mouse: clique posiciona, arrastar seleciona, duplo clique = palavra, triplo = linha
        self.mouse_sobre = livre and r_texto.collidepoint(ent.mouse_tela)
        if self.mouse_sobre:
            if ent.roda:
                self.rolagem = max(0, min(self.rolagem - ent.roda * 3, max(0, len(vis) - cabe_lin)))
            if ent.clicou(1):
                ent.consumir_clique()
                self.focado = True
                self.sugestoes = []
                lin, col = self._pos_do_mouse(r_texto, mx, my, alt_l, cw)
                agora = time.time()
                t0, pos0, n = self._cliques
                n = n + 1 if agora - t0 < 0.4 and pos0 == (lin, col) else 1
                self._cliques = (agora, (lin, col), n)
                shift = ent.tecla("left shift") or ent.tecla("right shift")
                if n == 2:
                    a, b = self._palavra_em(lin, col)
                    self.ancora, self.lin, self.col = (lin, a), lin, b
                elif n >= 3:
                    self.ancora = (lin, 0)
                    self.lin, self.col = (lin + 1, 0) if lin < len(self.linhas) - 1 else (lin, len(self.linhas[lin]))
                else:
                    if shift:
                        if self.ancora is None:
                            self.ancora = (self.lin, self.col)
                    else:
                        self.ancora = (lin, col)
                    self.lin, self.col = lin, col
                    self.arrastando = True
        elif ent.clicou(1) and self.focado and not r.collidepoint(ent.mouse_tela):
            self.focado = False
            self.sugestoes = []
        if self.arrastando:
            if not ent.mouse_pressionado(1):
                self.arrastando = False
            else:
                if my < r_texto.y:
                    self.rolagem = max(0, self.rolagem - 1)
                elif my > r_texto.bottom:
                    self.rolagem = min(max(0, len(vis) - cabe_lin), self.rolagem + 1)
                self.lin, self.col = self._pos_do_mouse(r_texto, mx, max(r_texto.y, min(my, r_texto.bottom - 2)),
                                                        alt_l, cw)
        # mantém o cursor visível (menos enquanto rola com a roda/Ctrl+setas)
        kc = self._linha_visual_do_cursor()
        if not ent.roda and not self.arrastando:
            if kc < self.rolagem:
                self.rolagem = kc
            elif kc >= self.rolagem + cabe_lin:
                self.rolagem = kc - cabe_lin + 1
        self.rolagem = max(0, min(self.rolagem, max(0, len(vis) - cabe_lin)))
        s = ui.surface
        pygame.draw.rect(s, CORES["fundo"], r)
        pygame.draw.rect(s, CORES["gutter"], (r_texto.x, r_texto.y, GUTTER, r_texto.h))
        anterior = s.get_clip()
        s.set_clip(r_texto)
        y = r_texto.y + 4
        cores_linha = {}
        cursor_xy = None
        sel = self.selecao()
        for k in range(self.rolagem, min(len(vis), self.rolagem + cabe_lin)):
            i, a, b = vis[k]
            marca = self.marcas.get(i)
            fundo = None
            if marca:
                fundo = CORES[marca]
            elif i in self.destaques:
                t = self.destaques[i]
                fundo = tuple(int(CORES["fundo"][j] + (CORES["executou"][j] - CORES["fundo"][j]) * t) for j in range(3))
            elif i == self.lin and self.focado and not sel:
                fundo = CORES["linha_atual"]
            if fundo:
                pygame.draw.rect(s, fundo, (r.x + GUTTER, y - 1, r.w - GUTTER, alt_l))
            x0 = r.x + GUTTER + 6 + (RECUO_QUEBRA * cw if a > 0 else 0)
            if sel:                                         # fundo azul da seleção neste pedaço
                (l1, c1), (l2, c2) = sel
                if l1 <= i <= l2:
                    ini = max(a, c1) if i == l1 else a
                    fim = min(b, c2) if i == l2 else b
                    extra = cw if (i < l2 and b == len(self.linhas[i])) else 0
                    if fim > ini or extra:
                        pygame.draw.rect(s, CORES["selecao"], (x0 + cw * (ini - a), y - 1, cw * (fim - ini) + extra, alt_l))
            if self.busca:
                p = self.linhas[i].find(self.busca, a)
                while 0 <= p < b:
                    pygame.draw.rect(s, CORES["achado"], (x0 + cw * (p - a), y + alt_l - 4, cw * len(self.busca), 3))
                    p = self.linhas[i].find(self.busca, p + 1)
            if a == 0:
                num = f.render(str(i + 1), True, (255, 120, 120) if marca == "erro" else CORES["num_linha"])
                s.blit(num, (r.x + GUTTER - 6 - num.get_width(), y))
            else:   # continuação de uma linha quebrada
                pygame.draw.line(s, CORES["num_linha"], (r.x + GUTTER - 14, y + 3), (r.x + GUTTER - 14, y + alt_l - 6))
                pygame.draw.line(s, CORES["num_linha"], (r.x + GUTTER - 14, y + alt_l - 6), (r.x + GUTTER - 8, y + alt_l - 6))
            if i not in cores_linha:
                cores_linha[i] = self._cores(self.linhas[i])
            self._desenhar_trecho(s, f, self.linhas[i], cores_linha[i], a, b, x0, y, cw)
            if i == self.lin and (a <= self.col < b or (self.col == b and b == len(self.linhas[i]))):
                cursor_xy = (x0 + cw * (self.col - a), y)
            y += alt_l
        if cursor_xy and self.focado and int(time.time() * 2) % 2 == 0:
            pygame.draw.line(s, CORES["cursor"], cursor_xy, (cursor_xy[0], cursor_xy[1] + alt_l - 2), 2)
        s.set_clip(anterior)
        if self.busca is not None:
            barra = pygame.Rect(r.x, r.y, r.w, alto_busca)
            pygame.draw.rect(s, (44, 47, 60), barra)
            ui.texto(barra.x + 8, barra.centery, f"Procurar: {self.busca}|", 13, ancora="midleft", sombra=False)
            ui.texto(barra.right - 8, barra.centery, "Enter próxima · Shift+Enter anterior · Esc fecha", 10,
                     ancora="midright", cor=(160, 165, 180), sombra=False)
        pygame.draw.rect(s, (90, 140, 220) if self.focado else (60, 64, 76), r, 1)
        if len(vis) > cabe_lin:   # barra de rolagem
            h = max(20, r_texto.h * cabe_lin // len(vis))
            yb = r_texto.y + (r_texto.h - h) * self.rolagem // max(1, len(vis) - cabe_lin)
            pygame.draw.rect(s, (80, 84, 100), (r.right - 6, yb, 4, h), border_radius=2)
        if self.focado and self.sugestoes and cursor_xy:
            self._desenhar_sugestoes(ui, r, cursor_xy, alt_l, cw, ent, livre)

    def _desenhar_sugestoes(self, ui, r, cursor_xy, alt_l, cw, ent, livre):
        f = self.fonte()
        menor = pygame.font.SysFont("segoeui,arial", 12)
        w = min(r.w - 8, max(220, max(f.size(s[1])[0] + menor.size(s[2])[0] for s in self.sugestoes) + 30))
        h = 20 * len(self.sugestoes) + 6
        x = max(r.x + 4, min(cursor_xy[0] - cw * len(self._prefixo()), r.right - w - 4))
        y = cursor_xy[1] + alt_l
        if y + h > ui.altura - 4:
            y = cursor_xy[1] - h
        caixa = pygame.Rect(x, y, w, h)
        pygame.draw.rect(ui.surface, (44, 47, 60), caixa, border_radius=4)
        pygame.draw.rect(ui.surface, (95, 100, 125), caixa, 1, border_radius=4)
        for n, (inserir, rotulo, desc) in enumerate(self.sugestoes):
            lr = pygame.Rect(x + 2, y + 3 + 20 * n, w - 4, 20)
            if livre and lr.collidepoint(ent.mouse_tela):
                if ent.clicou(1):
                    ent.consumir_clique()
                    self.sel_sugestao = n
                    self._aceitar_sugestao()
                    return
            if n == self.sel_sugestao:
                pygame.draw.rect(ui.surface, (64, 92, 150), lr, border_radius=3)
            ui.surface.blit(f.render(rotulo, True, (235, 238, 245)), (lr.x + 6, lr.y + 2))
            ui.surface.blit(menor.render(desc, True, (165, 170, 190)),
                            (lr.x + 14 + f.size(rotulo)[0], lr.y + 3))
        ui.texto(x + w, y + h + 2, "Tab/Enter completa · Esc fecha", 10, ancora="topright",
                 cor=(140, 145, 160), sombra=True)

    @staticmethod
    def _desenhar_trecho(s, f, linha, cores, a, b, x0, y, cw):
        """Desenha linha[a:b] agrupando caracteres seguidos da mesma cor."""
        j = a
        while j < b:
            c = cores[j]
            k = j
            while k < b and cores[k] == c:
                k += 1
            trecho = linha[j:k]
            if trecho.strip():
                s.blit(f.render(trecho, True, c), (x0 + cw * (j - a), y))
            j = k

    @staticmethod
    def _cores(linha):
        cores = [CORES["texto"]] * len(linha)
        for m in TOKEN.finditer(linha):
            com, string, num, palavra, evento, espaco, outro = m.groups()
            if com:
                tipo = "comentario"
            elif string:
                tipo = "texto_str"
            elif num:
                tipo = "numero"
            elif palavra:
                tipo = ("palavra" if palavra in PALAVRAS else
                        "variavel" if palavra[0].isupper() or palavra[0] == "_" else "texto")
            elif evento:
                tipo = "evento"
            elif espaco:
                continue
            else:
                tipo = "simbolo"
            cores[m.start():m.end()] = [CORES[tipo]] * (m.end() - m.start())
        return cores


# --- área de transferência (a do sistema quando dá; senão uma interna) ------------------------------
def _area_transferencia(texto, linha=False):
    _area_interna["texto"], _area_interna["linha"] = texto, linha
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        pygame.scrap.put_text(texto)
    except Exception:
        pass


def _ler_area():
    texto = ""
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        texto = pygame.scrap.get_text() or ""
    except Exception:
        texto = ""
    if not texto:
        texto = _area_interna["texto"]
    texto = texto.replace("\x00", "")
    return texto, _area_interna["linha"] and texto == _area_interna["texto"]
