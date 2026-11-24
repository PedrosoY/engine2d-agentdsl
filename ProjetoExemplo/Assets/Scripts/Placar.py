from engine2d import Componente, TextoUI


class Placar(Componente):
    """Mostra pontos e vida do jogador num TextoUI do mesmo objeto."""

    CAMPOS = {"nome_do_jogador": "str"}
    nome_do_jogador = "jogador"

    def iniciar(self):
        self.texto = self.obter(TextoUI)
        self.aviso = ""
        self.tempo_aviso = 0.0

    def atualizar(self, dt):
        jogador = self.cena.encontrar(self.nome_do_jogador)   # procura o objeto pelo nome
        if jogador is None or self.texto is None:
            return
        j = jogador.obter("Jogador")
        moedas = len(self.cena.com_tag("moeda"))
        self.texto.texto = f"Pontos: {j.pontos}    Vida: {j.vida}    Moedas restantes: {moedas}"
        self.tempo_aviso = max(0.0, self.tempo_aviso - dt)

    def avisar(self, mensagem):
        self.aviso = mensagem
        self.tempo_aviso = 2.5

    def desenhar_ui(self, ui):
        if self.tempo_aviso > 0:
            ui.texto(ui.largura / 2, 90, self.aviso, 30, cor=(255, 210, 80), ancora="center", negrito=True)
