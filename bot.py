import threading
import random
import os
import json

from dotenv import load_dotenv
import berserk
import chess
import openai


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


def request_log_append(log_item):
    with open('./request_log.json', 'r') as f:
        log = json.load(f)
    log.append(log_item)
    with open('./request_log.json', 'w') as f:
        json.dump(log, f)


def get_random_move(board: chess.Board) -> chess.Move:
    return random.choice(list(board.legal_moves))


def get_model_move(board: chess.Board) -> chess.Move:
    openai.api_key = os.getenv('OPENAI_API_KEY')

    move_history = [m.uci() for m in board.move_stack]
    legal_moves = [m.uci() for m in board.legal_moves]
    prompt = 'You are a chess engine. Given move history:\n' + \
        ', '.join(move_history) + '\n' + \
        'And possible moves:\n' + \
        ', '.join(legal_moves) + '\n' + \
        'Output the move that maximizes the probability of winning.'

    completion_params = {
        'engine': 'text-davinci-003',
        'prompt': prompt,
        'temperature': 0.7,
        'max_tokens': 64,
        'top_p': 1.0,
        'frequency_penalty': 0.0,
        'presence_penalty': 0.0,
    }
    response = openai.Completion.create(**completion_params)
    response_text = response['choices'][0]['text'].lower()
    response_moves = [m for m in legal_moves if m in response_text]

    request_log_append({
        'completion_params': completion_params,
        'response': response,
        'response_moves': response_moves,
    })

    print(response_moves)  # TODO

    if len(response_moves) == 0:
        move = get_random_move(board)
        print(f'Response contained no moves, made random move {move}')
    elif len(response_moves) == 1:
        move = chess.Move.from_uci(response_moves[0])
        print(f'Response contained exactly one move {move}')
    else:
        move = chess.Move.from_uci(random.choice(response_moves))
        print(f'Response contained moves {response_moves}, randomly chose move {move}')

    return move


class Game(threading.Thread):
    def __init__(self, client, event, **kwargs):
        super().__init__(**kwargs)
        self.game_id = event['game']['gameId']
        self.color = chess.WHITE if event['game']['color'] == 'white' else chess.BLACK
        self.opponent_id = event['game']['opponent']['id']

        self.client = client
        self.stream = client.bots.stream_game_state(self.game_id)

        color = event['game']['color']
        self.log(f'Starting game against {self.opponent_id} playing with color {color}')
        self.make_move(chess.Board(event['game']['fen']))

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
        board = chess.Board()
        for move in event['moves'].split(' '):
            board.push_san(move)

        to_move = 'gpt-chess' if self.color == board.turn else 'Opponent'
        self.log(f'{to_move} to move in position,\n{board_str_unicode(board)}\n')
        self.make_move(board)

    def handle_chat_line(self, event):
        pass

    def make_move(self, board: chess.Board):
        if self.color != board.turn:
            return

        # move = get_random_move(board)
        move = get_model_move(board)
        client.bots.make_move(self.game_id, move.uci())

        self.log(f'Made move {move.uci()}\n')

    def log(self, message):
        print(f'Game {self.game_id}: {message}')


if __name__ == '__main__':
    load_dotenv()
    session = berserk.TokenSession(os.getenv('LICHESS_TOKEN'))
    client = berserk.Client(session)

    # handle events
    for event in client.bots.stream_incoming_events():
        print(f'Client Event: {event}\n')

        if event['type'] == 'challenge':
            # TODO: accept all challenges
            challenge_id = event['challenge']['id']
            challenger_id = event['challenge']['challenger']['id']
            if challenger_id == 'mtpink':
                client.bots.accept_challenge(challenge_id)
            else:
                client.bots.decline_challenge(challenge_id)
        elif event['type'] == 'gameStart':
            game = Game(client, event)
            game.start()
