import pygame
import random
import math
import numpy as np
import os
from PIL import Image

#may break things
os.chdir(os.path.dirname(os.path.abspath(__file__)))


COLLISION_INTANGIBILITY = 30
FRAMES_PER_SECOND = 60
FRAME_LENGTH_SECONDS = 1 / FRAMES_PER_SECOND

SPEED_CAP = 30

FONT_NAME = os.path.join("cascadia-code", "Cascadia.ttf")

TEAM_COLORS = [[166, 10, 28], [15, 10, 166]]

BASE_WIDTH = 1920
BASE_HEIGHT = 1080

def image_to_surface(image):
    return pygame.image.fromstring(
        image.tobytes(), image.size, image.mode
    ).convert_alpha()

def alpha_change(image, alpha_percent):
    r, g, b, a = image.split()
    return Image.merge(
        "RGBA", (r, g, b, a.point(lambda x: (x * alpha_percent) // 100))
    )

def from_sprite_sheet(image, width):
    images = []
    sprite_sheet_width, sprite_sheet_height = image.size
    if sprite_sheet_width % width != 0:
        raise ValueError(f"sprite_sheet_width must be evenly divisible by width. (sprite_sheet_width: {sprite_sheet_width}, width: {width}")
    for i in range(sprite_sheet_width // width):
        x = i * width
        images.append(image.crop((x, 0, x+width, sprite_sheet_height)))
    return images

class UIElement:
    width = 360
    height = 135
    border_width = 10
    name_x_offset = 15
    name_y_offset = 20
    level_x_offset = width - 50
    level_y_offset = 30
    health_bar_width = width - (border_width * 2)
    health_bar_height = 55
    health_bar_x_offset = border_width
    health_bar_y_offset = border_width
    cooldown_bar_width = (width - (2 * border_width)) // 2
    cooldown_bar_height = 30
    cooldown_bar_x_offsets = [
        border_width,
        border_width + cooldown_bar_width,
        border_width,
        border_width + cooldown_bar_width,
    ]
    cooldown_bar_y_offsets = [
        border_width + health_bar_height,
        border_width + health_bar_height,
        border_width + health_bar_height + cooldown_bar_height,
        border_width + health_bar_height + cooldown_bar_height,
    ]
    move_name_x_offset = 10
    move_name_y_offset = 7
    health_colors = [
        [50, (0, 220, 63, 255)],
        [20, (226, 162, 3, 255)],
        [0, (219, 17, 15, 255)],
    ]
    cooldown_colors = [[0, (104, 185, 232, 255)]]

    def __init__(self, x, y, character):
        self.x = x
        self.y = y
        self.character = character

    def first_draw(self, draw):
        if self.character.game.video_mode:
            colors = [color for color in TEAM_COLORS[self.character.team]]
            colors.append(255)
            colors = tuple(colors)
            draw.rectangle([self.x, self.y, self.x + self.width, self.y + self.height], fill=colors)
            draw.rectangle(
                [
                    self.x + self.border_width,
                    self.y + self.border_width,
                    self.x + self.width - self.border_width,
                    self.y + self.height - self.border_width,
                ],
                fill=(255, 255, 255, 255),
            )


    def display(self):
        screen = self.character.game.screen
        border_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        inner_rect = pygame.Rect(
            self.x + self.border_width,
            self.y + self.border_width,
            self.width - (2 * self.border_width),
            self.height - (2 * self.border_width),
        )
        if self.character.game.pygame_mode:
            pygame.draw.rect(
                screen, pygame.Color(*TEAM_COLORS[self.character.team]), border_rect
            )
            pygame.draw.rect(screen, pygame.Color(255, 255, 255), inner_rect)

        self.draw_bar(
            screen,
            self.character.hp,
            self.character.get_max_hp(),
            self.x + self.health_bar_x_offset,
            self.y + self.health_bar_y_offset,
            self.health_bar_width,
            self.health_bar_height,
            self.health_colors,
        )
        self.character.game.draw_text(
            self.x + self.name_x_offset,
            self.y + self.name_y_offset,
            self.character.name,
            28,
            0,
            0,
            0,
            255,
        )
        self.character.game.draw_text(
            self.x + self.level_x_offset,
            self.y + self.level_y_offset,
            f"L{self.character.level}",
            16,
            0,
            0,
            0,
            255,
        )
        for i in range(4):
            current_cooldown = self.character.cooldowns[i]
            try:
                max_cooldown = self.character.moves[i].cooldown
                move_name = self.character.moves[i].name
            except IndexError:
                max_cooldown = 1
                move_name = ""
            self.draw_bar(
                screen,
                current_cooldown,
                max_cooldown,
                self.x + self.cooldown_bar_x_offsets[i],
                self.y + self.cooldown_bar_y_offsets[i],
                self.cooldown_bar_width,
                self.cooldown_bar_height,
                self.cooldown_colors,
            )
            self.character.game.draw_text(
                self.x + self.cooldown_bar_x_offsets[i] + self.move_name_x_offset,
                self.y + self.cooldown_bar_y_offsets[i] + self.move_name_y_offset,
                move_name,
                16,
                0,
                0,
                0,
                255,
            )

    def draw_bar(self, screen, value, max_value, x, y, width, height, colors):
        # colors is a list of lists
        # [[x, Color]]
        # x is the percentage of the bar to be filled for color to be displayed
        # higher x values should be placed earlier in the list
        value_decimal = value / max_value
        color = (0, 0, 0, 255)
        for color_pair in colors:
            if value_decimal * 100 >= color_pair[0]:
                color = color_pair[1]
                break
        adjusted_length = math.floor(value_decimal * width)
        if value > 0 and adjusted_length == 0:
            adjusted_length = 1
        self.character.game.draw_rectangle(x, y, adjusted_length, height, 0, color)
