"""Traduz os erros do compilador da AgentDSL para mensagens de iniciante, com dica de como consertar.

O compilador (léxico, sintático, semântico) diz O QUE está errado; aqui o jogo reconhece os erros mais
comuns e explica do jeito que um tutor explicaria.
"""
import difflib
import re

from Itens import CALDAS, COBERTURAS, ESTACOES, MASSAS, PONTOS, ROBOS, TAMANHOS, TIPOS

OPCOES = set(TAMANHOS + TIPOS + MASSAS + PONTOS + CALDAS + COBERTURAS + ESTACOES + ROBOS)


def amigavel(d, linhas):
    """Devolve (mensagem, dica) para o diagnóstico ``d``. ``linhas`` é o texto da janela, linha a linha."""
    msg = d.mensagem
    linha = linhas[d.pos.linha - 1] if d.pos and 0 < d.pos.linha <= len(linhas) else ""
    antes = linha[:d.pos.coluna - 1] if d.pos else ""

    if "no fim do plano" in msg and "esperava '.'" in msg:
        if "','" in msg or "encontrou ','" in msg:
            return "Comandos são separados por ';' e não por ','.", "Troque a vírgula por ponto e vírgula."
        return ("Faltou o ponto final '.' no fim do plano.",
                "Todo plano termina com '.'. O erro aparece no começo da próxima coisa que o robô leu.")
    if "esperava '<-'" in msg or "esperava SETA" in msg:
        if "encontrou '='" in msg or "encontrou '-'" in msg:
            return "A seta é '<-' (menor e hífen, juntos).", "Ex.: +!comecar <- dancar."
        return "Faltou a seta '<-' entre o objetivo e os comandos.", "Ex.: +!produzir <- pegar_casquinha."
    if msg.startswith("esperava uma ação") or msg.startswith("esperava um valor"):
        if "encontrou '.'" in msg and antes.rstrip().endswith(";"):
            return "Sobrou um ';' antes do '.'.", "O último comando não leva ';'."
        if "encontrou ';'" in msg and antes.rstrip().endswith(";"):
            return "Tem ';' repetido.", "Use um só ';' entre dois comandos."
        if "encontrou '.'" in msg and antes.rstrip().endswith("<-"):
            return "O plano está sem comandos depois do '<-'.", "Escreva pelo menos um comando, ex.: dancar."
        return "O robô esperava um comando aqui.", "Comandos: pegar_casquinha(medio), adicionar_sorvete(creme)..."
    if "esperava uma crença ou um plano" in msg:
        if "encontrou 'modelo'" in msg or "encontrou 'agente'" in msg:
            return ("Não precisa escrever 'modelo' ou 'agente' aqui.",
                    "Cada janela já é o programa dos robôs que ela controla: escreva só os planos.")
        return ("Cada plano começa com +!objetivo ou -!objetivo (ou +evento).",
                "Talvez faltou o '+' no começo, ou o '.' no plano de cima.")
    if "esperava ')'" in msg:
        return "Faltou fechar o parêntese ')'.", "Ex.: pegar_casquinha(medio)"
    if "caractere inválido" in msg:
        c = re.search(r"'(.)'", msg)
        return (f"O caractere {c.group(0) if c else ''} não existe na linguagem.",
                "Use letras sem acento nos nomes (ex.: dancar, não dançar).")
    if msg.startswith("ação desconhecida"):
        nome = re.search(r"'([^']+)'", msg).group(1)
        sug = re.search(r"quis dizer '([^']+)'", msg)
        return (f"O comando '{nome}' não existe.",
                f"Você quis dizer '{sug.group(1)}'?" if sug else "Veja os comandos com F1.")
    m = re.match(r"'(\w+)' espera (\d+) argumento\(s\), recebeu (\d+)", msg)
    if m:
        nome, n, recebeu = m.group(1), int(m.group(2)), int(m.group(3))
        if n == 0:
            return f"'{nome}' não leva parênteses nem valores.", f"Escreva só {nome}"
        return (f"'{nome}' precisa de {n} valor(es) entre parênteses (você passou {recebeu}).",
                {"pegar_casquinha": "Ex.: pegar_casquinha", "adicionar_sorvete": "Ex.: adicionar_sorvete(creme)",
                 "bater": "Ex.: bater(medio)"}.get(nome, "Veja F1."))
    m = re.match(r"variável '(\w+)' usada .* sem estar ligada", msg)
    if m:
        v = m.group(1)
        if v.lower() in OPCOES:
            return (f"'{v}' começa com maiúscula, então é uma VARIÁVEL.",
                    f"Para a opção, escreva tudo minúsculo: {v.lower()}")
        return (f"A variável '{v}' não recebeu valor antes de ser usada.",
                "Ela precisa aparecer no evento ou numa condição antes (ex.: pedido_sabor(S)).")
    m = re.match(r"alvo '(\w+)' em '(\w+)'", msg)
    if m:
        v, acao = m.group(1), m.group(2)
        sug = difflib.get_close_matches(v, OPCOES, n=1, cutoff=0.6)
        return (f"'{v}' não é uma opção que o robô conheça (em {acao}).",
                f"Você quis dizer '{sug[0]}'?" if sug else "Veja as opções com F1.")
    m = re.match(r"o objetivo '!(\w+)' não tem nenhum plano", msg)
    if m:
        sug = re.search(r"quis dizer '!([^']+)'", msg)
        return (f"Não existe plano para o objetivo !{m.group(1)}.",
                f"Você quis dizer !{sug.group(1)}?" if sug else f"Crie um plano: +!{m.group(1)} <- ...")
    if "nunca será gerado" in msg:
        nome = re.search(r"'([+-]\w+)", msg)
        return (f"O evento {nome.group(1) if nome else ''} nunca vai acontecer.",
                "Esse nome não é percebido pelo robô: confira a escrita (F1).")
    if "aparece uma só vez" in msg:
        v = re.search(r"'(\w+)'", msg).group(1)
        return f"A variável {v} foi usada uma vez só.", f"Se não precisa dela, escreva _{v}."
    if "ainda bloqueado" in msg:
        m = re.match(r"a variável '(\w+)'", msg)
        if m and m.group(1).lower() in OPCOES:
            return (f"'{m.group(1)}' começa com maiúscula, então é uma VARIÁVEL.",
                    f"Para a opção, escreva tudo minúsculo: {m.group(1).lower()}")
        return msg[0].upper() + msg[1:], "Abra a Árvore (T) para ver o preço."
    if "sem fechar" in msg or "não fechado" in msg:
        return "Faltou fechar as aspas do texto.", 'Ex.: imprimir("oi")'
    return msg, ""
