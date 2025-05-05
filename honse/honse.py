from collections import defaultdict
import queue
import pygame

pygame.init()
pygame.font.init()
pygame.mixer.init()
import random
import math
import honse_data
import honse_pokemon
import honse_particles
import sys
import json
import numpy as np
import base64
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import cProfile
import functools
import os
import subprocess
import numpy as np


class HonseGame:
    def __init__(
        self,
        json_path,
        background,
        music,
        pygame_mode,
        video_mode,
        width=1920,
        fps=60,
    ):
        self.pygame_mode = pygame_mode
        self.video_mode = video_mode
        self.game_end_timer = 300
        self.game_end = False
        self.SCREEN_WIDTH = width
        self.SCREEN_HEIGHT = int(width * 9/16)
        self.FRAMES_PER_SECOND = fps
        if self.pygame_mode:
            self.screen = pygame.display.set_mode((self.SCREEN_WIDTH , self.SCREEN_HEIGHT))
        else:
            self.screen = pygame.display.set_mode((self.SCREEN_WIDTH , self.SCREEN_HEIGHT), flags=pygame.HIDDEN)
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
        # message lists for rendering purposes
        self.current_frame_messages = []
        self.all_frame_messages = []
        # message log for other purposes
        self.message_log = []
        self.background = background
        self.current_frame_image = None
        self.current_frame_draw = None
        self.video_out_path = "output.mp4"
        self.draw_every_nth_frame = 1
        self.music = music
        self.width_ratio = self.SCREEN_WIDTH / 1920
        self.load_map()
        self.create_sounds()
        self.play_music()
        self.font_setup()

    def times_width_ratio(self, value):
        # is it faster to do it this way? idk!!!!
        # does it matter? i also dont know!!!!!!
        return value if self.width_ratio == 1 else int(max(1, value*self.width_ratio))

    def font_setup(self):
        # [pygame font, PIL font, height of font in pixels]
        self.message_fonts = {
            16: [
                pygame.font.Font(honse_data.FONT_NAME, self.times_width_ratio(16)),
                ImageFont.truetype(honse_data.FONT_NAME, self.times_width_ratio(16)),
            ],
            24: [
                pygame.font.Font(honse_data.FONT_NAME, self.times_width_ratio(24)),
                ImageFont.truetype(honse_data.FONT_NAME, self.times_width_ratio(24)),
            ],
            28: [
                pygame.font.Font(honse_data.FONT_NAME, self.times_width_ratio(28)),
                ImageFont.truetype(honse_data.FONT_NAME, self.times_width_ratio(28)),
            ],
            48: [
                pygame.font.Font(honse_data.FONT_NAME, self.times_width_ratio(48)),
                ImageFont.truetype(honse_data.FONT_NAME, self.times_width_ratio(48)),
            ],
        }
        for value in self.message_fonts.values():
            value.append(value[0].get_ascent() - value[0].get_descent())
        self.message_y_offset = 5
        self.message_x_offset = 10

    def play_music(self):
        if self.pygame_mode:
            pygame.mixer.music.load(os.path.join("music", self.music))
            pygame.mixer.music.play(0)
        if self.video_mode:
            pass
            # i'll get to you

    def create_sounds(self):
        files = os.listdir("sfx")
        self.sounds = {}
        for file in files:
            if file.endswith(".mp3"):
                no_file_extension = file.removesuffix(".mp3")
                file_path = os.path.join("sfx", file)
                self.sounds[no_file_extension] = [
                    file_path,
                    pygame.mixer.Sound(file_path)
                    ]

    def play_sound(self, sound, repeat=0):
        if self.pygame_mode:
            self.sounds[sound][1].play(repeat)
        if self.video_mode:
            pass
            # i'll get to this later

    def save_into_ffmpeg(self, frame):
        # frame.show()
        # exit()
        frame_data = frame.tobytes()
        try:
            self.video_writer.stdin.write(frame_data)
        except BrokenPipeError:
            print("Broken pipe error: FFmpeg process may have terminated.")
        except Exception as e:
            print(f"Error writing to FFmpeg stdin: {e}")

    def first_draw(self):
        if self.video_mode:
            image = Image.new(
                mode="RGBA",
                size=(self.SCREEN_WIDTH, self.SCREEN_HEIGHT),
                color=(255, 255, 255, 255),
            )
            image.paste(self.background_image, (0, 0))
            draw = ImageDraw.Draw(image, "RGBA")
            for character in self.characters:
                character.ui_element.first_draw(draw)
            self.background_image = image
            self.video_writer = subprocess.Popen(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "rawvideo",
                    "-vcodec",
                    "rawvideo",
                    "-pix_fmt",
                    "rgba",
                    "-s",
                    f"{self.SCREEN_WIDTH}x{self.SCREEN_HEIGHT}",
                    "-r",
                    str(self.FRAMES_PER_SECOND / self.draw_every_nth_frame), #TODO: render at double speed, may want to change later
                    "-i",
                    "-",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "30",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-loglevel",
                    "warning",
                    "-tune",
                    "zerolatency",
                    "-threads",
                    "2",
                    self.video_out_path,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            self.current_frame_image = Image.new(
                "RGBA", (self.SCREEN_WIDTH, self.SCREEN_HEIGHT)
            )
            self.current_frame_draw = ImageDraw.Draw(self.current_frame_image)

    def show_display(self):
        if self.pygame_mode:
            pygame.display.flip()
        if self.video_mode and self.current_frame_image is not None:
            self.save_into_ffmpeg(self.current_frame_image)

    def draw_background(self):
        if self.pygame_mode:
            self.screen.fill("white")
            self.screen.blit(self.background_surface, (0, 0))
        if self.video_mode:
            self.current_frame_image.paste(self.background_image)

    def draw_circle(self, x, y, radius, rgba):
        x = self.times_width_ratio(x)
        y = self.times_width_ratio(y)
        radius = self.times_width_ratio(radius)
        if self.pygame_mode:
            color = pygame.Color(rgba[0], rgba[1], rgba[2], rgba[3])
            if rgba[3] != 255:
                circle_surface = pygame.Surface(
                    (radius * 2, radius * 2), pygame.SRCALPHA
                )
                pygame.draw.circle(circle_surface, color, (radius, radius), radius)
                self.screen.blit(circle_surface, (x - radius, y - radius))
            else:
                pygame.draw.circle(self.screen, color, (x, y), int(radius))
        if self.video_mode:
            self.current_frame_draw.ellipse(
                (x - radius, y - radius, x + (radius - 1), y + (radius - 1)), fill=rgba
            )

    # https://stackoverflow.com/questions/34747946/rotating-a-square-in-pil
    # answer by Sparkler
    def draw_rectangle(self, x_pos, y_pos, width, height, rotation, rgba):
        x_pos = self.times_width_ratio(x_pos)
        y_pos = self.times_width_ratio(y_pos)
        width = self.times_width_ratio(width)
        height = self.times_width_ratio(height)
        if self.pygame_mode:
            color = pygame.Color(rgba[0], rgba[1], rgba[2], rgba[3])
            if rotation % 360 != 0:
                surface = pygame.Surface((width, height), pygame.SRCALPHA)
                surface.fill(color)
                surface = pygame.transform.rotate(surface, rotation)
                rect = surface.get_rect(center=(x_pos, y_pos))
                self.screen.blit(surface, (rect.x, rect.y))
            else:
                if rgba[3] != 255:
                    rect_surface = pygame.Surface((width, height), pygame.SRCALPHA)
                    rect = pygame.Rect(0, 0, width, height)
                    pygame.draw.rect(rect_surface, color, rect)
                    self.screen.blit(rect_surface, (x_pos, y_pos))
                else:
                    rect = pygame.Rect(x_pos, y_pos, width, height)
                    pygame.draw.rect(self.screen, color, rect)
        if self.video_mode:
            if rotation % 360 == 0:
                verticies = [
                    (x_pos, y_pos),
                    (x_pos + width, y_pos),
                    (x_pos + width, y_pos + height),
                    (x_pos, y_pos + height),
                ]
            else:
                rotation_radians = np.radians(rotation)
                c, s = math.cos(rotation_radians), math.sin(rotation_radians)
                rectCoords = [
                    (width / 2.0, height / 2.0),
                    (width / 2.0, -height / 2.0),
                    (-width / 2.0, -height / 2.0),
                    (-width / 2.0, height / 2.0),
                ]
                verticies = [
                    (c * x - s * y + x_pos, s * x + c * y + y_pos)
                    for (x, y) in rectCoords
                ]
            self.current_frame_draw.polygon(verticies, fill=rgba)

    def draw_image(self, x, y, pygame_surface, pil_image):
        if self.pygame_mode:
            self.screen.blit(pygame_surface, (x, y))
        if self.video_mode:
            self.current_frame_image.paste(pil_image, (int(x), int(y)), pil_image)

    @functools.lru_cache(maxsize=512)
    def get_text_image(self, text, font_key, r, g, b, a):
        font = self.message_fonts[font_key][1]
        empty = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(empty)
        size = draw.textbbox((0, 0), text, font=font)
        width, height = size[2] - size[0], size[3] - size[1]
        img = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(img)
        draw.text((-size[0], -size[1]), text, (r, g, b, a), font=font)
        return img

    def draw_text(self, x, y, text, font_key, r, g, b, a):
        x = self.times_width_ratio(x)
        y = self.times_width_ratio(y)
        if self.pygame_mode:
            color = pygame.Color(r, g, b)
            text_surface = self.message_fonts[font_key][0].render(text, False, color)
            text_surface.set_alpha(a)
            self.screen.blit(text_surface, (x, y))
        if self.video_mode:
            img = self.get_text_image(text, font_key, r, g, b, a)
            self.current_frame_image.paste(img, (int(x), int(y)), img)

    def check_game_end(self):
        team1_alive = len(
            [
                character
                for character in self.characters
                if character.team == 0 and not character.is_fainted()
            ]
        )
        team2_alive = len(
            [
                character
                for character in self.characters
                if character.team == 1 and not character.is_fainted()
            ]
        )
        if not team1_alive and team2_alive:
            self.display_message("Team 2 wins!", 48, honse_data.TEAM_COLORS[1])
            self.game_end = True
        elif not team2_alive and team1_alive:
            self.display_message("Team 1 wins!", 48, honse_data.TEAM_COLORS[0])
            self.game_end = True
        elif not team2_alive and not team1_alive:
            self.display_message("Tie!", 48, [0, 0, 0])
            self.game_end = True

    def add_character(self, name, team, level, stats, moves, types, image):
        number_of_teammates = len([i for i in self.characters if i.team == team])
        character = honse_pokemon.Character(
            self, name, team, level, stats, moves, types, image, number_of_teammates
        )
        self.characters.append(character)

    def display_message(self, text, font_index, RGBA):
        self.current_frame_messages.append([text, font_index, RGBA])

    def render_all_messages(self):
        # this is where the next text box should be drawn
        y = honse_data.BASE_HEIGHT
        if len(self.current_frame_messages):
            reversed_copy = [msg for msg in self.current_frame_messages]
            reversed_copy.reverse()
            self.current_frame_messages = []
            self.all_frame_messages = [reversed_copy] + self.all_frame_messages
        frames_since_most_recent_frame = 0
        for frame_of_messages in self.all_frame_messages:
            for message_data in frame_of_messages:
                message = message_data[0]
                font_key = message_data[1]
                r = message_data[2][0]
                g = message_data[2][1]
                b = message_data[2][2]
                if frames_since_most_recent_frame == 0:
                    a = 255
                else:
                    a = max(127, (192 - 16 * frames_since_most_recent_frame))
                x = int(honse_data.BASE_WIDTH * 0.75) + self.message_x_offset
                y -= self.message_y_offset + self.message_fonts[font_key][2]
                if y < 0:
                    return
                self.draw_text(x, y, message, font_key, r, g, b, a)
                y -= self.message_y_offset
            frames_since_most_recent_frame += 1

    # Lina functions start here
    def grid_coord(self, x, y):
        return int(x) // self.cell_size, int(y) // self.cell_size

    def cells_wall_crosses(self, x1, y1, x2, y2):
        cells = set()
        steps = int(max(abs(x2 - x1), abs(y2 - y1)) / self.cell_size) + 1
        for i in range(steps + 1):
            t = i / steps
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            cells.add(self.grid_coord(x, y))
        return cells

    def load_map(self, scale=1.0):
        with open(self.json_path, "r") as f:
            data = json.load(f)
        bg_img_data = base64.b64decode(data["image"])
        image = Image.open(BytesIO(bg_img_data))
        if scale != 1.0:
            new_size = (int(image.width * scale), int(image.height * scale))
            image = image.resize(new_size, Image.ANTIALIAS)
        if self.background is None:
            self.background_surface = pygame.image.fromstring(
                image.tobytes(), image.size, image.mode
            )
            self.background_image = Image.open(BytesIO(image.tobytes()))
        else:
            self.background_surface = pygame.image.load(self.background)
            self.background_image = Image.open(self.background).convert("RGBA")

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
        self.first_draw()
        average_fps = []
        try:
            while self.running:
                self.frame_count += 1
                # poll for events
                # pygame.QUIT event means the user clicked X to close your window
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        sys.exit()

                # fill the screen with a color to wipe away anything from last frame
                self.draw_background()

                self.particle_spawner.delete_particles()
                self.particle_spawner.emit()
                for spawner in self.temporary_particle_spawners:
                    spawner.delete_particles()
                    spawner.emit()

                # update ui
                for character in self.characters:
                    character.ui_element.display()

                # sort by speed
                tangible_characters = filter(
                    lambda c: not c.is_intangible(), self.characters
                )
                tangible_characters = sorted(
                    tangible_characters, key=lambda x: x.get_speed(), reverse=True
                )
                collisions = []
                for character in tangible_characters:
                    for other_character in tangible_characters:
                        if other_character is character:
                            continue
                        if character.is_colliding(other_character):
                            character.use_move(other_character)
                            collisions.append([character, other_character])

                for collision in collisions:
                    collision[0].resolve_collision(collision[1])

                # update loop
                for character in self.characters:
                    character.update()

                # move loop
                for character in self.characters:
                    character.move()

                # draw loop
                # fainted characters should appear below other characters. Draw them first
                for character in sorted(
                    self.characters, key=lambda x: 0 if x.is_fainted() else 1
                ):
                    character.draw()

                self.particle_spawner.emit(True)
                for spawner in self.temporary_particle_spawners:
                    spawner.emit(True)

                if not self.game_end:
                    self.check_game_end()

                self.render_all_messages()
                if self.running and self.frame_count % self.draw_every_nth_frame == 0:
                    self.show_display()

                if self.pygame_mode:
                    self.clock.tick(self.FRAMES_PER_SECOND)
                else:
                    self.clock.tick(0)
                average_fps.append(self.clock.get_fps())
                if self.frame_count % honse_data.FRAMES_PER_SECOND == 0:
                    print(f"FPS: {np.mean(average_fps)}")
                    average_fps = []

                if self.game_end:
                    self.game_end_timer -= 1
                    if self.game_end_timer < 0:
                        self.running = False
        except KeyboardInterrupt:
            self.running = False
        finally:
            if self.video_mode:
                try:
                    self.video_writer.stdin.close()  # signal EOF to FFmpeg
                except Exception as e:
                    print(f"Failed to close FFmpeg stdin: {e}")

                try:
                    self.video_writer.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print("FFmpeg did not terminate in time, killing it.")
                    self.video_writer.kill()

                if self.video_writer.returncode != 0:
                    print(
                        "FFmpeg returned non-zero exit status:",
                        self.video_writer.returncode,
                    )
                else:
                    print("FFmpeg finished successfully.")


# i am lazy and dont want to resize the map rn
# plz pass in a map that is 3/4 the size of height and width for the second parameter
game = HonseGame("map02.json", "map02.png", "hgss kanto wild theme.mp3", True, False)
game.add_character(
    "Saurbot",
    0,
    100,
    {"HP": 77, "ATK": 5, "DEF": 107, "SPA": 5, "SPD": 104, "SPE": 20},
    random.sample(list(honse_pokemon.moves.values()), 4),
    [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]],
    "bob.png",
)
game.add_character(
    "Saur",
    0,
    100,
    {"HP": 114, "ATK": 44, "DEF": 104, "SPA": 95, "SPD": 138, "SPE": 55},
    random.sample(list(honse_pokemon.moves.values()), 4),
    [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Poison"]],
    "saur.png",
)
game.add_character(
    "Apollo",
    0,
    100,
    {"HP": 88, "ATK": 119, "DEF": 103, "SPA": 117, "SPD": 101, "SPE": 94},
    random.sample(list(honse_pokemon.moves.values()), 4),
    [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Ghost"]],
    "apollo.png",
)
game.add_character(
    "Dragonite",
    0,
    100,
    {"HP": 91, "ATK": 134, "DEF": 95, "SPA": 100, "SPD": 100, "SPE": 80},
    random.sample(list(honse_pokemon.moves.values()), 4),
    [honse_pokemon.pokemon_types["Dragon"], honse_pokemon.pokemon_types["Flying"]],
    "dragonite.png",
)

game.add_character(
    "Alakazam",
    1,
    100,
    {"HP": 55, "ATK": 50, "DEF": 45, "SPA": 135, "SPD": 95, "SPE": 120},
    random.sample(list(honse_pokemon.moves.values()), 4),
    [honse_pokemon.pokemon_types["Psychic"]],
    "alakazam.png",
)
game.add_character(
    "Warwolf",
    1,
    100,
    {"HP": 106, "ATK": 116, "DEF": 69, "SPA": 46, "SPD": 87, "SPE": 96},
    random.sample(list(honse_pokemon.moves.values()), 4),
    [honse_pokemon.pokemon_types["Ice"], honse_pokemon.pokemon_types["Dark"]],
    "warwolf.png",
)
game.add_character(
    "Sudowoodo",
    1,
    100,
    {"HP": 80, "ATK": 115, "DEF": 125, "SPA": 30, "SPD": 65, "SPE": 55},
    random.sample(list(honse_pokemon.moves.values()), 4),
    [honse_pokemon.pokemon_types["Rock"]],
    "sudowoodo.png",
)
game.add_character(
    "Croconaw",
    1,
    100,
    {"HP": 75, "ATK": 90, "DEF": 85, "SPA": 59, "SPD": 68, "SPE": 68},
    random.sample(list(honse_pokemon.moves.values()), 4),
    [honse_pokemon.pokemon_types["Water"]],
    "croconaw.png",
)
cProfile.run("game.main_loop()", sort="cumtime", filename="res")


import pstats

p = pstats.Stats("res")
p.strip_dirs()
p.sort_stats("cumulative").print_stats(40)
pygame.quit()
