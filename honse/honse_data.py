from numpy.random import f
import pygame
import random
import math
import numpy as np
import os
from PIL import Image

#may break things
os.chdir(os.path.dirname(os.path.abspath(__file__)))

STAT_BUFF_DURATION = 900
MAX_EFFECT_VALUE = 1800

COLLISION_INTANGIBILITY = 30
FRAMES_PER_SECOND = 60
FRAME_LENGTH_SECONDS = 1 / FRAMES_PER_SECOND

SPEED_CAP = 30

FONT_NAME = os.path.join("cascadia-code", "Cascadia.ttf")

TEAM_COLORS = [[166, 10, 28], [15, 10, 166]]

BASE_WIDTH = 1920
BASE_HEIGHT = 1080

SUDDEN_DEATH_FRAMES = 2700

# equates to 24 hours for when i want things to last indefinitely
A_LOT_OF_FRAMES = 5184000
# the number of frames a status icon will display before the next effect is displayed
STATUS_ICON_BLINK_LENGTH = 90

NATURES = {
    "Hardy": {"ATK": 1, "DEF": 1, "SPA": 1, "SPD": 1, "SPE": 1},
    "Lonely": {"ATK": 1.1, "DEF": 0.9, "SPA": 1, "SPD": 1, "SPE": 1},
    "Brave": {"ATK": 1.1, "DEF": 1, "SPA": 1, "SPD": 1, "SPE": 0.9},
    "Adamant": {"ATK": 1.1, "DEF": 1, "SPA": 0.9, "SPD": 1, "SPE": 1},
    "Naughty": {"ATK": 1.1, "DEF": 1, "SPA": 1, "SPD": 0.9, "SPE": 1},
    "Bold": {"ATK": 0.9, "DEF": 1.1, "SPA": 1, "SPD": 1, "SPE": 1},
    "Docile": {"ATK": 1, "DEF": 1, "SPA": 1, "SPD": 1, "SPE": 1},
    "Relaxed": {"ATK": 1, "DEF": 1.1, "SPA": 1, "SPD": 1, "SPE": 0.9},
    "Impish": {"ATK": 1, "DEF": 1.1, "SPA": 0.9, "SPD": 1, "SPE": 1},
    "Lax": {"ATK": 1, "DEF": 1.1, "SPA": 1, "SPD": 0.9, "SPE": 1},
    "Timid": {"ATK": 0.9, "DEF": 1, "SPA": 1, "SPD": 1, "SPE": 1.1},
    "Hasty": {"ATK": 1, "DEF": 0.9, "SPA": 1, "SPD": 1, "SPE": 1.1},
    "Serious": {"ATK": 1, "DEF": 1, "SPA": 1, "SPD": 1, "SPE": 1},
    "Jolly": {"ATK": 1, "DEF": 1, "SPA": 0.9, "SPD": 1, "SPE": 1.1},
    "Naive": {"ATK": 1, "DEF": 1, "SPA": 1, "SPD": 0.9, "SPE": 1.1},
    "Modest": {"ATK": 0.9, "DEF": 1, "SPA": 1.1, "SPD": 1, "SPE": 1},
    "Mild": {"ATK": 1, "DEF": 0.9, "SPA": 1.1, "SPD": 1, "SPE": 1},
    "Quiet": {"ATK": 1, "DEF": 1, "SPA": 1.1, "SPD": 1, "SPE": 0.9},
    "Bashful": {"ATK": 1, "DEF": 1, "SPA": 1, "SPD": 1, "SPE": 1},
    "Rash": {"ATK": 1, "DEF": 1, "SPA": 1.1, "SPD": 0.9, "SPE": 1},
    "Calm": {"ATK": 0.9, "DEF": 1, "SPA": 1, "SPD": 1.1, "SPE": 1},
    "Gentle": {"ATK": 1, "DEF": 0.9, "SPA": 1, "SPD": 1.1, "SPE": 1},
    "Sassy": {"ATK": 1, "DEF": 1, "SPA": 1, "SPD": 1.1, "SPE": 0.9},
    "Careful": {"ATK": 1, "DEF": 1, "SPA": 0.9, "SPD": 1.1, "SPE": 1},
    "Quirky": {"ATK": 1, "DEF": 1, "SPA": 1, "SPD": 1, "SPE": 1},
    }


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

# when you can't reproduce a bug, use the bug finder.
# add code to detect when the bug occurs, and pass a brief description of what occurred and the game object to found_bug
# then set the game to run a bunch of times and get_found_bugs at the end
class BugFinder:
    def __init__(self):
        self.message_log = []

    def found_bug(self, description, game):
        game_log_file = game.log_out_path
        frame = game.frame_count
        self.message_log.append(f"{description} - Check frame {frame} of {game_log_file}.")

    def get_found_bugs(self):
        if len(self.message_log):
            text = "Bugs found:\n"
            for msg in self.message_log:
                text += "\t" + msg + "\n"
            return text.strip()
        else:
            return "No bugs found."

BUG_FINDER = BugFinder()

class UIElement:
    width = 360
    height = 135
    border_width = 10
    name_x_offset = 15
    name_y_offset = 20
    level_font_size = 16
    health_bar_width = width - (border_width * 2)
    health_bar_height = 55
    health_bar_x_offset = border_width
    health_bar_y_offset = border_width
    # 40 is the size of all the status icons
    # status icons are drawn from the top right of the ui element
    # there should be 5 pixels between each status icon. status icons in total take up to the last 90 pixels of the ui element
    # they render on top of the health bar
    status_icon_x = width - (40 + border_width + 5)
    status_icon_y = ((health_bar_height - 40) // 2) + border_width
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
    locked_cooldown_colors = [[0, (250, 70, 82, 255)]]
    max_character_name_length = 14

    def __init__(self, x, y, character):
        self.x = x
        self.y = y
        self.game = character.game
        self.character = character
        self.display_name = character.name
        if len(self.display_name) > self.max_character_name_length:
            self.display_name = self.display_name[:self.max_character_name_length]
        # at any given time
        # the ui can display one non-volatile status (burn, freeze, paralysis, poison, sleep, toxic)
        # and one volatile status (every other status)
        # status queue is a list of lists
        # each sublist is a list of statuses that share a status icon
        # this is so that an icon isnt getting displayed twice if there are two similar statuses
        # when a status wears off, but there is a similar status remaining, since they share a list, its place in the queue wont change
        self.status_queue = []

    def next_status_icon(self):
        if len(self.status_queue) > 1:
            removed_status = self.status_queue.pop(0)
            self.status_queue.append(removed_status)

    def queue_status(self, status):
        appended = False
        if len(self.status_queue) > 0:     
            for sublist in self.status_queue:
                if sublist[0].status_icon == status.status_icon:
                    sublist.append(status)
                    appended = True
                    break
        if appended == False:
            self.status_queue.append([status])

    def unqueue_status(self, status):
        for i, status_group in enumerate(self.status_queue):
            if status in status_group:
                self.status_queue[i].remove(status)
                if len(self.status_queue[i]) == 0:
                    self.status_queue.pop(i)

    def draw_status_icons(self):
        volatile_status_icon = None
        non_volatile_status_icon = None
        if len(self.status_queue):
            volatile_status_icon = self.status_queue[0][0].status_icon
        if self.character.has_non_volatile_status:
            non_volatile_status_icon = self.character.get_non_volatile_status().status_icon
        if non_volatile_status_icon is None and volatile_status_icon is None:
            return
        elif volatile_status_icon is not None and non_volatile_status_icon is not None:
            image = self.game.status_icon_images[volatile_status_icon]
            surface = self.game.status_icon_surfaces[volatile_status_icon]
            self.game.draw_image(
                self.x + self.status_icon_x,
                self.y + self.status_icon_y,
                surface,
                image
                )
            image = self.game.status_icon_images[non_volatile_status_icon]
            surface = self.game.status_icon_surfaces[non_volatile_status_icon]
            self.game.draw_image(
                self.x + self.status_icon_x-45,
                self.y + self.status_icon_y,
                surface,
                image
                )
        else:
            if volatile_status_icon is not None:
                icon = volatile_status_icon
            else:
                icon = non_volatile_status_icon
            image = self.game.status_icon_images[icon]
            surface = self.game.status_icon_surfaces[icon]
            self.game.draw_image(
                self.x + self.status_icon_x,
                self.y + self.status_icon_y,
                surface,
                image
                )

    def first_draw(self, draw):
        if self.game.video_mode:
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
        screen = self.game.screen
        border_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        inner_rect = pygame.Rect(
            self.x + self.border_width,
            self.y + self.border_width,
            self.width - (2 * self.border_width),
            self.height - (2 * self.border_width),
        )
        if self.game.pygame_mode:
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
        self.draw_status_icons()
        name_size = self.game.draw_text(
            self.x + self.name_x_offset,
            self.y + self.name_y_offset,
            self.character.name,
            24,
            0,
            0,
            0,
            255,
        )
        self.game.draw_text(
            self.x + 30 + max(50,name_size[0]),
            self.y + self.name_y_offset + name_size[1] - self.level_font_size,
            f"L{self.character.level}",
            self.level_font_size,
            0,
            0,
            0,
            255,
        )
        self.game.draw_text(
            self.x + self.name_x_offset,
            self.y + self.name_y_offset + name_size[1] + 5,
            f"HP {self.character.get_hp_as_percent()}%",
            self.level_font_size,
            0,
            0,
            0,
            255,
        )
        for i in range(4):
            current_cooldown = self.character.cooldowns[i]
            colors = self.cooldown_colors
            try:
                max_cooldown = self.character.moves[i].cooldown
                move_name = self.character.moves[i].name
                if self.character.is_move_locked(i):
                    colors = self.locked_cooldown_colors
                    current_cooldown = max_cooldown
            except IndexError:
                continue
            self.draw_bar(
                screen,
                current_cooldown,
                max_cooldown,
                self.x + self.cooldown_bar_x_offsets[i],
                self.y + self.cooldown_bar_y_offsets[i],
                self.cooldown_bar_width,
                self.cooldown_bar_height,
                colors,
            )
            self.game.draw_text(
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
        self.game.draw_rectangle(x, y, adjusted_length, height, 0, color)
