from collections import defaultdict
import pygame
pygame.init()
pygame.font.init()

import random
import math
import honse_data
import honse_pokemon
import honse_particles
import sys
import json 
import numpy as np
import base64
from PIL import Image
from io import BytesIO
import cProfile



class HonseGame:
    message_fonts = [
        pygame.font.Font('freesansbold.ttf', 24),
        pygame.font.Font('freesansbold.ttf', 16)
        ]
    message_y_offset = 5
    message_x_offset = 10
    def __init__(self, json_path, width=1920, height=1080, fps=60):
        self.SCREEN_WIDTH = width
        self.SCREEN_HEIGHT = height
        self.FRAMES_PER_SECOND = fps
        self.screen = pygame.display.set_mode((honse_data.SCREEN_WIDTH, honse_data.SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True
        self.dt = 0
        self.frame_count = 0
        self.characters = []
        self.json_path = json_path
        self.particle_spawner = honse_particles.ParticleSpawner(self)
        self.temporary_particle_spawners = []
        self.cell_size = 30
        self.wall_grid = defaultdict(list)
        self.load_map()
        # message lists for rendering purposes
        self.current_frame_messages = []
        self.all_frame_messages = []
        # message log for other purposes
        self.message_log = []

    def scale_to_fps(self, value):
        return value * 60 / self.FRAMES_PER_SECOND

    def add_character(self, name, team, level, stats, moves, types, image):
        number_of_teammates = len([i for i in self.characters if i.team == team])
        character = honse_pokemon.Character(self, name, team, level, stats, moves, types, image, number_of_teammates)
        self.characters.append(character)

    def display_message(self, text, font_index, rgb):
        self.current_frame_messages.append([text, font_index, rgb])

    def render_all_messages(self):
        # this is where the next text box should be drawn
        y_next_text_box_location = self.SCREEN_HEIGHT
        if len(self.current_frame_messages):
            reversed_copy = [msg for msg in self.current_frame_messages]
            reversed_copy.reverse()
            self.current_frame_messages = []
            self.all_frame_messages = [reversed_copy] + self.all_frame_messages
        frames_since_most_recent_frame = 0
        for frame_of_messages in self.all_frame_messages:
            for message_data in frame_of_messages:
                message = message_data[0]
                font_index = message_data[1]
                font = self.message_fonts[font_index]
                r = message_data[2][0]
                g = message_data[2][1]
                b = message_data[2][2]
                if frames_since_most_recent_frame == 0:
                    a = 255
                else:
                    a = max(127, (192 - 16*frames_since_most_recent_frame))
                color = pygame.Color(r, g, b)
                text = font.render(message, False, color)
                text.set_alpha(a)
                text_rect = text.get_rect()
                y_next_text_box_location -= (self.message_y_offset + text_rect.height)
                if y_next_text_box_location < 0:
                    return
                text_rect.y = y_next_text_box_location
                y_next_text_box_location -= self.message_y_offset
                text_rect.x = int(self.SCREEN_WIDTH * 0.75) + self.message_x_offset
                self.screen.blit(text, text_rect)
            frames_since_most_recent_frame += 1
    # Lina functions start here
    def grid_coord(self, x, y):
        return int(x) // self.cell_size, int(y) // self.cell_size

    def cells_wall_crosses(self, x1, y1, x2, y2):
        cells = set()
        steps = int(max(abs(x2-x1), abs(y2-y1)) / self.cell_size) + 1
        for i in range(steps+1):
            t = i / steps
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            cells.add(self.grid_coord(x,y))
        return cells

    def load_map(self, scale=1.0):
        with open(self.json_path, "r") as f:
            data = json.load(f)
        bg_img_data = base64.b64decode(data["image"])
        image = Image.open(BytesIO(bg_img_data))
        if scale != 1.0:
            new_size = (int(image.width * scale), int(image.height * scale))
            image = image.resize(new_size, Image.ANTIALIAS)
        self.background = pygame.image.fromstring(image.tobytes(), image.size, image.mode)
        self.walls = [
            {
                "x1": int(wall["x1"] * scale),
                "y1": int(wall["y1"] * scale),
                "x2": int(wall["x2"] * scale),
                "y2": int(wall["y2"] * scale),
                "nx": wall["nx"],
                "ny": wall["ny"],
            }
            for wall in data["walls"]]
        self.areas = [
            {
                "x1": int(area["x1"] * scale),
                "y1": int(area["y1"] * scale),
                "x2": int(area["x2"] * scale),
                "y2": int(area["y2"] * scale),
            }
            for area in data["areas"]]
        for wall in self.walls:
            x1, y1 = wall["x1"], wall["y1"]
            x2, y2 = wall["x2"], wall["y2"]
            cells = self.cells_wall_crosses(x1, y1, x2, y2)
            for cell in cells:
                self.wall_grid[cell].append(wall)

    def spawn_in_area(self, area_index):
        x = random.randint(self.areas[area_index]["x1"], self.areas[area_index]["x2"])
        y = random.randint(self.areas[area_index]["y1"], self.areas[area_index]["y2"])
        return [x, y]
    # Lina functions end here

    def main_loop(self):
        while self.running:
            self.frame_count += 1
            # poll for events
            # pygame.QUIT event means the user clicked X to close your window
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    sys.exit()

            # fill the screen with a color to wipe away anything from last frame
            self.screen.fill("white")
            self.screen.blit(self.background, (0,0))

            self.particle_spawner.emit()
            for spawner in self.temporary_particle_spawners:
                spawner.emit()

            # update ui
            for character in self.characters:
                character.ui_element.display()

            # sort by speed
            tangible_characters = filter(lambda c: not c.is_intangible(), self.characters)
            tangible_characters = sorted(tangible_characters, key=lambda x: x.get_speed(), reverse=True)
            for character in tangible_characters:
                for other_character in tangible_characters:
                    if other_character is character:
                        continue
                    if character.is_colliding(other_character):
                        character.use_move(other_character)
                        character.resolve_collision(other_character)
    
            # update loop
            for character in self.characters:
                character.update()

            # move loop
            for character in self.characters:
                character.move()

            # draw loop
            # fainted characters should appear below other characters. Draw them first
            for character in sorted(self.characters, key=lambda x: 0 if x.is_fainted() else 1):
                character.draw()

            self.render_all_messages()

            pygame.display.flip()

            self.clock.tick(self.FRAMES_PER_SECOND)
            if self.frame_count % honse_data.FRAMES_PER_SECOND == 0:
                print(self.clock.get_fps())   
'''
characters = [
    honse_pokemon.Character("Saurbot", 350, 250, 1, 100, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")
]

ui_elements = [
    honse_data.UIElement(0, honse_data.SCREEN_HEIGHT-135, characters[0]),
    honse_data.UIElement(360, honse_data.SCREEN_HEIGHT-135, characters[0]),
    honse_data.UIElement(720, honse_data.SCREEN_HEIGHT-135, characters[0]),
    honse_data.UIElement(1080, honse_data.SCREEN_HEIGHT-135, characters[0]),
    honse_data.UIElement(0, honse_data.SCREEN_HEIGHT-270, characters[0]),
    honse_data.UIElement(360, honse_data.SCREEN_HEIGHT-270, characters[0]),
    honse_data.UIElement(720, honse_data.SCREEN_HEIGHT-270, characters[0]),
    honse_data.UIElement(1080, honse_data.SCREEN_HEIGHT-270, characters[0])
]

characters = [
    honse_pokemon.Character("P1", 350, 250, 1, 1, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png"),
    honse_pokemon.Character("P2", 400, 250, 1, 1, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png"),
    honse_pokemon.Character("P3", 450, 250, 1, 1, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png"),
    honse_pokemon.Character("P4", 500, 250, 1, 1, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png"),
    honse_pokemon.Character("P1", 350, 325, 1, 1, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png"),
    honse_pokemon.Character("P2", 400, 325, 1, 1, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png"),
    honse_pokemon.Character("P3", 450, 325, 1, 1, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png"),
    honse_pokemon.Character("P4", 500, 325, 1, 1, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")]

moves = {
}
'''
game = HonseGame("map02.json")
game.add_character(
    "Saurbot", 0, 100,
    {"HP": 77, "ATK": 5, "DEF": 107, "SPA": 5, "SPD": 104, "SPE": 20},
    [honse_pokemon.moves["Tackle"]],
    [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")
game.add_character(
    "Saur", 0, 100,
    {"HP": 114, "ATK": 44, "DEF": 104, "SPA": 95, "SPD": 138, "SPE": 55},
    [honse_pokemon.moves["Tackle"]],
    [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Poison"]], "saur.png")
game.add_character(
    "Apollo", 0, 100,
    {"HP": 88, "ATK": 119, "DEF": 103, "SPA": 117, "SPD": 101, "SPE": 94},
    [honse_pokemon.moves["Tackle"]],
    [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Ghost"]], "apollo.png")
game.add_character(
    "Dragonite", 0, 100,
    {"HP": 91, "ATK": 134, "DEF": 95, "SPA": 100, "SPD": 100, "SPE": 80},
    [honse_pokemon.moves["Tackle"]],
    [honse_pokemon.pokemon_types["Dragon"], honse_pokemon.pokemon_types["Flying"]], "dragonite.png")
game.add_character(
    "Alakazam", 1, 100,
    {"HP": 55, "ATK": 50, "DEF": 45, "SPA": 135, "SPD": 95, "SPE": 120},
    [honse_pokemon.moves["Tackle"]],
    [honse_pokemon.pokemon_types["Psychic"]], "alakazam.png")
game.add_character(
    "Warwolf", 1, 100,
    {"HP": 106, "ATK": 116, "DEF": 69, "SPA": 46, "SPD": 87, "SPE": 96},
    [honse_pokemon.moves["Tackle"]],
    [honse_pokemon.pokemon_types["Ice"], honse_pokemon.pokemon_types["Dark"]], "warwolf.png")
game.add_character(
    "Sudowoodo", 1, 100,
    {"HP": 80, "ATK": 115, "DEF": 125, "SPA": 30, "SPD": 65, "SPE": 55},
    [honse_pokemon.moves["Tackle"]],
    [honse_pokemon.pokemon_types["Rock"]], "sudowoodo.png")
game.add_character(
    "Croconaw", 1, 100,
    {"HP": 75, "ATK": 90, "DEF": 85, "SPA": 59, "SPD": 68, "SPE": 68},
    [honse_pokemon.moves["Tackle"]],
    [honse_pokemon.pokemon_types["Water"]], "croconaw.png")
cProfile.run("game.main_loop()", sort="cumtime")
pygame.quit()