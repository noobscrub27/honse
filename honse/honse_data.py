from dataclasses import dataclass
from numpy.random import f
import pygame
import random
import math
import numpy as np
import os
from PIL import Image, ImageColor, ImageFont, ImageDraw
import colorsys

#may break things
os.chdir(os.path.dirname(os.path.abspath(__file__)))

STAT_BUFF_DURATION = 900
MAX_EFFECT_VALUE = 1800

COLLISION_INTANGIBILITY = 30
FRAMES_PER_SECOND = 60
FRAME_LENGTH_SECONDS = 1 / FRAMES_PER_SECOND

SPEED_CAP = 30

FONT_NAME = os.path.join("fonts", "cascadia-code", "Cascadia.ttf")
FONT_NAME = os.path.join("fonts", "pokemon-gen-4-regular", "pokemon-gen-4-regular.otf")

FONT_NAME = os.path.join("fonts", "pokemon-bw", "pokemon-bw.otf")
FONT_NAME = os.path.join("fonts", "pokemon-xyoras", "pokemon-xyoras.otf")
FONT_NAME = os.path.join("fonts", "pokemon-gen-4-fullwidth", "pokemon-gen-4-fullwidth.otf")
# this holds all of the fonts
# font name: {font_size: [pygame_object, PIL_object]}
fonts = {}
TEAM_COLORS = [[166, 10, 28], [15, 10, 166]]

BASE_WIDTH = 1920
BASE_HEIGHT = 1080

SUDDEN_DEATH_FRAMES = 7200

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

def hue_shift(image, shift_amount):
    # get alpha
    r, g, b, a = image.split()
    # convert to hsv
    image = image.convert("HSV")
    h, s, v = image.split()
    # hue shift
    image = Image.merge("HSV", (h.point(lambda x: x + shift_amount), s, v))
    # convert to rgb
    image = image.convert("RGB")
    # get rgb
    r, g, b = image.split()
    # reassemble rgb with previous alpha
    image = Image.merge("RGBA", (r, g, b, a))
    return image

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

BAR_COLORS = {
        "white_bg": (248, 248, 248, 255),
        "white_bg_transparent": (248, 248, 248, 127),
        "blackish_bg_light": (80, 104, 88, 255),
        "blackish_bg_dark": (72, 64, 88, 255),
        "high_hp_light": (112, 248, 168, 255),
        "high_hp_dark": (88, 208, 128, 255),
        "low_hp_light": (248, 224, 56, 255),
        "low_hp_dark": (200, 168, 8, 255),
        "critical_hp_light": (248, 88, 56, 255),
        "critical_hp_lighter": (248, 128, 88, 255),
        "critical_hp_dark": (168, 64, 72, 255),
        "move_ready": (64, 248, 88, 255),
        "move_cooldown": (64, 200, 248, 255),
        "move_locked": (200, 88, 88, 255),
        }

def draw_bar(game, x, y, width, height, value, color, always_display_if_not_empty=False):
    adjusted_length = math.floor(value * width)
    if always_display_if_not_empty and value > 0 and adjusted_length == 0:
        adjusted_length = 1
    game.draw_rectangle(x, y, adjusted_length, height, 0, color)

def draw_health_bar(game, x, y, width, height, value, label_text, label_width):
    # the bar is drawn black
    # then white for the inner 5/7ths
    # then color based on value for the inner 3/7ths
    height_mod_seven = height % 7
    height_divided_by_seven = height // 7
    white_bg_height = 5 * height_divided_by_seven + height_mod_seven
    white_bg_y = y + height_divided_by_seven
    bar_light_height = 3 * height_divided_by_seven + height_mod_seven
    bar_light_y = white_bg_y + height_divided_by_seven
    bar_dark_height = height_divided_by_seven
    bar_dark_y = bar_light_y
    bar_x = x + label_width
    bar_width = width - label_width
    health_bar_x = bar_x + height_divided_by_seven
    health_bar_width = bar_width - (2*height_divided_by_seven)
    game.draw_rectangle(x, y, width, height, 0, BAR_COLORS["blackish_bg_light"])
    game.draw_rectangle(bar_x, white_bg_y, bar_width, white_bg_height, 0, BAR_COLORS["white_bg"])
    game.draw_rectangle(health_bar_x, bar_dark_y, health_bar_width, bar_dark_height, 0, BAR_COLORS["blackish_bg_light"])
    game.draw_rectangle(health_bar_x, bar_light_y, health_bar_width, bar_light_height, 0, BAR_COLORS["blackish_bg_dark"])
    if value > 0.5:
        light_color = BAR_COLORS["high_hp_light"]
        dark_color = BAR_COLORS["high_hp_dark"]
    elif value > 0.2:
        light_color = BAR_COLORS["low_hp_light"]
        dark_color = BAR_COLORS["low_hp_dark"]
    else:
        light_color = BAR_COLORS["critical_hp_light"]
        dark_color = BAR_COLORS["critical_hp_dark"]
    draw_bar(game, health_bar_x, bar_light_y, health_bar_width, bar_light_height, value, light_color, True)
    draw_bar(game, health_bar_x, bar_dark_y, health_bar_width, bar_dark_height, value, dark_color, True)
    text_x = x + ((label_width - label_text.size[0]) // 2)
    text_y = y + ((height - label_text.size[1]) // 2)
    label_text.draw(text_x, text_y)

def draw_move_bar(game, x, y, width, height, value, label_text, label_x, locked=False):
    if locked:
        color = BAR_COLORS["move_locked"]
        value = 1
    elif value == 0:
        color = BAR_COLORS["move_ready"]
        value = 1
    else:
        color = BAR_COLORS["move_cooldown"]
        draw_bar(game, x, y, width, height, 1, BAR_COLORS["white_bg_transparent"])
    draw_bar(game, x, y, width, height, value, color)
    label_text.draw(label_x, y)

class UIElement:
    width = 240
    status_size = 40
    status_padding = 5
    status1_x = width - status_size
    status2_x = width - (2 * status_size) - status_padding
    name_gradient_size = 20
    max_name_length_pixels = status2_x - status_padding - name_gradient_size
    status1_x = width - 40
    status2_x = width - 85
    hp_bar_height = 42
    hp_label_width = 0
    move_bar_height = 20
    move_name_padding = 10
    move_bar_width = (width - (2*move_name_padding)) // 2
    left_move_x = 0
    right_move_x = width // 2
    y_padding = 4
    name_font_size = 20
    move_font_size = 16
    hp_font_size = 16
    height = status_size + hp_bar_height + move_bar_height + (y_padding * 4)
    def __init__(self, x, y, character):
        self.x = x
        self.y = y
        self.game = character.game
        self.character = character
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
        if status.status_icon is None or len(status.status_icon) == 0:
            return
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
                self.x + self.status1_x,
                self.y,
                surface,
                image
                )
            image = self.game.status_icon_images[non_volatile_status_icon]
            surface = self.game.status_icon_surfaces[non_volatile_status_icon]
            self.game.draw_image(
                self.x + self.status2_x,
                self.y,
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
                self.x + self.status1_x,
                self.y,
                surface,
                image
                )

    def update_move_and_hp_text(self):
        new_hp = self.character.get_hp_as_percent()
        if self.last_hp_amount != new_hp:
            self.last_hp_amount = new_hp
            hp_ratio = self.character.hp / self.character.max_hp
            if hp_ratio > 0.5:
                color = BAR_COLORS["high_hp_light"]
            elif hp_ratio > 0.2:
                color = BAR_COLORS["low_hp_light"]
            else:
                color = BAR_COLORS["critical_hp_lighter"]
            self.hp_text = HonseText(self.game, f"{self.last_hp_amount}%", self.font, self.hp_font_size, color)
            self.hp_text.get_text_image()
        for i, move in enumerate(self.character.current_moves):
            if move.name != self.move_name_strings[i]:
                self.move_name_strings[i] = move.name
                self.move_name_texts[i] = HonseText(self.game, move.name, self.font, self.move_font_size, (0, 0, 0, 255))

    def first_draw(self, draw):
        self.font = self.game.message_fonts["gen4"]
        name_bg_color = self.character.team.color_rgb
        name_bg_color = (
            name_bg_color[0],
            name_bg_color[1],
            name_bg_color[2],
            127)
        font = self.font.get_pil_font(self.name_font_size)
        ascent, descent = font.getmetrics()
        name_bg_height = ascent + descent
        name_length = font.getlength(self.character.name)
        while name_length > self.max_name_length_pixels:
            self.name_font_size -= 1
            font = self.font.get_pil_font(self.name_font_size)
            ascent, descent = font.getmetrics()
            name_bg_height = ascent + descent
            name_length = font.getlength(self.character.name)
        self.name_text = HonseText(self.game, self.character.name, self.font, self.name_font_size, (255, 255, 255, 255), name_bg_color, self.name_gradient_size, self.width, name_bg_height)
        font = self.font.get_pil_font(self.hp_font_size)
        self.hp_label_width = font.getlength("100%") + 8
        self.last_hp_amount = 0
        self.move_name_strings = ["", "", "", ""]
        self.move_name_texts = [None, None, None, None]
        self.update_move_and_hp_text()

    def display(self):
        self.update_move_and_hp_text()
        if len(self.status_queue) or self.character.has_non_volatile_status:
            centered = False
        else:
            centered = True
        y = self.y + self.y_padding
        self.name_text.draw(self.x, y, True, centered)
        y += self.name_text.get_size()[1] + self.y_padding
        health_value = self.character.hp / self.character.max_hp
        draw_health_bar(self.game, self.x, y, self.width, self.hp_bar_height, health_value, self.hp_text, self.hp_label_width)
        y += self.y_padding + self.hp_bar_height
        self.draw_status_icons()
        fainted = self.character.is_fainted()
        for i in range(4):
            try:
                if self.move_name_texts[i] is None:
                    continue
            except IndexError:
                continue
            if i % 2 == 0:
                x = self.x + self.left_move_x
            else:
                x = self.x + self.right_move_x
            if i == 2:
                y += self.move_bar_height + (self.y_padding // 2)
            max_cooldown = self.character.current_moves[i].cooldown
            current_cooldown = self.character.cooldowns[i]
            locked = self.character.is_move_locked(i)
            draw_move_bar(self.game, x, y, self.move_bar_width, self.move_bar_height, current_cooldown/max_cooldown, self.move_name_texts[i], x + self.move_name_padding, locked=locked or fainted)


# text_surface = self.message_fonts[font_key][0].render(text, False, color)
class HonseFont:
    def __init__(self, game, name: str, file: str):
        self.game = game
        self.name = name
        self.file = file
        self.pygame_fonts = {}
        self.pil_fonts = {}

    def get_pygame_font(self, size):
        if size not in self.pygame_fonts:
            self.pygame_fonts[size] = pygame.font.Font(self.file, self.game.times_width_ratio(size))
        return self.pygame_fonts[size]

    def get_pil_font(self, size):
        if size not in self.pil_fonts:
            self.pil_fonts[size] = ImageFont.truetype(self.file, self.game.times_width_ratio(size))
        return self.pil_fonts[size]

class HonseText:
    formatting_code_indicator = "$"
    def __init__(self, game, text: str, font: "HonseFont", font_size: int, text_color: tuple, background_color: tuple|None = None, gradient_size: int = 0, force_background_width: int|None = None, force_background_height: int|None = None):
        self.game = game
        self.text = text.replace("\n", "")
        self.display_text = ""
        self.font = font
        self.font_size = font_size
        self.color = text_color
        self.substrings = []
        self.background_color = background_color
        self.gradient_size = gradient_size
        self.text_surface = None
        self.text_image = None
        self.background_surface = None
        self.background_image = None
        self.substrings_mapped = False
        self.force_background_width = force_background_width
        self.force_background_height = force_background_height
        self.parse_text()
        self.size = None
        self.background_image_size = None

    def parse_text(self):
        # similar to double backslash, double formatting_code_indicator cancels itself out
        text = self.text.replace(self.formatting_code_indicator+self.formatting_code_indicator, "")
        text_parts = text.split(self.formatting_code_indicator)
        current_color = self.color
        display_text = ""
        for i, text_part in enumerate(text_parts):
            if i != 0:
                if text_part.startswith("#"):
                    hex_code = text_part[:7]
                    rgb = ImageColor.getcolor(hex_code, "RGB")
                    text_part = text_part[7:]
                    current_color = (rgb[0], rgb[1], rgb[2], current_color[3])
                elif text_part.startswith("ALPHA"):
                    alpha = text_part[5:8]
                    text_part = text_part[8:]
                    alpha = min(255, max(0, int(alpha)))
                    current_color = (current_color[0], current_color[1], current_color[2], alpha)
            display_text += text_part
            substring = {"text":text_part, "color":current_color}
            self.substrings.append(substring)
        self.display_text = display_text

    def get_text_surface(self):
        if self.text_image is None:
            self.get_text_image()
        self.text_surface = image_to_surface(self.text_image)

    def get_text_image(self):
        font = self.font.get_pil_font(self.font_size)
        width = 0
        height = 0
        for substring in self.substrings:
            bbox = font.getbbox(substring["text"])
            substring["x"] = width
            width += bbox[2]
            if bbox[3] > height:
                height = bbox[3]
        width = math.ceil(width)
        height = math.ceil(height)
        self.text_image = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(self.text_image)
        for substring in self.substrings:
            draw.text((substring["x"],0), substring["text"], font=font, fill=substring["color"])
        self.size = self.text_image.size

    def get_background_surface(self):
        if self.background_color is not None and self.background_image is None:
            self.get_background_image()
        self.background_surface = image_to_surface(self.background_image)

    def get_background_image(self):
        if self.background_color is None:
            return
        if self.size is None:
            self.get_text_image()
        width = self.size[0] + (2 * self.gradient_size)
        if self.force_background_width is not None:
            width = self.force_background_width
        ascent, descent = self.font.get_pil_font(self.font_size).getmetrics()
        height = ascent + descent
        if self.force_background_height is not None:
            height = self.force_background_height
        self.background_image = Image.new("RGBA", (width, height), color = self.background_color)
        # gradients
        if self.gradient_size > 0:
            max_alpha = self.background_color[3]
            gradient = Image.new("L", (width, 1), color=max_alpha)
            for i in range(self.gradient_size):
                a = int(i * (max_alpha / self.gradient_size))
                gradient.putpixel((i, 0), a)
                gradient.putpixel((width-i-1, 0), a)
            alpha = gradient.resize(self.background_image.size)
            self.background_image.putalpha(alpha)
        self.background_image_size = self.background_image.size

    def draw(self, x, y, align_with_background=False, centered=True):
        if self.background_color is not None:
            self.draw_background(x, y, align_with_background, centered)
        else:
            align_with_background = False
        self.draw_text(x, y, align_with_background, centered)

    def draw_background(self, x, y, align_with_background, centered):
        if self.game.pygame_mode and self.background_surface is None:
            self.get_background_surface()
        if self.game.video_mode and self.background_image is None:
            self.get_background_image()
        if not align_with_background:
            if centered:
                x -= ((self.background_image_size[0] - self.size[0]) // 2)
            else:
                x -= self.gradient_size
            y -= ((self.background_image_size[1] - self.size[1]) // 2)
        self.game.draw_image(x, y, self.background_surface, self.background_image)

    def draw_text(self, x, y, align_with_background, centered):
        if self.game.pygame_mode and self.text_surface is None:
            self.get_text_surface()
        if self.game.video_mode and self.text_image is None:
            self.get_text_image()
        if align_with_background:
            if centered:
                x += ((self.background_image_size[0] - self.size[0]) // 2)
            else:
                x += self.gradient_size
            y += ((self.background_image_size[1] - self.size[1]) // 2)
        self.game.draw_image(x, y, self.text_surface, self.text_image)

    def get_size(self):
        if self.background_image_size is not None:
            return self.background_image_size
        else:
            return self.size

#https://www.reddit.com/r/learnpython/comments/kbxbsi/rgb_string_value_to_hex_python_38/
def hexify(num):
    return f"{num:02x}"

def hexify_tuple(tup):
    return ''.join(hexify(value) for value in tup)

'''
    def get_font(self, font, size):
        pass

    if self.pygame_mode:
            color = pygame.Color(r, g, b)
            text_surface = self.message_fonts[font_key][0].render(text, False, color)
            text_surface.set_alpha(a)
            self.screen.blit(text_surface, (x, y))
        if self.video_mode:
            img, size = self.get_text_image(text, font_key, r, g, b, a)
            self.current_frame_image.paste(img, (int(x), int(y)), img)
'''

