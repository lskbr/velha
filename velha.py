import asyncio
import time
import random
import os
import telepot
import telepot.aio
import logging
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton

"""
Velha - Bot para o telegram

Requer Python 3.6 ou superior!
"""

logger = logging.getLogger(__name__)


def posicoes_de(fonte, caracter):
    """Retorna os índices onde caracter ocorre na string fonte"""
    return [i for i, c in enumerate(fonte) if c == caracter]


class Velhus:
    """
    Classe que simula a grelha e permite calcular as jogas possíveis.
    Utilizada para calcular a jogada do computador.

    O Estado contém a grelha como uma lista de strings.
    Espaço significa que a posição está livre.
    X ou O que o jogador já marcou esta posição.

    Grelha
    Índices   Posições
     0 1 2     1 | 2 | 3
              ---+---+---
     3 4 5     4 | 5 | 6
              ---+---+---
     6 7 8     7 | 8 | 9
    """
    GANHANTES = [set(x) for x in [(0, 1, 2), (3, 4, 5), (6, 7, 8),
                                  (0, 4, 8), (6, 4, 2),
                                  (0, 3, 6), (1, 4, 7), (2, 5, 8)]]

    def __init__(self, estado=None):
        """estado: estado inicial. Default: branco"""
        self.estado = estado or [" "] * 9

    def jogadas_possiveis(self):
        """Onde podemos jogar?"""
        return posicoes_de(self.estado, " ")

    def posicoes_por_jogador(self):
        """Retorna uma tupla com as posições do jogador X e do jogador O"""
        return (posicoes_de(self.estado, "X"), posicoes_de(self.estado, "O"))

    def ganhou(self, posicoes, jogador):
        """Verifica se um dos jogadores ganhou a partida"""
        s = set(posicoes)
        for p in Velhus.GANHANTES:
            if len(p - s) == 0:
                return True
        return False

    def joga(self, posicao, jogador):
        """Joga pelo jogador em um posição específica"""
        if self.estado[posicao] == " ":
            self.estado[posicao] = jogador
        else:
            raise ValueError(f"Posição({posicao}) inválida.")

    def resultado(self):
        jX, jO = self.posicoes_por_jogador()
        if self.ganhou(jX, "X"):
            return("X")   # X Ganhou
        elif self.ganhou(jO, "O"):
            return("O")   # O Ganhou
        elif not self.jogadas_possiveis():
            return("*")   # Empate sem resultado
        else:
            return("?")   # Inconclusivo

    @staticmethod
    def alterna(jogador):
        """Inverte o jogodor atual. X --> O e O --> X"""
        return "X" if jogador == "O" else "O"

    @staticmethod
    def melhor(result, jogador):
        if jogador == "X":
            return max(result.values())
        else:
            return min(result.values())

    def proxima(self, jogador, estado, nivel=0, nmax=3):
        """Cria um dicionário que calcula as possibilidades de futuras jogadas.
           jogador: jogador corrente (da vez)
           estado: estado do jogo (grelha)
           nivel: nivel atual de recursão, usado para diminuir a dificuldade do jogo
           nmax: nível máximo de exploração. Retorna caso o nível atual atinja o máximo.
           result: dicionário com a pontuação por resultado.
        """
        result = {}
        # Percorre as jogadas possíveis
        for possivel in self.jogadas_possiveis():
            j = Velhus(estado[:])  # Cria um tabuleiro hipotético, a partir do estado atual.
            j.joga(possivel, jogador)  # joga pelo jogador
            resultado = j.resultado()  # verifica o resultado da jogada

            if resultado == "X" or resultado == "O":
                rlocal = 10 - nivel    # Atribui pontos com base no nível atual
                result[possivel] = rlocal if resultado == "X" else -rlocal
            elif resultado == "?" and nivel < nmax:  # Como o resultado não é final, continua a jogar
                outro = self.alterna(jogador)
                lresult = j.proxima(outro, j.estado, nivel + 1, nmax)
                result[possivel] = self.melhor(lresult, outro) if lresult else 0
        return result

    @classmethod
    def dump_estado(cls, estado):
        """Ajuda a debugar, imprime o estado do jogo"""
        dump = "\n"
        for x, e in enumerate(estado):
            if e == " ":
                e = "_"
            dump += f"{e} "
            if x in [2, 5, 8]:
                dump += "\n"
        return dump

    def melhor_jogada(self, jogador, estado, dmax):
        """
        Calcula qual a melhor jogada para o jogador
        jogador: jogador da vez (para qual a melhor jogada será calculada)
        estado: estado atual do jogo
        dmax: nível máximo de profundidade. Usado para diminuir a dificuldade.
        """
        result = self.proxima(jogador, estado, nmax=dmax)  # Quais são as possiblidades?
        melhores_jogadas = []
        melhor = self.melhor(result, jogador)

        logger.debug(Velhus.dump_estado(estado))
        logger.debug(f"Jogador={jogador}")

        for posicao, resultado in result.items():
            if resultado == melhor:   # Se esta posição tem o melhor score
                melhores_jogadas.append(posicao)
            logger.debug(f"Melhor: {melhor} {melhores_jogadas} r={resultado} posicao={posicao}")
        return melhores_jogadas


class Velha:
    """Controla o estado de cada jogador"""

    def __init__(self, user_id):
        """Cria uma nova partida pelo jogador, identificado pela user_id do telegram"""
        self.estado = [" "] * 9           # Estado do jogo
        self.ultima_jogada = time.time()  # Quando o jogador jogou pela última vez?
        self.mensagem = "Olá!"       # Mensgem retornada para o usuário
        self.tela = 0                # Estado do jogo (0 - Escolha do nível, 1 - Escolha de X ou O
                                     #                 2 - Jogando, 3 - Partida terminada)
        self.dificuldade = 0         # Nível de dificuldade
        self.jogador = "X"           # Jogador (humano)
        self.computador = "O"        # Jogador (computador)
        self.user_id = user_id       # user_id do Telegram
        self.message = None          # id da mensagem a alterar no telegram

    def joga(self, posicao, jogador):
        """Joga pelo jogador, marcando na grelha"""
        self.ultima_jogada = time.time()
        if self.estado[posicao] == " ":
            self.estado[posicao] = jogador
            self.mensagem = "OK"
            return True
        else:
            self.mensagem = "Você já jogou nesta posição, escolha outra"
            return False

    def constroi_grelha(self):
        """Retorna a grelha do jogo"""
        grelha = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=self.estado[0], callback_data='1'),
             InlineKeyboardButton(text=self.estado[1], callback_data='2'),
             InlineKeyboardButton(text=self.estado[2], callback_data='3')],
            [InlineKeyboardButton(text=self.estado[3], callback_data='4'),
             InlineKeyboardButton(text=self.estado[4], callback_data='5'),
             InlineKeyboardButton(text=self.estado[5], callback_data='6')],
            [InlineKeyboardButton(text=self.estado[6], callback_data='7'),
             InlineKeyboardButton(text=self.estado[7], callback_data='8'),
             InlineKeyboardButton(text=self.estado[8], callback_data='9')],
            [InlineKeyboardButton(text='Recomeçar', callback_data='recomecar')],
        ])
        return grelha

    def nivel_de_dificuldade(self):
        """Retorna as opções dos níveis de dificuldade do jogo"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Fácil", callback_data='facil')],
            [InlineKeyboardButton(text="Médio", callback_data='medio')],
            [InlineKeyboardButton(text="Difícil", callback_data='dificil')]])

    def tipo_jogador(self):
        """Retorna as opções de quem joga primeiro"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="X", callback_data='X')],
            [InlineKeyboardButton(text="O", callback_data='O')]])


class Partidas:
    """Mantém uma lista de partidas, indexadas pelo user_id"""

    TIMEOUT = 15 * 60  # 15 minutos

    def __init__(self):
        self.partidas = {}

    def pega_jogo(self, user_id):
        """Procura o jogo do usuário, criando um novo caso não encontre"""
        jogo = self.partidas.get(user_id)
        if not jogo:
            jogo = Velha(user_id)
            self.partidas[user_id] = jogo
        return jogo

    def __len__(self):
        """Número de partidas em memória"""
        return len(self.partidas)

    def apaga(self, user_id):
        """Remove uma partida do dicionário"""
        if user_id in self.partidas:
            del self.partidas[user_id]

    def novo_jogo(self, jogo):
        """Substitui o jogo atual por um novo"""
        message, user_id = jogo.message, jogo.user_id
        self.apaga(user_id)
        novo = self.pega_jogo(user_id)
        novo.message = message
        return novo

    def limpa_antigas(self):
        agora = time.time()
        a_remover = []
        for user, partida in self.partidas.items():
            if agora - partida.ultima_jogada > Partidas.TIMEOUT:
                a_remover.append(user)
        for user in a_remover:
            self.apaga(user)


class JogoDaVelha:
    """Classe controladora do Jogo"""

    def __init__(self, bot):
        """Recebe o bot e inicializa a lista de partidas ativas"""
        self.partidas = Partidas()
        self.bot = bot

    @staticmethod
    def msg_user_id(msg):
        """Extrai o user_id de uma mensagem"""
        return msg["from"]["id"]

    @staticmethod
    def msg_chat_id(msg):
        """Extrai o chat_id de uma mensagem"""
        return msg["message"]["chat"]["id"]

    def pega_jogo(self, msg):
        """Retorna o jogo atual para o usuário"""
        user_id = self.msg_user_id(msg)
        return self.partidas.pega_jogo(user_id)

    async def chat_handler(self, msg):
        """Processa o chat vindo do usuário"""
        content_type, chat_type, chat_id = telepot.glance(msg)
        logger.debug(f"Content_type: {content_type} Chat type: {chat_type} Messge: {msg}")

        jogo = self.pega_jogo(msg)
        await self.reply_markup(jogo, chat_id)

    async def reply_markup(self, jogo, chat_id=None):
        """Dependendo do estado atual do jogo, retorna as opções disponíveis"""
        if jogo.tela == 0:
            markup = jogo.nivel_de_dificuldade()
            mensagem = 'Jogo da Velha - Escolha o nível de dificuldade'
        elif jogo.tela == 1:
            markup = jogo.tipo_jogador()
            mensagem = 'X sempre joga primeiro. Você quer jogar como X ou O?'
        elif jogo.tela == 2:
            markup = jogo.constroi_grelha()
            mensagem = jogo.mensagem or 'Jogo da Velha'

        if jogo.message is None and chat_id is not None:
            message = await self.bot.sendMessage(chat_id, mensagem, reply_markup=markup)
            jogo.message = telepot.message_identifier(message)
        else:
            try:
                await self.bot.editMessageText(jogo.message, mensagem, reply_markup=markup)
            except telepot.exception.TelegramError as te:
                pass

    def configura_dificuldade(self, jogo, query_data):
        if query_data in ["facil", "medio", "dificil"]:
            if query_data == "facil":
                jogo.dificuldade = 1
            elif query_data == "medio":
                jogo.dificuldade = 2
            elif query_data == "dificil":
                jogo.dificuldade = 3
            jogo.tela = 1

    def configura_primeiro_jogador(self, jogo, query_data):
        if query_data in ["X", "O"]:
            jogo.jogador = query_data
            jogo.computador = "X" if query_data == "O" else "O"
            jogo.tela = 2

    def verifica_resultado(self, jogo, computador=False):
        velha = Velhus(jogo.estado)
        resultado = velha.resultado()
        logger.debug(f"RESULTADO: {resultado} Jogador: {jogo.user_id} Estado do jogo: {jogo.tela}")
        if resultado == "?":  # Partida ainda não acabou, continua a jogar
            if not computador:  # Vez do computador
                self.joga_pelo_computador(jogo, velha)
            return False
        elif resultado == "*":
            jogo.mensagem = "Empate"
        elif resultado == jogo.jogador:
            jogo.mensagem = "Você ganhou!"
        else:
            jogo.mensagem = "Você perdeu!"
        jogo.tela = 3  # Termina o jogo
        return True

    def joga_pelo_computador(self, jogo, velha=None):
        if velha is None:
            velha = Velhus(jogo.estado)
        posicoes = velha.jogadas_possiveis()
        # A primeira jogada do computador sempre é aleatória (para impedir começar sempre no centro)
        if len(posicoes) == 9 or jogo.dificuldade == 1:
            posicao = random.choice(posicoes)  # O nível fácil é aleatório
        elif jogo.dificuldade == 2:
            # Escolhe a melhor jogada, usando minmax, mas limitando a profundidade de busca a 2 níveis
            posicao = random.choice(velha.melhor_jogada(jogo.computador, jogo.estado, 2))
        elif jogo.dificuldade == 3:
            # Escolhe a melhor jogada, usando minmax, mas limitando a profundidade de busca a 9 níveis (todos)
            posicao = random.choice(velha.melhor_jogada(jogo.computador, jogo.estado, 9))
        jogo.joga(posicao, jogo.computador)  # Marca a jogada do computador
        logger.debug(f"DIFICULDADE: {jogo.dificuldade} posição: {posicao} usuário: {jogo.user_id}")
        self.verifica_resultado(jogo, computador=True)

    def verifica_jogada(self, jogo):
        self.verifica_resultado(jogo, computador=False)

    async def callback_query(self, msg):
        """Processa a resposta para as escolhas do usuário"""
        query_id, from_id, query_data = telepot.glance(msg, flavor='callback_query')
        logger.debug(f'Callback Query: {query_id}, {from_id}, {query_data}')
        jogo = self.pega_jogo(msg)
        logger.debug(f"Callback query: usuário: {jogo.user_id} mensagem: {msg}")

        if jogo.tela == 0:
            self.configura_dificuldade(jogo, query_data)
            await self.reply_markup(jogo, self.msg_chat_id(msg))
        elif jogo.tela == 1:
            self.configura_primeiro_jogador(jogo, query_data)
            if jogo.computador == "X":
                self.joga_pelo_computador(jogo)
            await self.reply_markup(jogo, self.msg_chat_id(msg))
        elif query_data == "recomecar":
            jogo = self.partidas.novo_jogo(jogo)
            await self.reply_markup(jogo, self.msg_chat_id(msg))
        elif len(query_data) == 1 and query_data.isdigit() and jogo.tela == 2:
            posicao = int(query_data) - 1
            if jogo.joga(posicao, jogo.jogador):
                self.verifica_jogada(jogo)
                grelha = jogo.constroi_grelha()
                await self.bot.editMessageText(jogo.message, f"Velha: {jogo.mensagem}", reply_markup=grelha)
            else:
                await self.bot.answerCallbackQuery(query_id, text='Escolha outra posição')
        elif jogo.tela == 3:
            await self.bot.answerCallbackQuery(query_id, text='Partida terminada. Escolha recomeçar para jogar de novo')

    async def stats(self, loop):
        """Imprime estatísticas e limpa jogos antigos"""
        while True:
            partidas = len(self.partidas)
            logger.info(f"Partidas em memória: {partidas}")
            self.partidas.limpa_antigas()
            await asyncio.sleep(60, loop=loop)


# Pega o token da variável de ambiente BOT_TOKEN
TOKEN = os.getenv("BOT_TOKEN")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(levelname)6s %(filename)s %(funcName)s:%(lineno)d %(message)s')
    loop = asyncio.get_event_loop()
    bot = telepot.aio.Bot(TOKEN, loop=loop)  # Cria o bot
    jogo = JogoDaVelha(bot)                  # Cria o jogo
    loop.create_task(jogo.stats(loop))       # Cria a tarefa que limpa as partidas velhas
    loop.create_task(bot.message_loop({'chat': jogo.chat_handler,
                                       'callback_query': jogo.callback_query}))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

