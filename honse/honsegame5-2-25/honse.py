import pygame
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

pygame.init()

class HonseGame:
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
        self.load_map()
        self.particle_spawner = honse_particles.ParticleSpawner(self)
        self.temporary_particle_spawners = []

    def scale_to_fps(self, value):
        return value * 60 / self.FRAMES_PER_SECOND

    def add_character(self, name, team, level, stats, moves, types, image):
        number_of_teammates = len([i for i in self.characters if i.team == team])
        character = honse_pokemon.Character(self, name, team, level, stats, moves, types, image, number_of_teammates)
        self.characters.append(character)

    # Lina functions start here
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
            for wall in data["walls"]
        ]
        self.areas = [
            {
                "x1": int(area["x1"] * scale),
                "y1": int(area["y1"] * scale),
                "x2": int(area["x2"] * scale),
                "y2": int(area["y2"] * scale),
            }
            for area in data["areas"]
        ]

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
            self.screen.fill("purple")
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
                        print("BONK")
                        honse_particles.basic_collision(character.position, self)
                        character.intangibility = honse_data.COLLISION_INTANGIBILITY
                        character.attack(other_character)
                        character.resolve_collision(other_character)
    
            # update loop
            for character in self.characters:
                character.update()

            # move loop
            for character in self.characters:
                character.move()

            # draw loop
            for character in self.characters:
                character.draw()

            pygame.display.flip()

            self.clock.tick(honse_data.FRAMES_PER_SECOND)
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
game = HonseGame("map01_epsilon7.json")
game.add_character("Saurbot1", 0, 100, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")
game.add_character("Saurbot2", 0, 100, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")
game.add_character("Saurbot3", 0, 100, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")
game.add_character("Saurbot4", 0, 100, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")
game.add_character("Saurbot5", 1, 100, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")
game.add_character("Saurbot6", 1, 100, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")
game.add_character("Saurbot7", 1, 100, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")
game.add_character("Saurbot8", 1, 100, honse_pokemon.stats, [], [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]], "bob.png")
game.main_loop()

pygame.quit()