import json
move = input("> ")
with open("honse_moves.json", "r") as f:
    moves = json.load(f)
    print(moves[move])
