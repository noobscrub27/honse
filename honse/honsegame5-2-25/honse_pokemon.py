from io import BytesIO
import pygame
import random
import math
import honse_data
import honse_particles
import enum
from PIL import Image
import numpy as np

TYPE_EFFECTIVENESS = [
    0.25,
    2/3,
    1,
    1.5]

TYPE_EFFECTIVENESS_QUOTES = [
    "It barely had any effect.",
    "It's not very effective.",
    "",
    "It's super effective!"
    ]

class EffectTypes(enum.Enum):
    ATTACK_MODIFICATION = 1
    DEFENSE_MODIFICATION = 2
    SPECIAL_ATTACK_MODIFICATION = 3
    SPECIAL_DEFENSE_MODIFICATION = 4
    SPEED_MODIFICATION = 5
    ACCELERATION_MODIFICATION = 6
    DRAG_MODIFICATION = 7

stats = {
    "HP": 100,
    "ATK": 100,
    "DEF": 100,
    "SPA": 100,
    "SPD": 100,
    "SPE": 150}

pokemon_types = {}
class PokemonType:
    def __init__(self, name):
        self.name = name
        self.weaknesses = []
        self.resistances = []
        self.immunities = []

with open("fnf-types.csv", "r") as f:
    lines = f.readlines()
    type_order = lines[0].split(",")[1:]
    for i, line in enumerate(lines[1:]):
        current_type = PokemonType(type_order[i])
        matchups = line.split(",")[1:]
        for j, matchup in enumerate(matchups):
            if matchup == "0.5":
                current_type.resistances.append(type_order[j])
            elif matchup == "2":
                current_type.weaknesses.append(type_order[j])
            elif matchup == "0":
                current_type.immunities.append(type_order[j])
        pokemon_types[type_order[i]] = current_type
    for pkmn_type in pokemon_types.values():
        pkmn_type.weaknesses = [pokemon_types[item] for item in pkmn_type.weaknesses]
        pkmn_type.resistances = [pokemon_types[item] for item in pkmn_type.resistances]
        pkmn_type.immunities = [pokemon_types[item] for item in pkmn_type.immunities]

def speed_formula(base, level, ivs=31, evs=0, nature=1):
    return min(max(1,15*(base/255)), 30)

def hp_formula(base, level, ivs=31, evs=0):
    return math.floor(((2*base+ivs+math.floor(evs/4))*level)/100) + level + 10

def other_stat_formula(base, level, ivs=31, evs=0, nature=1):
    return math.floor((math.floor(((2*base+ivs+math.floor(evs/4))*level)/100) + 5) * nature)

def collision_check(terrain_map, rect):
    try:
        return terrain_map.get_at(rect.center) == pygame.Color(0,0,0,255)
    except IndexError:
        return True

class Effect:
    effect_types = []
    def __init__(self, inflicted_by, inflicted_upon):
        self.inflicted_by = inflicted_by
        self.inflicted_upon = inflicted_upon

    def modify(self, effect_type, *args):
        if effect_type not in self.effect_types:
            return
        # modify code goes here

class Character():
    def __init__(self, game, name, team, level, stats, moves, types, image, teammate_id):
        self.game = game
        angle = random.uniform(0, 2 * np.pi)
        velocity = [np.cos(angle), np.sin(angle)]
        self.velocity = np.array(velocity, dtype=float)
        self.radius = 20
        self.name = name
        # the id of the team
        self.team = team
        # the id of the character on that team
        self.teammate_id = teammate_id
        self.level = level
        self.base_stats = stats
        self.moves = moves
        self.cooldowns = [0, 0, 0, 0]
        for i in range(len(self.moves)):
            self.on_cooldown(i)
        self.types = types
        # speed is pixels/frame
        self.current_speed = 0
        self.direction = random.uniform(0,360)
        # hitstop, intangibility, and invulnerability are measured in frames
        self.invulnerability = 0
        self.intangibility = 0
        self.hitstop = 0
        # insteading of adding a flat amount, acceleration and drag work changing the speed by a portion of the difference between current speed and target speed
        self.acceleration = 0.1
        self.drag = 0.1
        self.effects = []
        self.hp = self.get_hp()
        self.image_name = image
        self.get_image()
        ui_x = self.game.SCREEN_WIDTH * (self.teammate_id*3)/16
        ui_y = self.game.SCREEN_HEIGHT - ((self.game.SCREEN_HEIGHT/8)*(2-self.team))
        self.ui_element = honse_data.UIElement(ui_x, ui_y, self)
        self.spawn_in()

    def spawn_in(self):
        while True:
            self.position = np.array(self.game.spawn_in_area(self.team), dtype=float)
            colliding = False
            for character in self.game.characters:
                if character is self:
                    continue
                if self.is_colliding(character):
                    colliding = True
                    break
            if colliding == False:
                break

    def get_image(self):
        from PIL import Image
        image=Image.open(self.image_name)
        cropped_image = image.getbbox()
        cropped_image = image.crop(cropped_image)
        self.surface = pygame.image.fromstring(cropped_image.tobytes(), cropped_image.size, cropped_image.mode).convert_alpha()
        transparent_image = cropped_image
        transparent_image.putalpha(100)
        self.fainted_surface = pygame.image.fromstring(transparent_image.tobytes(), transparent_image.size, transparent_image.mode).convert_alpha()

    def on_cooldown(self, move_id):
        self.cooldowns[move_id] = self.moves[move_id].cooldown

    def tick_cooldowns(self):
        for i, cooldown in enumerate(self.cooldowns):
            if cooldown > 0:
                self.cooldowns[i] -= 1
            elif cooldown < 0:
                self.cooldowns[i] = 0

    def get_type_matchup(self, pkmn_type):
        damage_mod = 1
        for t in self.types:
            if pkmn_type in t.immunities:
                return 0.25

    def is_fainted(self):
        if self.hp < 0:
            self.hp = 0
        return self.hp == 0

    def is_intangible(self):
        return self.intangibility > 0 or self.in_hitstop() or self.is_fainted()

    def is_invulnerabile(self):
        return self.invulnerability > 0 or self.in_hitstop() or self.is_fainted()

    def in_hitstop(self):
        return self.hitstop > 0

    def tick_invulnerability(self, time=1):
        if self.invulnerability > 0:
            self.invulnerability -= time
        if self.invulnerability < 0:
            self.invulnerability = 0

    def tick_intangibility(self, time=1):
        if self.intangibility > 0:
            self.intangibility -= time
        if self.intangibility < 0:
            self.intangibility = 0

    def get_hp(self):
        return hp_formula(self.base_stats["HP"], self.level)

    def apply_stat_modifications(self, effect_type, stat):
        for effect in self.effects:
            if effect_type in effect.effect_types:
                stat = effect.activate(effect_type, stat)
        return stat

    def get_attack(self):
        attack = other_stat_formula(self.base_stats["ATK"], self.level)
        return self.apply_stat_modifications(EffectTypes.ATTACK_MODIFICATION, attack)
        
    def get_defense(self):
        defense = other_stat_formula(self.base_stats["DEF"], self.level)
        return self.apply_stat_modifications(EffectTypes.DEFENSE_MODIFICATION, defense)

    def get_special_attack(self):
        special_attack = other_stat_formula(self.base_stats["SPA"], self.level)
        return self.apply_stat_modifications(EffectTypes.SPECIAL_ATTACK_MODIFICATION, special_attack)

    def get_special_defense(self):
        special_defense = other_stat_formula(self.base_stats["SPD"], self.level)
        return self.apply_stat_modifications(EffectTypes.SPECIAL_DEFENSE_MODIFICATION, special_defense)

    def get_speed(self):
        speed = speed_formula(self.base_stats["SPE"], self.level)
        return self.apply_stat_modifications(EffectTypes.SPEED_MODIFICATION, speed)

    def get_acceleration(self):
        return self.apply_stat_modifications(EffectTypes.ACCELERATION_MODIFICATION, self.acceleration)

    def get_drag(self):
        return self.apply_stat_modifications(EffectTypes.DRAG_MODIFICATION, self.drag)

    def update_current_speed(self):
        speed = self.get_speed()
        if self.current_speed < speed:
            speed_mod = self.get_acceleration()
        else:
            speed_mod = self.get_drag()
        self.current_speed += (speed - self.current_speed) * speed_mod
        self.velocity = (self.velocity / np.linalg.norm(self.velocity)) * self.game.scale_to_fps(self.current_speed)

    def attack(self, target):
        pass

    # Lina functions start here
    def is_colliding(self, other):
        distance = np.linalg.norm(self.position - other.position)
        return distance < (self.radius + other.radius)

    def closest_point_on_segment(self, p1, p2, p):
        line = p2 - p1
        length_squared = np.dot(line, line)
        if length_squared == 0:
            return p1
        t = np.dot(p - p1, line) / length_squared
        t = max(0, min(1, t))
        return p1 + t * line

    def collide_with_wall(self, wall):
        p1 = np.array([wall["x1"], wall["y1"]], dtype=float)
        p2 = np.array([wall["x2"], wall["y2"]], dtype=float)
        closest = self.closest_point_on_segment(p1, p2, self.position)
        normal = np.array([wall["nx"], wall["ny"]], dtype=float)
        dist = np.linalg.norm(self.position - closest)
        if dist < self.radius and np.dot(self.velocity, normal) < 0:
            self.velocity -= 2 * np.dot(self.velocity, normal) * normal

            overlap = self.radius - dist
            self.position += normal * overlap

    def resolve_collision(self, other):
        o1 = self.position
        o2 = other.position

        v1 = self.velocity
        v2 = other.velocity

        axis = (o1 - o2) / np.linalg.norm(o1 - o2)

        v1_ = axis * np.linalg.norm(v1)
        v2_ = -axis * np.linalg.norm(v2)

        self.velocity = v1_
        other.velocity = v2_

        overlap = (self.radius + other.radius) - np.linalg.norm(o1 - o2)
        if overlap > 0:
            self.position += axis * (overlap / 2)
            other.position -= axis * (overlap / 2)
    # Lina functions end here

    def update(self):
        if self.in_hitstop():
            self.hitstop -= 1
        else:
            self.tick_intangibility()
            self.tick_invulnerability()
            self.update_current_speed()
        self.tick_cooldowns()

    def move(self):
        if self.in_hitstop() or self.is_fainted():
            return
        for wall in self.game.walls:
            self.collide_with_wall(wall)
        self.position += self.velocity

    def draw(self):
        if self.is_fainted():
            surface = self.fainted_surface
        else:
            surface = self.surface
        surface_rect = surface.get_rect()
        surface_rect.center = (self.position[0], self.position[1])
        self.game.screen.blit(surface, surface_rect)



class Move:
    def __init__(self, name, pkmn_type, cooldown):
        self.name = name
        self.type = pkmn_type
        self.cooldown = cooldown

    def on_use(self, user, **kwargs):
       self.send_message(f"{user.name} used {self.name}!")

    def send_message(self, text):
        print(text)


class BasicAttack(Move):
    def __init__(self, name, power, pkmn_type, hitstun, invulnerability, animation, cooldown):
        super().__init__(name, pkmn_type, cooldown)
        self.power = power
        self.hitstun = hitstun
        self.invulnerability = invulnerability
        self.animation = animation

    def on_use(self, user, **kwargs):
        target = kwargs["target"]
        target.do_damage()

moves = {}