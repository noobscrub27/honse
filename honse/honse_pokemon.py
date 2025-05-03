from io import BytesIO
import pygame
import random
import math
import honse_data
import honse_particles
import enum
from PIL import Image
import numpy as np
import enum

class MoveCategories(enum.Enum):
    PHYSICAL = 0
    SPECIAL = 1
    STATUS = 2

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

def get_type_effectiveness_quote(move, target):
    effectiveness = target.get_type_matchup(move.type)
    if effectiveness > 1:
        return "It's super effective!"
    elif effectiveness == 0.25:
        return "It barely had any effect."
    elif effectiveness < 1:
        return "It's not very effective."
    else:
        return ""


def damage_formula(move, attacker, defender, spread=False):
    if move.category == MoveCategories.PHYSICAL:
        attack = attacker.get_attack()
        defense = defender.get_defense()
    else:
        attack = attacker.get_special_attack()
        defense = defender.get_special_defense()
    damage = ((((((2*attacker.level)/5)+2) * move.power * (attack/defense))/50)+2)
    # spread is only true for the non-primary target of spread moves
    if spread:
        damage *= 0.5
    damage *= defender.get_type_matchup(move.type)
    if move.type in attacker.types:
        damage *= 1.5
    damage *= random.randint(85,100) / 100
    return max(1, math.floor(damage))

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
    "SPE": 5}

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
    for t in type_order:
        pokemon_types[t] = PokemonType(t)
    for i, line in enumerate(lines[1:]):
        current_type = pokemon_types[type_order[i]]
        matchups = line.split(",")[1:]
        for j, matchup in enumerate(matchups):
            if matchup == "0.5":
                pokemon_types[type_order[j]].resistances.append(current_type)
            elif matchup == "2":
                pokemon_types[type_order[j]].weaknesses.append(current_type)
            elif matchup == "0":
                pokemon_types[type_order[j]].immunities.append(current_type)

def speed_formula(base, level, ivs=31, evs=0, nature=1):
    return max(1,15*(base/255))

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
        self.hp = self.get_max_hp()
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
        self.intangible_surface = self.surface.copy()
        self.intangible_surface.fill((255, 255, 255, 190), None, pygame.BLEND_RGBA_MULT)
        self.fainted_surface = self.surface.copy()
        self.fainted_surface.fill((255, 127, 127, 85), None, pygame.BLEND_RGBA_MULT)

    def same_team(self, other):
        return self.team == other.team

    def on_cooldown(self, move_id):
        self.cooldowns[move_id] = self.moves[move_id].cooldown

    def tick_cooldowns(self):
        for i, cooldown in enumerate(self.cooldowns):
            if cooldown > 0:
                self.cooldowns[i] -= 1
            elif cooldown < 0:
                self.cooldowns[i] = 0

    def get_type_matchup(self, pkmn_type):
        damage_numerator = 1
        damage_denominator = 1
        for t in self.types:
            if pkmn_type in t.immunities:
                return 0.25
            elif pkmn_type in t.weaknesses:
                damage_numerator *= 3
                damage_denominator *= 2
            elif pkmn_type in t.resistances:
                damage_numerator *= 2
                damage_denominator *= 3
        return damage_numerator / damage_denominator
        

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

    def get_max_hp(self):
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
        # fainted pokemon should slow down until they stop
        if self.is_fainted():
            if self.current_speed < 1:
                self.current_speed = 0
            else:
                self.current_speed *= 0.95
        else:
            if self.current_speed < speed:
                speed_mod = self.get_acceleration()
            else:
                speed_mod = self.get_drag()
            self.current_speed += (speed - self.current_speed) * speed_mod
        self.current_speed = min(self.current_speed, honse_data.SPEED_CAP)
        self.velocity = (self.velocity / np.linalg.norm(self.velocity)) * self.game.scale_to_fps(self.current_speed)

    def use_move(self, target):
        for i, move in enumerate(self.moves):
            if self.cooldowns[i] == 0:
                success = move.on_use(self, target=target)
                if success:
                    self.on_cooldown(i)
                    return

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
        if self.is_fainted():
            self.cooldowns = [0,0,0,0]
        else:
            self.tick_cooldowns()

    def move(self):
        if self.in_hitstop() or self.current_speed == 0:
            return
        cell_x = int(self.position[0]) // self.game.cell_size
        cell_y = int(self.position[1]) // self.game.cell_size
        # Lina code
        nearby_walls = sum(
            (self.game.wall_grid.get((i,j), []) for i in range (cell_x-1, cell_x+2) for j in range(cell_y-1, cell_y+2)), [])
        for wall in nearby_walls:
            self.collide_with_wall(wall)
        self.position += self.velocity

    def draw(self):
        if self.is_fainted():
            surface = self.fainted_surface
        elif (self.is_intangible() or self.is_invulnerabile()) and not self.in_hitstop():
            surface = self.intangible_surface
        else:
            surface = self.surface
        surface_rect = surface.get_rect()
        surface_rect.center = (self.position[0], self.position[1])
        self.game.screen.blit(surface, surface_rect)



class Move:
    def __init__(self, name, pkmn_type, category, cooldown):
        self.name = name
        self.type = pkmn_type
        self.category = category
        self.cooldown = cooldown

    def on_use(self, user, **kwargs):
       self.send_message(f"{user.name} used {self.name}!")

    def send_message(self, text):
        print(text)


class BasicAttack(Move):
    def __init__(self, name, pkmn_type, category, cooldown, power, hitstop, invulnerability, base_knockback, knockback_scaling):
        super().__init__(name, pkmn_type, category, cooldown)
        self.power = power
        self.hitstop = hitstop
        self.invulnerability = invulnerability
        self.base_knockback = base_knockback
        self.knockback_scaling = knockback_scaling

    def knockback_modifier(self, current_hp, damage):
        # knockback is multiplied by knockback scaling
        # knockback scaling is equal to 1+((knockback_scaling * damage)/current_hp)
        # damage cannot exceed current HP
        # this is also used for hitstop
        knockback_modification = 1 + ((self.knockback_scaling*damage)/current_hp)
        return knockback_modification

    def animation(self, game, x, y):
        for i in range(random.randint(8,12)):
            size = random.randint(8,12)
            x_speed = random.randint(4, 8) * random.choice([-1, 1])
            y_speed = random.randint(4, 8) * random.choice([-1, 1])
            particle = honse_particles.RectParticle(
                x, y, x_speed, y_speed,
                size, size, -0.4, -0.4, random.randint(0,20),
                235, random.randint(100,200), 52, 255, 10)
            
            game.particle_spawner.add_particles(particle)

    def on_use(self, user, **kwargs):
        target = kwargs["target"]
        if target.same_team(user):
            return False
        damage = min(target.hp, damage_formula(self, user, target))
        knockback_mod = self.knockback_modifier(target.hp, damage)
        knockback = self.base_knockback * knockback_mod
        hitstop = int(self.hitstop * knockback_mod)
        target.hp -= damage
        target.hitstop = hitstop
        target.current_speed += knockback
        user.game.display_message(f"{user.name} used {self.name}!", 0, [0,0,0])
        effectiveness_quote = get_type_effectiveness_quote(self, target)
        if effectiveness_quote:
            user.game.display_message(effectiveness_quote, 1, [0,0,0])
        user.game.display_message(f"{target.name} took {damage} damage.", 1, [0,0,0])
        if target.hp <= 0:
            user.game.display_message(f"{target.name} fainted!", 0, [127,0,0])
        self.animation(user.game, target.position[0], target.position[1])
        return True

moves = {
    "Tackle": BasicAttack("Tackle", pokemon_types["Normal"], MoveCategories.PHYSICAL, 150, 45, 4, 0, 10, 1)
    }