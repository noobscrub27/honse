import pygame
import random
import math
import numpy as np

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

COLLISION_INTANGIBILITY = 30
FRAMES_PER_SECOND = 60
FRAME_LENGTH_SECONDS = 1 / FRAMES_PER_SECOND

SPEED_CAP = 30

class UIElement:
    width = 360
    height = 135
    border_width = 10
    name_x_offset = 15
    name_y_offset = 20
    level_x_offset = width-50
    level_y_offset = 30
    health_bar_width = width-(border_width*2)
    health_bar_height = 55
    health_bar_x_offset = border_width
    health_bar_y_offset = border_width
    cooldown_bar_width = (width - (2*border_width)) // 2
    cooldown_bar_height = 30
    cooldown_bar_x_offsets = [border_width, border_width+cooldown_bar_width, border_width, border_width+cooldown_bar_width]
    cooldown_bar_y_offsets = [border_width+health_bar_height, border_width+health_bar_height, border_width+health_bar_height+cooldown_bar_height, border_width+health_bar_height+cooldown_bar_height]
    move_name_x_offset = 10
    move_name_y_offset = 7
    name_font = pygame.font.Font('freesansbold.ttf', 28)
    level_font = pygame.font.Font('freesansbold.ttf', 16)
    move_font = pygame.font.Font('freesansbold.ttf', 16)
    health_colors = [
        [50, pygame.Color(0, 220, 63)],
        [20, pygame.Color(226, 162, 3)],
        [0, pygame.Color(219, 17, 15)]]
    cooldown_colors = [[0, pygame.Color(104, 185, 232)]]

    def __init__(self, x, y, character):
        self.x = x
        self.y = y
        self.character = character

    def display(self):
        screen = self.character.game.screen
        border_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        inner_rect = pygame.Rect(self.x+self.border_width,
                                 self.y+self.border_width,
                                 self.width-(2*self.border_width),
                                 self.height-(2*self.border_width))
        pygame.draw.rect(screen, "black", border_rect)
        pygame.draw.rect(screen, "white", inner_rect)
        
        self.draw_bar(screen, self.character.hp, self.character.get_max_hp(), self.x+self.health_bar_x_offset, self.y+self.health_bar_y_offset, self.health_bar_width, self.health_bar_height, self.health_colors)
        self.draw_text(screen, self.character.name, self.name_font, self.x+self.name_x_offset, self.y+self.name_y_offset)
        self.draw_text(screen, f"L{self.character.level}", self.level_font, self.x+self.level_x_offset, self.y+self.level_y_offset)
        for i in range(4):
            current_cooldown = self.character.cooldowns[i]
            try:
                max_cooldown = self.character.moves[i].cooldown
                move_name = self.character.moves[i].name
            except IndexError:
                max_cooldown = 1
                move_name = ""
            self.draw_bar(screen, current_cooldown, max_cooldown, self.x+self.cooldown_bar_x_offsets[i], self.y+self.cooldown_bar_y_offsets[i], self.cooldown_bar_width, self.cooldown_bar_height, self.cooldown_colors)
            self.draw_text(screen, move_name, self.move_font, self.x+self.cooldown_bar_x_offsets[i]+self.move_name_x_offset, self.y+self.cooldown_bar_y_offsets[i]+self.move_name_y_offset)
        

    def draw_text(self, screen, text, font, x, y):
        text = font.render(text, False, 'black')
        text_rect = text.get_rect()
        text_rect.x = x
        text_rect.y = y
        screen.blit(text, text_rect)

    def draw_bar(self, screen, value, max_value, x, y, width, height, colors):
        # colors is a list of lists
        # [[x, Color]]
        # x is the percentage of the bar to be filled for color to be displayed
        # higher x values should be placed earlier in the list
        value_decimal = value / max_value
        color = "white"
        for color_pair in colors:
            if value_decimal * 100 >= color_pair[0]:
                color = color_pair[1]
                break
        adjusted_length = math.floor(value_decimal * width)
        if value > 0 and adjusted_length == 0:
            adjusted_length = 1
        bar = pygame.Rect(x, y, adjusted_length, height)
        pygame.draw.rect(screen, color, bar)