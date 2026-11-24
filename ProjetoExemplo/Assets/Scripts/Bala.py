from engine2d import Componente


class Bala(Componente):
    """Vai no prefab da bala. Ao encostar num inimigo, avisa o agente da DSL e some."""

    CAMPOS = {"dano": "int"}
    dano = 1

    def ao_entrar_colisao(self, outro):
        objeto = outro.gameobject
        if objeto.tag != "inimigo":
            return
        agente = objeto.obter("ComportamentoAgente")
        if agente is not None:
            # Gera o evento +atingido(D) no agente do inimigo (o .agt decide o que acontece)
            agente.pulsar("atingido", (self.dano,))
        self.gameobject.destruir()
