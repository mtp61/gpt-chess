import threading
import random

import berserk
import chess


def board_str_unicode(board: chess.Board):
    builder = []
    for square in chess.SQUARES_180:
        piece = board.piece_at(square)

        if piece:
            builder.append(piece.unicode_symbol())
        else:
            builder.append(".")

        if chess.BB_SQUARES[square] & chess.BB_FILE_H:
            if square != chess.H1:
                builder.append("\n")
        else:
            builder.append(" ")

    return "".join(builder)


class Game(threading.Thread):
    def __init__(self, client, event, **kwargs):
        super().__init__(**kwargs)
        self.game_id = event['game']['gameId']
        self.board = chess.Board(event['game']['fen'])
        self.color = chess.WHITE if event['game']['color'] == 'white' else chess.BLACK
        self.opponent_id = event['game']['opponent']['id']

        self.client = client
        self.stream = client.bots.stream_game_state(self.game_id)

        color = event['game']['color']
        self.log(f'Starting game against {self.opponent_id} playing with color {color}')
        self.make_move()

    def run(self):
        for event in self.stream:
            if event['type'] == 'gameState':
                if event['status'] != 'started':
                    status = event['status']
                    winner = event['winner']
                    self.log(f'Game over with status={status}, winner={winner}\n')
                    return

                self.handle_state_change(event)
            elif event['type'] == 'chatLine':
                self.handle_chat_line(event)

    def handle_state_change(self, event):
        move = event['moves'].split(' ')[-1]
        self.board.push_san(move)

        to_move = 'gpt-chess' if self.color == self.board.turn else 'Opponent'
        self.log(f'{to_move} to move in position,\n{board_str_unicode(self.board)}\n')
        # TODO: display board in color

        self.make_move()

    def handle_chat_line(self, event):
        pass  # TODO

    def make_move(self):
        if self.color != self.board.turn:
            return

        # TODO: get move from model

        move = random.choice(list(self.board.legal_moves))
        client.bots.make_move(self.game_id, move)

        self.log(f'Made random move {move.uci()}\n')

    def log(self, message):
        print(f'Game {self.game_id}: {message}')


if __name__ == '__main__':
    # setup client
    with open('./lichess.token') as f:
        token = f.read().strip()

    session = berserk.TokenSession(token)
    client = berserk.Client(session)

    # handle events
    for event in client.bots.stream_incoming_events():
        print(f'Client Event: {event}\n')

        if event['type'] == 'challenge':
            if event['challenge']['challenger']['id'] == 'mtpink':  # TODO: accept all challenges
                client.bots.accept_challenge(event['challenge']['id'])
        elif event['type'] == 'gameStart':
            game = Game(client, event)
            game.start()
