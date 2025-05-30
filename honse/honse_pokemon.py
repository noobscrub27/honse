from ast import Dict
from io import BytesIO
from telnetlib import STATUS
import pygame
import random
import math
import honse_data
import honse_particles
import enum
import numpy as np
from PIL import Image, ImageDraw, ImageColor
import os
import json
from dataclasses import dataclass, field
from copy import deepcopy
from typing import Optional

#may break things
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class MoveCategories(enum.Enum):
    PHYSICAL = enum.auto()
    SPECIAL = enum.auto()
    STATUS = enum.auto()

class Weather(enum.Enum):
    CLEAR = enum.auto()
    HARSH_SUNLIGHT = enum.auto()
    RAIN = enum.auto()
    SANDSTORM = enum.auto()
    HAIL = enum.auto()
    EXTREMELY_HARSH_SUNLIGHT = enum.auto()
    HEAVY_RAIN = enum.auto()
    STRONG_WINDS = enum.auto()
    SHADOWY_AURA = enum.auto()

# logistic function that returns the value, in cooldown frames, of a stat stage
# value assumes that it is being inflicted on the opponent
# reminder that positive values = more cooldown
# value gain slows as the stat stage increases, with a asymptotes at -600 and 600
def get_stage_cooldown_value(stage_total):
    MAX_VALUE = 900
    return MAX_VALUE + int((-2*MAX_VALUE)/1+math.exp(-0.5*stage_total))

def stage_to_modifier(stage):
    stage = min(6, max(-6, stage))
    if stage == 0:
        return 1
    elif stage > 0:
        num = 2 + stage
        denom = 2
    else:
        num = 2
        denom = 2 - stage
    return num / denom

def get_type_effectiveness_stuff(move, target):
    effectiveness = target.get_type_matchup(move.type)
    if effectiveness > 1:
        return "It's super effective!", "Hit Super Effective"
    elif effectiveness == 0.25:
        return "It barely had any effect.", "Hit Alt Weak"
    elif effectiveness < 1:
        return "It's not very effective.", "Hit Weak Not Very Effective"
    else:
        return "", "Hit Normal Damage"

def crit_calc(attack, attacker, target):
        crit_stage = attack.move.crit_stage
        damage_mod = 1.5
        # if the crit stage is < 0 at any point in the process, return 1 (normal damage)
        if crit_stage < 0:
            return 1
        if activate_effect(EffectTrigger.CRIT_NEGATION, target, False):
            return 1
        crit_stage = activate_effect(EffectTrigger.CRIT_STAGE_MODIFICATION, attacker, crit_stage)
        if crit_stage < 0:
            return 1
        if crit_stage >= 3:
            return damage_mod
        elif crit_stage == 2:
            return damage_mod if random.random() <= 0.5 else 1
        elif crit_stage == 1:
            return damage_mod if random.random() <= 0.125 else 1
        else:
            return damage_mod if random.random() <= 1/24 else 1

def damage_formula(attack_object, attacker: "Character", defender: "Character"):
    spread = not attack_object.initial_use
    if attack_object.move.category == MoveCategories.PHYSICAL:
        attack_stat = "ATK" if attack_object.attack_stat_override is None else attack_object.attack_stat_override
        defense_stat = "DEF" if attack_object.defense_stat_override is None else attack_object.defense_stat_override
    else:
        attack_stat = "SPA" if attack_object.attack_stat_override is None else attack_object.attack_stat_override
        defense_stat = "SPD" if attack_object.defense_stat_override is None else attack_object.defense_stat_override
    ignore_attack_modifiers = attack_object.ignore_attack_modifiers
    ignore_defense_modifiers = attack_object.ignore_defense_modifiers
    if attack_object.foul_play:
        attack = defender.current_modified_stats[attack_stat]
        unmodified_attack = defender.current_unmodified_stats[attack_stat]
    else:
        attack = attacker.current_modified_stats[attack_stat]
        unmodified_attack = attacker.current_unmodified_stats[attack_stat]
    defense = defender.current_modified_stats[defense_stat]
    unmodified_defense = defender.current_unmodified_stats[defense_stat]
    # logging stuff
    move_text = f"Move: {attack_object.move.name}, Base Power: {attack_object.power}"
    attacker_text = "defender" if attack_object.foul_play else "attacker"
    attack_stat_source = attacker if attacker_text == "attacker" else defender
    attack_header = f"Attack stat: {attacker_text}'s {attack_stat}:"
    attack_text1 = f"\tBase stat: {attack_stat_source.base_stats[attack_stat]}, IV: {attack_stat_source.ivs[attack_stat]}, EV: {attack_stat_source.evs[attack_stat]}, Nature: {attack_stat_source.nature[attack_stat]}, Level: {attack_stat_source.level}"
    attack_text2 = f"\tCompletely unmodified attack: {attack_stat_source.calculate_unmodified_stat(attack_stat)}, Base stat modifiers: {unmodified_attack}, All modifiers: {attack}"
    defense_header = f"Defense stat: defender's {defense_stat}"
    defense_text1 = f"\tBase stat: {defender.base_stats[defense_stat]}, IV: {defender.ivs[defense_stat]}, EV: {defender.evs[defense_stat]}, Nature: {defender.nature[defense_stat]}, Level: {defender.level}"
    defense_text2 = f"\tCompletely unmodified defense: {defender.calculate_unmodified_stat(defense_stat)}, Base stat modifiers: {unmodified_defense}, All modifiers: {defense}"
    attacker_effects = "Attacker effects:"
    if len(attacker.effects):
        for effect in attacker.effects:
            attacker_effects += "\n\t" + str(effect)
    else: attacker_effects += " None"
    defender_effects = "Defender effects:"
    if len(defender.effects):
        for effect in defender.effects:
            defender_effects += "\n\t" + str(effect)
    else: defender_effects += " None"
    if 1 in [attack, unmodified_attack, defense, unmodified_defense]:
        bug_description = "SOMETHING WENT WRONG HERE! STAT VALUE OF 1 DETECTED."
        honse_data.BUG_FINDER.found_bug(bug_description, attacker.game)
        attacker.game.message_log.append([bug_description, False])
    if ignore_attack_modifiers:
        attack = unmodified_attack
    if ignore_defense_modifiers:
        defense = unmodified_defense
    crit_mod = crit_calc(attack_object, attacker, defender)
    if crit_mod > 1:
        attack = max(attack, unmodified_attack)
        defense = min(defense, unmodified_defense)
    initial_damage = (
        ((((2 * attacker.level) / 5) + 2) * attack_object.power * (attack / defense)) / 50
    ) + 2
    # spread is only true for the non-primary target of spread moves
    if spread:
        spread_mod = 0.5
    else:
        spread_mod = 1
    type_effectiveness = defender.get_type_matchup(attack_object.type, attack_object.move.effectiveness_overrides)
    if attack_object.type in attacker.get_types():
        stab_mod = 1.5
    else:
        stab_mod = 1
    random_mod = random.randint(85, 100) / 100
    damage = initial_damage * spread_mod * type_effectiveness * stab_mod * random_mod
    damage =  max(1, math.floor(damage))
    final_stat_text = f"Final attack: {attack}, Final defense: {defense}, Final power: {attack_object.power}, Attacker level: {attacker.level}, Initial damage: {initial_damage}"
    damage_mod_text = f"Spread: {spread_mod}, Effectiveness: {type_effectiveness}, Stab: {stab_mod}, Random: {random_mod}"
    log_text = move_text + "\n" + attacker_effects + "\n" + defender_effects + "\n" + attack_header + "\n" + attack_text1 + "\n" + attack_text2 + "\n" + defense_header + "\n" + defense_text1 + "\n" + defense_text2 + "\n" + final_stat_text + "\n" + damage_mod_text + f"\nDamage: {damage}"
    attacker.game.message_log.append([log_text, False])
    return damage, crit_mod > 1

# when activating an effect, you must include an effect trigger as the first parameter
# the second parameter is a dict of kwargs to provide the activate function
class EffectTrigger(enum.Enum):
    INSTANT = enum.auto()
    STAT_MODIFICATION = enum.auto()
    STAGE_MODIFICATION = enum.auto()
    BASE_STAT_OVERRIDE = enum.auto()
    CRIT_STAGE_MODIFICATION = enum.auto()
    CRIT_DAMAGE_MODIFICATION = enum.auto()
    CRIT_NEGATION = enum.auto()
    ACCELERATION_MODIFICATION = enum.auto()
    DRAG_MODIFICATION = enum.auto()
    MOVE_SPEED_MODIFICATION = enum.auto()
    # end of turn effects will trigger on their own. do not trigger end of turn effects with activate_effect
    END_OF_TURN = enum.auto()
    MOVE_LOCK = enum.auto()
    ON_TRY_USE_MOVE = enum.auto()
    ON_USE_MOVE = enum.auto()
    ON_LANDING_MOVE = enum.auto()
    ON_HIT_BY_MOVE = enum.auto()
    AFTER_USE_MOVE = enum.auto()
    # this does not trigger whenever a move goes on cooldown
    # it only triggers when a move goes on cooldown after it was used
    # this is primarily for effects that modify the cooldown of the move that was just used
    AFTER_MOVE_COOLDOWN = enum.auto()
    MOVE_OVERRIDE = enum.auto()
    TYPE_OVERRIDE = enum.auto()
    TYPE_ADDITION = enum.auto()

# tags are used for effects that block or override other effects
# effects that block or override other effects decide whether to do so based on tags
class EffectTag(enum.Enum):
    NON_VOLATILE = enum.auto()
    BASE_ATTACK_OVERRIDE = enum.auto()
    BASE_DEFENSE_OVERRIDE = enum.auto()
    BASE_SPECIAL_ATTACK_OVERRIDE = enum.auto()
    BASE_SPECIAL_DEFENSE_OVERRIDE = enum.auto()
    BASE_SPEED_OVERRIDE = enum.auto()
    LEECH_SEED = enum.auto()
    CONFUSION = enum.auto()
    ROLLOUT = enum.auto()
    TYPE_OVERRIDE = enum.auto()

# most effects work by taking an input, modifying it, and returning an output
# for example, stat modifications take an input (the stat), modify it, and return the changed stat as an output
# however, there are a few effects that don't work this way
# for example, effects that do damage every N frames (end of turn effects) usually (if ever) need to return a result
def activate_effect(effect_trigger: EffectTrigger, character: "Character", starting_value=None, effect_kwargs:Optional[dict]=None):
    effect_kwargs = {} if effect_kwargs is None else effect_kwargs
    result = starting_value
    for effect in character.effects:
        if effect_trigger in effect.triggers:
            result = effect.activate(effect_trigger, result, **effect_kwargs)
    return result

STAT_NAMES = {
    "HP": "HP",
    "ATK": "Attack",
    "DEF": "Defense",
    "SPA": "Special Attack",
    "SPD": "Special Defense",
    "SPE": "Speed"}

stats = {"HP": 100, "ATK": 100, "DEF": 100, "SPA": 100, "SPD": 100, "SPE": 5}

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
    type_order = [t.strip() for t in type_order]
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
# this will be read from a file later
# but pokemon types will need to be redone once integrated into saurbot anyway
pokemon_types["Normal"].cooldown_modifier = 1
pokemon_types["Fighting"].cooldown_modifier = 0.9
pokemon_types["Flying"].cooldown_modifier = 0.8
pokemon_types["Poison"].cooldown_modifier = 1.1
pokemon_types["Ground"].cooldown_modifier = 1.1
pokemon_types["Rock"].cooldown_modifier = 1.1
pokemon_types["Bug"].cooldown_modifier = 0.9
pokemon_types["Ghost"].cooldown_modifier = 0.9
pokemon_types["Steel"].cooldown_modifier = 1.2
pokemon_types["Fire"].cooldown_modifier = 0.9
pokemon_types["Water"].cooldown_modifier = 1
pokemon_types["Grass"].cooldown_modifier = 1.1
pokemon_types["Electric"].cooldown_modifier = 0.8
pokemon_types["Psychic"].cooldown_modifier = 1
pokemon_types["Ice"].cooldown_modifier = 1.2
pokemon_types["Dragon"].cooldown_modifier = 1.1
pokemon_types["Dark"].cooldown_modifier = 1
pokemon_types["Fairy"].cooldown_modifier = 1
pokemon_types["Shadow"].cooldown_modifier = 0.7
pokemon_types["Typeless"].cooldown_modifier = 1

# the base knockback for a 100 BP move in speed units applied
pokemon_types["Normal"].base_knockback = 8
pokemon_types["Fighting"].base_knockback = 9
pokemon_types["Flying"].base_knockback = 10
pokemon_types["Poison"].base_knockback = 7
pokemon_types["Ground"].base_knockback = 9
pokemon_types["Rock"].base_knockback = 9
pokemon_types["Bug"].base_knockback = 7
pokemon_types["Ghost"].base_knockback = 6
pokemon_types["Steel"].base_knockback = 9
pokemon_types["Fire"].base_knockback = 8
pokemon_types["Water"].base_knockback = 10
pokemon_types["Grass"].base_knockback = 8
pokemon_types["Electric"].base_knockback = 7
pokemon_types["Psychic"].base_knockback = 7
pokemon_types["Ice"].base_knockback = 6
pokemon_types["Dragon"].base_knockback = 9
pokemon_types["Dark"].base_knockback = 8
pokemon_types["Fairy"].base_knockback = 7
pokemon_types["Shadow"].base_knockback = 12
pokemon_types["Typeless"].base_knockback = 8

pokemon_types["Normal"].default_hitstop = 8
pokemon_types["Fighting"].default_hitstop = 20
pokemon_types["Flying"].default_hitstop = 8
pokemon_types["Poison"].default_hitstop = 8
pokemon_types["Ground"].default_hitstop = 8
pokemon_types["Rock"].default_hitstop = 8
pokemon_types["Bug"].default_hitstop = 8
pokemon_types["Ghost"].default_hitstop = 8
pokemon_types["Steel"].default_hitstop = 8
pokemon_types["Fire"].default_hitstop = 20
pokemon_types["Water"].default_hitstop = 35
pokemon_types["Grass"].default_hitstop = 25
pokemon_types["Electric"].default_hitstop = 50
pokemon_types["Psychic"].default_hitstop = 20
pokemon_types["Ice"].default_hitstop = 80
pokemon_types["Dragon"].default_hitstop = 8
pokemon_types["Dark"].default_hitstop = 8
pokemon_types["Fairy"].default_hitstop = 8
pokemon_types["Shadow"].default_hitstop = 8
pokemon_types["Typeless"].default_hitstop = 8

pokemon_types["Normal"].default_animation = honse_particles.large_impact_animation
pokemon_types["Fighting"].default_animation = honse_particles.punch_spawner_animation
pokemon_types["Flying"].default_animation = honse_particles.large_impact_animation
pokemon_types["Poison"].default_animation = honse_particles.large_impact_animation
pokemon_types["Ground"].default_animation = honse_particles.large_impact_animation
pokemon_types["Rock"].default_animation = honse_particles.large_impact_animation
pokemon_types["Bug"].default_animation = honse_particles.large_impact_animation
pokemon_types["Ghost"].default_animation = honse_particles.large_impact_animation
pokemon_types["Steel"].default_animation = honse_particles.large_impact_animation
pokemon_types["Fire"].default_animation = honse_particles.flame_animation
pokemon_types["Water"].default_animation = honse_particles.droplet_animation
pokemon_types["Grass"].default_animation = honse_particles.razor_leaf_animation
pokemon_types["Electric"].default_animation = honse_particles.bolt_animation
pokemon_types["Psychic"].default_animation = honse_particles.psychic_animation
pokemon_types["Ice"].default_animation = honse_particles.ice_animation
pokemon_types["Dragon"].default_animation = honse_particles.large_impact_animation
pokemon_types["Dark"].default_animation = honse_particles.large_impact_animation
pokemon_types["Fairy"].default_animation = honse_particles.large_impact_animation
pokemon_types["Shadow"].default_animation = honse_particles.large_impact_animation
pokemon_types["Typeless"].default_animation = honse_particles.large_impact_animation

pokemon_types["Normal"].sound = "Tackle"
pokemon_types["Fighting"].sound = "Close Combat"
pokemon_types["Flying"].sound = "Tackle"
pokemon_types["Poison"].sound = "Tackle"
pokemon_types["Ground"].sound = "Tackle"
pokemon_types["Rock"].sound = "Tackle"
pokemon_types["Bug"].sound = "Tackle"
pokemon_types["Ghost"].sound = "Tackle"
pokemon_types["Steel"].sound = "Tackle"
pokemon_types["Fire"].sound = "Ember"
pokemon_types["Water"].sound = "Water Gun"
pokemon_types["Grass"].sound = "Razor Leaf"
pokemon_types["Electric"].sound = "Zap Cannon"
pokemon_types["Psychic"].sound = "Confusion"
pokemon_types["Ice"].sound = "Ice Ball"
pokemon_types["Dragon"].sound = "Tackle"
pokemon_types["Dark"].sound = "Tackle"
pokemon_types["Fairy"].sound = "Tackle"
pokemon_types["Shadow"].sound = "Tackle"
pokemon_types["Typeless"].sound = "Tackle"

def get_type_color(color):
    rgb = ImageColor.getcolor(color, "RGB")
    return (rgb[0], rgb[1], rgb[2], 127)

pokemon_types["Bug"].hazard_color = get_type_color("#A8B820")
pokemon_types["Dark"].hazard_color = get_type_color("#705848")
pokemon_types["Dragon"].hazard_color = get_type_color("#7038F8")
pokemon_types["Electric"].hazard_color = get_type_color("#F8D030")
pokemon_types["Fairy"].hazard_color = get_type_color("#EE99AC")
pokemon_types["Fighting"].hazard_color = get_type_color("#C03028")
pokemon_types["Fire"].hazard_color = get_type_color("#F08030")
pokemon_types["Flying"].hazard_color = get_type_color("#A890F0")
pokemon_types["Ghost"].hazard_color = get_type_color("#705898")
pokemon_types["Grass"].hazard_color = get_type_color("#78C850")
pokemon_types["Ground"].hazard_color = get_type_color("#E0C068")
pokemon_types["Ice"].hazard_color = get_type_color("#98D8D8")
pokemon_types["Normal"].hazard_color = get_type_color("#A8A878")
pokemon_types["Poison"].hazard_color = get_type_color("#A040A0")
pokemon_types["Psychic"].hazard_color = get_type_color("#F85888")
pokemon_types["Rock"].hazard_color = get_type_color("#B8A038")
pokemon_types["Steel"].hazard_color = get_type_color("#D1D1E0")
pokemon_types["Water"].hazard_color = get_type_color("#6890F0")
pokemon_types["Shadow"].hazard_color = get_type_color("#42357D")
pokemon_types["Typeless"].hazard_color = get_type_color("#FFFFFF")

ENVIRONMENTS = {
    "indoors": pokemon_types["Normal"],
    "sand": pokemon_types["Ground"],
    "cave": pokemon_types["Rock"],
    "grass": pokemon_types["Grass"],
    "water": pokemon_types["Water"]
    }

def speed_formula(base):
    return 15 * (base / 255)

def hp_formula(base, level, ivs, evs):
    return (
        math.floor(((2 * base + ivs + math.floor(evs / 4)) * level) / 100) + level + 10
    )

def other_stat_formula(base, level, ivs, evs, nature):
    return math.floor(
        (math.floor(((2 * base + ivs + math.floor(evs / 4)) * level) / 100) + 5)
        * nature
    )

@dataclass
class EffectOptions:
    lifetime: int = 1200
class EffectInterface:
    # lifetime default value is 24 hours in frames. effectively infinite for the purposes of this program
    def __init__(self,
                 game=None,
                 source=None,
                 inflicted_by=None,
                 inflicted_upon=None,
                 lifetime: int = 5184000
                 ):
        self.text_size = 16
        self.game = game
        self.inflicted_by = inflicted_by
        self.inflicted_upon = inflicted_upon
        self.lifetime_lived = 0
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.source = source
        # all None for these arguments means this effect was just created to call get_effect_value for the purpose of calculating move cooldowns
        if game is None and source is None and inflicted_by is None and inflicted_upon is None:
            self.success = False
        else:
            self.success = self.infliction()

    # each effect has a way of assigning itself an effect value
    # the effect value is a representation of how powerful an effect is
    # a high positive effect value represents an effect that is very detremental to whoever has that status
    # a high negative effect value represents an effect that is very benefitial to whoever has that status
    # effect value is used to modify cooldowns for moves
    # in general, 1 effect value = 1 frame longer cooldown
    def get_effect_value(self):
        return 0

    # checks if it can be inflicted
    def can_inflict(self):
        for effect in self.inflicted_upon.effects:
            blocked_effects = [tag for tag in self.tags if tag in effect.blocks]
            if len(blocked_effects):
                return False
        return True

    def infliction(self):
        success = False
        if self.can_inflict():
            if EffectTrigger.INSTANT in self.triggers:
                self.instant_effect()
                success = True
            else:
                success = self.inflicted_upon.inflict_status(self)
        if success:
            self.after_infliction()
        return success

    def instant_effect(self):
        pass

    def after_infliction(self):
        if len(self.overrides):
            for effect in self.inflicted_upon.effects:
                if effect is self:
                    continue
                overridden_effects = [tag for tag in effect.tags if tag in self.overrides]
                if len(overridden_effects):
                    effect.end_effect()

    def display_inflicted_message(self):
        pass

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        return input_value

    def update(self):
        self.lifetime_lived += 1
        if self.lifetime <= 0:
            self.end_effect()
        else:
            self.lifetime -= 1

    def end_of_turn(self):
        pass

    def end_effect(self):
        self.inflicted_upon.remove_status(self)

    def __str__(self):
        return f"{self.name} inflicted on {self.inflicted_upon.name} by {self.inflicted_by.name}'s {self.source.move.name}. Tags: {self.tags}"

@dataclass
class LeechSeedEffectOptions:
    lifetime: int = 1800,
    damage: float = 1/32,
    cooldown: int = 225,
    grass_immune: bool = True
class LeechSeedEffect(EffectInterface):
    def __init__(self,
             options: LeechSeedEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "LeechSeedEffect"
        self.status_icon = "seeded"
        self.damage = options.damage # decimal representing portion of max hp
        self.damage_cooldown = options.cooldown
        self.max_damage_cooldown = options.cooldown
        self.grass_immune = options.grass_immune
        self.triggers = [EffectTrigger.END_OF_TURN]
        self.tags = [EffectTag.LEECH_SEED]
        self.blocks = [EffectTag.LEECH_SEED]
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return 600

    def can_inflict(self):
        if self.grass_immune and pokemon_types["Grass"] in self.inflicted_upon.get_types():
            return False
        return super().can_inflict()

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} was seeded!", self.text_size, [0, 0, 0])

    def end_of_turn(self):
        if self.inflicted_by.is_fainted():
            self.lifetime = 0
        else:
            self.damage_cooldown -= 1
            if self.damage_cooldown <= 0 and not self.inflicted_upon.is_fainted():
                self.activate(EffectTrigger.END_OF_TURN, None)
                self.damage_cooldown = self.max_damage_cooldown

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.END_OF_TURN:
            self.game.display_message(f"{self.inflicted_upon.name}'s health is sapped by Leech Seed!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            healing = self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
            self.inflicted_by.do_healing(self.inflicted_by, healing, silent=True)
        return input_value

@dataclass
class DamagingNonVolatileEffectOptions:
    lifetime: int = 1800
    damage: float = 1/32
    damage_growth: float = 0
    cooldown: int = 300
    badly_poisoned: bool = False

POISON_DEFAULT_OPTIONS = DamagingNonVolatileEffectOptions(damage=1/16)
TOXIC_DEFAULT_OPTIONS = DamagingNonVolatileEffectOptions(damage=1/64, damage_growth=1/64, cooldown=225, badly_poisoned=True)
class BurnEffect(EffectInterface):
    def __init__(self,
             options: DamagingNonVolatileEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.status_icon = "burn"
        self.name = "BurnEffect"
        self.damage = options.damage # decimal representing portion of max hp
        self.damage_cooldown = options.cooldown
        self.max_damage_cooldown = options.cooldown
        self.stats = {"ATK": 0.5}
        self.triggers = [
            EffectTrigger.END_OF_TURN,
            EffectTrigger.STAT_MODIFICATION
            ]
        self.tags = [EffectTag.NON_VOLATILE]
        self.blocks = [EffectTag.NON_VOLATILE]
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        damage = self.damage * (self.max_lifetime / self.max_damage_cooldown)
        return honse_data.MAX_EFFECT_VALUE * damage

    def can_inflict(self):
        if pokemon_types["Fire"] in self.inflicted_upon.get_types():
            return False
        return super().can_inflict()

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} was burned!", self.text_size, [0, 0, 0])

    def end_of_turn(self):
        self.damage_cooldown -= 1
        if self.damage_cooldown <= 0 and not self.inflicted_upon.is_fainted():
            self.activate(EffectTrigger.END_OF_TURN, None)
            self.damage_cooldown = self.max_damage_cooldown

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.END_OF_TURN:
            self.game.display_message(f"{self.inflicted_upon.name} is hurt by its burn!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
        elif effect == EffectTrigger.STAT_MODIFICATION:
            stat = kwargs["stat"]
            if stat in self.stats:
                return int(input_value * self.stats[stat])
        return input_value

THAW_ON_USE = [
    "Flame Wheel",
    "Sacred Fire",
    "Flare Blitz",
    "Fusion Flare",
    "Scald",
    "Steam Eruption",
    "Burn Up"
    ]
THAW_ON_HIT = [
    "Scald",
    "Steam Eruption"
    ]

class FreezeEffect(EffectInterface):
    def __init__(self,
             options: DamagingNonVolatileEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.status_icon = "freeze"
        self.name = "FreezeEffect"
        self.damage = options.damage # decimal representing portion of max hp
        self.damage_cooldown = options.cooldown
        self.max_damage_cooldown = options.cooldown
        self.stats = {"SPA": 0.5}
        self.triggers = [
            EffectTrigger.END_OF_TURN,
            EffectTrigger.STAT_MODIFICATION
            ]
        self.tags = [EffectTag.NON_VOLATILE]
        self.blocks = [EffectTag.NON_VOLATILE]
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return 600

    def can_inflict(self):
        if pokemon_types["Ice"] in self.inflicted_upon.get_types() or self.game.weather == Weather.HARSH_SUNLIGHT:
            return False
        return super().can_inflict()

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} was frozen!", self.text_size, [0, 0, 0])

    def end_of_turn(self):
        self.damage_cooldown -= 1
        if self.damage_cooldown <= 0 and not self.inflicted_upon.is_fainted():
            self.activate(EffectTrigger.END_OF_TURN, None)
            self.damage_cooldown = self.max_damage_cooldown

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.END_OF_TURN:
            self.game.display_message(f"{self.inflicted_upon.name} is hurt by its frostbite!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
        elif effect == EffectTrigger.STAT_MODIFICATION:
            stat = kwargs["stat"]
            if stat in self.stats:
                return int(input_value * self.stats[stat])
            return input_value
        elif effect == EffectTrigger.ON_HIT_BY_MOVE:
            attack = kwargs["attack"]
            if attack.type.name == "Fire" or attack.move.name in THAW_ON_HIT:
                self.game.display_message(f"{self.inflicted_upon.name} was thawed!", self.text_size, [0, 0, 0])
                self.end_effect()
        elif effect == EffectTrigger.ON_USE_MOVE:
            attack = kwargs["attack"]
            if attack.move.name in THAW_ON_USE:
                self.game.display_message(f"{self.inflicted_upon.name} was thawed!", self.text_size, [0, 0, 0])
                self.end_effect()
        return input_value

class PoisonEffect(EffectInterface):
    def __init__(self,
             options: DamagingNonVolatileEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.status_icon = "toxic" if options.badly_poisoned else "poison"
        self.badly_poisoned = options.badly_poisoned
        self.name = "PoisonEffect"
        self.damage = options.damage # decimal representing portion of max hp
        self.damage_growth = options.damage_growth
        self.current_damage = self.damage
        self.damage_cooldown = options.cooldown
        self.max_damage_cooldown = options.cooldown
        self.triggers = [EffectTrigger.END_OF_TURN]
        self.tags = [EffectTag.NON_VOLATILE]
        self.blocks = [EffectTag.NON_VOLATILE]
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return 600

    def can_inflict(self):
        if pokemon_types["Poison"] in self.inflicted_upon.get_types() or pokemon_types["Steel"] in self.inflicted_upon.get_types():
            return False
        return super().can_inflict()

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        status_name = "badly poisoned" if self.badly_poisoned else "poisoned"
        self.game.display_message(f"{self.inflicted_upon.name} was {status_name}!", self.text_size, [0, 0, 0])

    def end_of_turn(self):
        self.damage_cooldown -= 1
        if self.damage_cooldown <= 0 and not self.inflicted_upon.is_fainted():
            self.activate(EffectTrigger.END_OF_TURN, None)
            self.damage_cooldown = self.max_damage_cooldown

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.END_OF_TURN:
            self.game.display_message(f"{self.inflicted_upon.name} is hurt by its poison!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.current_damage
            damage = min(damage, self.inflicted_upon.hp)
            self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
            self.current_damage += self.damage_growth
        return input_value

class ParalysisEffect(EffectInterface):
    def __init__(self,
             options: DamagingNonVolatileEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.status_icon = "paralysis"
        self.name = "ParalysisEffect"
        self.damage = options.damage # decimal representing portion of max hp
        self.stats = {"SPE": 0.5}
        self.move_speed_modifier = 0.5
        self.triggers = [
            EffectTrigger.AFTER_USE_MOVE,
            EffectTrigger.STAT_MODIFICATION,
            EffectTrigger.MOVE_SPEED_MODIFICATION
            ]
        self.tags = [EffectTag.NON_VOLATILE]
        self.blocks = [EffectTag.NON_VOLATILE]
        self.overrides = []
        super().__init__(game, source, inflicted_by, inflicted_upon, lifetime=options.lifetime)
        
    def get_effect_value(self):
        return 600

    def can_inflict(self):
        inflicted_upon_types = self.inflicted_upon.get_types()
        if pokemon_types["Electric"] in inflicted_upon_types:
            return False
        if pokemon_types["Ground"] in inflicted_upon_types and type(self.source) == Move and self.source.type == pokemon_types["Electric"]:
            return False
        return super().can_inflict()

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} was paralyzed!", self.text_size, [0, 0, 0])

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.AFTER_USE_MOVE:
            self.game.display_message(f"{self.inflicted_upon.name} is hurt by its paralysis!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
        elif effect == EffectTrigger.STAT_MODIFICATION:
            stat = kwargs["stat"]
            if stat in self.stats:
                return int(input_value * self.stats[stat])
            return input_value
        elif effect == EffectTrigger.MOVE_SPEED_MODIFICATION:
            return input_value * self.move_speed_modifier
        return input_value

class ConfusionEffect(EffectInterface):
    def __init__(self,
             options: EffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "ConfusionEffect"
        self.status_icon = "confused"
        self.confusion_chance = 1/3
        self.triggers = [EffectTrigger.ON_TRY_USE_MOVE]
        self.tags = [EffectTag.CONFUSION]
        self.blocks = [EffectTag.CONFUSION]
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)
        
    def get_effect_value(self):
        return 600

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} became confused!", self.text_size, [0, 0, 0])

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.ON_TRY_USE_MOVE:
            self.game.display_message(f"{self.inflicted_upon.name} is confused!", self.text_size, [0, 0, 0])
            if random.random() <= self.confusion_chance:
                self.game.display_message(f"It hurt itself in confusion!", self.text_size, [0, 0, 0])
                attack = Attack(UNOBTAINABLE_MOVES["confusion damage"], self.inflicted_upon, self.inflicted_upon, True)
                damage, crit = damage_formula(attack, self.inflicted_upon, self.inflicted_upon)
                self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
                return False
            else:
                return True
        return input_value

@dataclass
class SleepEffectOptions:
    min_lifetime = 450
    max_lifetime = 1350
class SleepEffect(EffectInterface):
    def __init__(self,
             options: SleepEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "SleepEffect"
        self.status_icon = "sleep"
        self.triggers = [EffectTrigger.MOVE_LOCK]
        self.tags = [EffectTag.NON_VOLATILE]
        self.blocks = [EffectTag.NON_VOLATILE]
        self.overrides = []
        lifetime = random.randint(options.min_lifetime, options.max_lifetime)
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=lifetime)

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()
        
    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} fell asleep!", self.text_size, [0, 0, 0])

    def get_effect_value(self):
        # having the recharge status decrease cooldowns for being a negative status feels weird, so this is 0
        return 0

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.MOVE_LOCK:
            return True
        return input_value

class MustRechargeEffect(EffectInterface):
    def __init__(self,
             options: EffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "MustRechargeEffect"
        self.status_icon = "locked move"
        self.triggers = [EffectTrigger.MOVE_LOCK]
        self.tags = []
        self.blocks = []
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()
        
    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} must recharge!", self.text_size, [0, 0, 0])

    def get_effect_value(self):
        # having the recharge status decrease cooldowns for being a negative status feels weird, so this is 0
        return 0

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.MOVE_LOCK:
            return True
        return input_value

@dataclass
class StatOptions:
    positive: bool
    lifetime: int = 1200
    stats: dict = field(default_factory=dict)
    
class StatStageEffect(EffectInterface):
    def __init__(self,
             options: StatOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "StatStageEffect"
        if options.positive:
            self.status_icon = "stat boost"
        else:
            self.status_icon = "stat drop"
        self.stats = options.stats
        self.triggers = [EffectTrigger.STAGE_MODIFICATION]
        self.tags = []
        self.blocks = []
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        stage_total = sum(list(self.stats.values()))
        return get_stage_cooldown_value(stage_total)

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        for stat, stage in self.stats.items():
            if stage < 0:
                boost_descriptor = "fell"
                if stage == -2:
                    boost_descriptor += " harshly"
                elif stage <= -3:
                    boost_descriptor += "severely"
            else:
                boost_descriptor = "rose"
                if stage == 2:
                    boost_descriptor += " sharply"
                elif stage >= 3:
                    boost_descriptor += "drastically"
            self.game.display_message(f"{self.inflicted_upon.name}'s {STAT_NAMES[stat].lower()} {boost_descriptor}!", self.text_size, [0, 0, 0])

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.STAT_MODIFICATION:
            stat = kwargs["stat"]
            if stat in self.stats:
                return int(input_value * self.stats[stat])
        return input_value

@dataclass
class MoveSpeedModificationEffectOptions:
    modifier: float
    lifetime: int = 1200
    
class MoveSpeedModificationEffect(EffectInterface):
    def __init__(self,
            options: MoveSpeedModificationEffectOptions,
            game=None,
            source=None,
            inflicted_by=None,
            inflicted_upon=None
            ):
        self.name = "MoveSpeedModificationEffect"
        self.modifier = options.modifier
        if self.modifier >= 1:
            self.status_icon = "stat boost"
        else:
            self.status_icon = "stat drop"
        self.triggers = [EffectTrigger.MOVE_SPEED_MODIFICATION]
        self.tags = []
        self.blocks = []
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        if self.modifier < 1:
            return 1/self.modifier * self.max_lifetime / 4
        else:
            return self.modifier * self.max_lifetime / -4

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        if self.modifier < 1:
            boost_descriptor = "slowed"
        else:
            boost_descriptor = "hastened"
        self.game.display_message(f"{self.inflicted_upon.name} was {boost_descriptor}!", self.text_size, [0, 0, 0])

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.MOVE_SPEED_MODIFICATION:
            return input_value * self.modifer
        return input_value

@dataclass
class CooldownReductionEffectOptions:
    cooldown_reduction_amount: int
# reduces all cooldowns by a flat amount, then wears off
class CooldownReductionEffect(EffectInterface):
    def __init__(self,
         options: CooldownReductionEffectOptions,
         game=None,
         source=None,
         inflicted_by=None,
         inflicted_upon=None
         ):
        self.name = "CooldownReductionEffect"
        self.status_icon = ""
        self.triggers = [EffectTrigger.INSTANT]
        self.tags = []
        self.blocks = []
        self.overrides = []
        self.reduction_amount = options.cooldown_reduction_amount
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=0)
        
    def get_effect_value(self):
        return int(-2.25 * self.reduction_amount)

    def instant_effect(self):
        self.display_inflicted_message()
        self.inflicted_upon.tick_cooldowns(self.reduction_amount)

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name}'s cooldowns were reduced!", self.text_size, [0, 0, 0])
        

# inflicts a random stat buff
class AcupressureEffect(EffectInterface):
    def __init__(self,
        options: EffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        self.name = "AcupressureEffect"
        self.stat_buff_lifetime = options.lifetime
        self.status_icon = ""
        self.triggers = [EffectTrigger.INSTANT]
        self.tags = []
        self.blocks = []
        self.overrides = []
        self.reduction_amount = options.cooldown_reduction_amount
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=0)
        
    def get_effect_value(self):
        # i feel like this is worth less tahn 2 stages since you cant choose where it goes
        return get_stage_cooldown_value(1)

    def display_inflicted_message(self):
        pass

    def instant_effect(self):
        self.display_inflicted_message()
        self.inflicted_upon.tick_cooldowns(self.reduction_amount)

    def infliction(self):
        self.display_inflicted_message()
        stat = random.choice("ATK", "DEF", "SPA", "SPD", "SPE")
        stat_stage_options = StatOptions(
            lifetime=self.stat_buff_lifetime,
            stats={stat:2},
            positive=True)
        StatStageEffect(
            options=stat_stage_options,
            game=self.game,
            inflicted_by=self.inflicted_by,
            inflicted_upon=self.inflicted_upon)
        if stat == "SPE":
            move_speed_options = MoveSpeedModificationEffectOptions(
                lifetime=self.stat_buff_lifetime,
                modifier=1.5)
            MoveSpeedModificationEffect(
                options=move_speed_options,
                game=self.game,
                inflicted_by=self.inflicted_by,
                inflicted_upon=self.inflicted_upon)

@dataclass
class HazardClearEffectOptions:
    radius: int
    clear_friendly_hazards: bool
class HazardClearEffect(EffectInterface):
    def __init__(self,
        options: HazardClearEffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        self.name = "HazardClearEffect"
        self.status_icon = ""
        self.triggers = [EffectTrigger.INSTANT]
        self.tags = []
        self.blocks = []
        self.overrides = []
        self.radius = options.radius
        self.clear_friendly_hazards = options.clear_friendly_hazards
        self.hazards_cleared = 0
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=0)
        
    def get_effect_value(self):
        if self.clear_friendly_hazards:
            return -300
        else:
            return -400

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_by.name} cleared away {self.hazards_cleared} nearby hazard{'s' if self.hazards_cleared != 1 else ''}!", self.text_size, [0, 0, 0])

    def instant_effect(self):
        for hazard in self.game.hazards:
            if hazard.defoggable:
                if not self.clear_friendly_hazards and self.inflicted_by.same_team(hazard.inflicted_by):
                    continue
                if np.linalg.norm(self.inflicted_by.position - hazard.position) <= self.radius:
                    hazard.end_effect()
                    self.hazards_cleared += 1
        self.display_inflicted_message()

class AggregateEffect(HazardClearEffect):
    def __init__(self,
        options: HazardClearEffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        super().__init__(options, game, source, inflicted_by, inflicted_upon)

    def instant_effect(self):
        super().instant_effect()
        if self.hazards_cleared > 0:
            healing = self.inflicted_by.max_hp // 4
            self.inflicted_by.do_healing(self.inflicted_by, self.inflicted_by)

class HealBellEffect(EffectInterface):
    def __init__(self,
        options: EffectOptions|None,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        self.name = "HazardClearEffect"
        self.status_icon = ""
        self.triggers = [EffectTrigger.INSTANT]
        self.tags = []
        self.blocks = []
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=0)
        
    def get_effect_value(self):
        return -900

    def instant_effect(self):
        for character in self.game.characters:
            if character.same_team(self.inflicted_by):
                non_volatile_status = character.get_non_volatile_status()
                if non_volatile_status is not None:
                    self.game.display_message(f"{character.name}'s status was cured!", self.text_size, [0, 0, 0])
                    character.remove_status(non_volatile_status)

class BellyDrumEffect(EffectInterface):
    def __init__(self,
        options: EffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        self.name = "BellyDrumEffect"
        self.status_icon = ""
        self.triggers = [EffectTrigger.INSTANT]
        self.tags = []
        self.blocks = []
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=0)
        
    def get_effect_value(self):
        return -1500

    def display_inflicted_message(self):
        pass

    def instant_effect(self):
        damage = self.inflicted_upon.max_hp // 2
        if self.inflicted_upon.hp > damage:
            StatStageEffect(self.game, self.source, self.inflicted_by, self.inflicted_upon, lifetime=honse_data.STAT_BUFF_DURATION, stat="ATK", stage=13)
            DamageEffect(self.game, self.source, self.inflicted_by, self.inflicted_upon, damage=1/2)

@dataclass
class TypeEffectOptions:
    lifetime: int = 1200
    types: list = field(default_factory=list)
class TypeChangeEffect(EffectInterface):
    def __init__(self,
        options: TypeEffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        self.name = "TypeChangeEffect"
        self.status_icon = "type change"
        self.triggers = [EffectTrigger.TYPE_OVERRIDE]
        self.tags = [EffectTag.TYPE_OVERRIDE]
        self.blocks = []
        self.overrides = [EffectTag.TYPE_OVERRIDE]
        self.types = options.types
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return 0

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name}'s type was changed!", self.text_size, [0, 0, 0])

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.TYPE_OVERRIDE:
            return self.types
        return input_value

class CamouflageEffect(TypeChangeEffect):
    def __init__(self,
        options: EffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        if game is None:
            options = TypeEffectOptions(
                lifetime=options.lifetime,
                types=pokemon_types["Normal"])
        else:
            options = TypeEffectOptions(
                lifetime=options.lifetime,
                types=[game.environment_type])
        super().__init__(options, game, source, inflicted_by, inflicted_upon)

@dataclass
class RolloutEffectOptions:
    move_name: str
    lifetime: int = 1800
    
# locks all moves except for the affected move.
# the affected move gets 2x power. this power is double every time the move is used.
# after 5 uses, the effect wears off
class RolloutEffect(EffectInterface):
    def __init__(self,
        options: RolloutEffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        self.name = "RolloutEffect"
        self.status_icon = "locked move"
        self.triggers = [
            EffectTrigger.ON_USE_MOVE,
            EffectTrigger.MOVE_LOCK
            ]
        self.tags = [EffectTag.ROLLOUT]
        self.modifier = 2
        self.blocks = []
        self.overrides = []
        self.affected_move = options.move
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return -90

    def can_inflict(self):
        for effect in self.inflicted_upon.effects:
            if EffectTag.ROLLOUT in effect.tags:
                effect.modifier *= 2
                return False
        return super().can_inflict()

    def update(self):
        if self.modifier > 16:
            self.lifetime = 0
        super().update()

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.MOVE_LOCK:
            move_id = kwargs["move_id"]
            if self.inflicted_upon.get_move(move_id).name != self.affected_move:
                return True
        elif effect == EffectTrigger.ON_USE_MOVE:
            attack = kwargs["attack"]
            if attack.move.name == self.affected_move:
                attack.power *= self.modifier
        return input_value

@dataclass
class DamageEffectOptions:
    damage: float
    percent_of_max_hp_damage: bool
    message: str = ""
    sound: str|None = None
class DamageEffect(EffectInterface):
    def __init__(self,
             options: DamageEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "DamageEffect"
        self.status_icon = ""
        self.triggers = [EffectTrigger.INSTANT]
        self.tags = []
        self.blocks = []
        self.overrides = []
        self.damage = options.damage
        self.percent_of_max_hp_damage = options.percent_of_max_hp_damage
        self.message = options.message
        self.sound = options.sound
        super().__init__(game, source, inflicted_by, inflicted_upon, lifetime=0)
        
    def get_effect_value(self):
        if self.percent_of_max_hp_damage:
            return int(honse_data.MAX_EFFECT_VALUE * self.damage)
        else:
            return min(honse_data.MAX_EFFECT_VALUE, int(self.damage * 10))

    def display_inflicted_message(self):
        if len(self.message):
            try:
                user = self.inflicted_by.name
            except AttributeError:
                user = ""
            message = self.message.replace("USER", user).replace("TARGET", self.inflicted_upon.name)
            self.game.display_message(message, self.text_size, [0, 0, 0])
        
    def instant_effect(self):
        self.display_inflicted_message()
        damage = int(self.inflicted_upon.max_hp * self.damage)
        damage = min(damage, self.inflicted_upon.hp)
        if self.sound is not None:
            self.game.play_sound(self.sound)
        self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)

@dataclass
class MoveEffectOptions:
    move: "Move"
class MoveEffect(EffectInterface):
    def __init__(self,
             options: MoveEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "MoveEffect"
        self.status_icon = ""
        self.triggers = [EffectTrigger.INSTANT]
        self.tags = []
        self.blocks = []
        self.overrides = []
        self.move = options.move
        super().__init__(game, source, inflicted_by, inflicted_upon, lifetime=0)

    def display_inflicted_message(self):
        pass

    def instant_effect(self):
        self.display_inflicted_message()
        self.move.on_use(self.inflicted_by, self.inflicted_upon, False)

@dataclass
class HazardOptions:
    lifetime: int
    effect: ... = None
    effect_options: ... = None
    center_on: ... = None
    hazard_set_radius_growth_time: int = 0
    active_radius_growth_time: int = 0
    active_full_radius_duration: int = 0
    active_cooldown: int = 0
    color: tuple = (0,0,0,127)
    active_color: tuple = (255,255,255,127)
    immune_timer: int = 60
    immune_teams: list = field(default_factory=list)
    immune_pokemon: list = field(default_factory=list)
    removable: bool = False
    knockback: float = 0.01
class Hazard:
    def __init__(self, 
                 options: HazardOptions,
                 position,
                 radius: int,
                 game=None,
                 source=None,
                 inflicted_by: ... = None):
        self.text_size = 16
        self.position = position
        self.effect = options.effect
        self.effect_options = options.effect_options
        self.name = "Hazard"
        self.game = game
        self.inflicted_by = inflicted_by
        self.temporary_immunity = {}
        self.lifetime_lived = 0
        self.lifetime = options.lifetime
        self.max_lifetime = self.lifetime
        self.center_on = options.center_on
        self.radius = radius
        # the number of frames until the hazard displays its radius in full
        self.time_to_full_radius = options.hazard_set_radius_growth_time
        # the number of frames it takes for the active area to grow to the full radius
        self.active_growth_duration = options.active_radius_growth_time
        # the number of frames it stays at full active radius
        self.active_duration = options.active_full_radius_duration
        self.current_active_duration = 0
        # the number of frames the hazard is inactive
        self.active_cooldown = options.active_cooldown
        self.max_active_cooldown = self.active_cooldown
        self.color = options.color
        self.active_color = options.active_color
        self.source = source
        self.immune_timer = options.immune_timer
        self.immune_teams = options.immune_teams
        self.immune_pokemon = options.immune_pokemon
        self.defoggable = options.removable
        # for move effects set knockback to 0.1 or some other low number. it will be basically neglible and just set the direction, while the moves knockback will apply normally
        self.knockback = options.knockback
        self.alive = self.infliction()

    def move(self):
        if self.center_on is not None:
            self.position = self.center_on.position

    def get_radius(self):
        try:
            return int(self.radius * min(1, self.lifetime_lived / self.time_to_full_radius))
        except ZeroDivisionError:
            return int(self.radius)

    def get_active_radius(self):
        try:
            if self.current_active_duration == 0:
                return 0
            return int(self.radius * min(1, self.current_active_duration / self.active_growth_duration))
        except ZeroDivisionError:
            return 0

    def infliction(self):
        success = True
        if success:
            self.game.hazards.append(self)
            self.display_inflicted_message()
        return success

    def display_inflicted_message(self):
        pass

    def can_activate(self, target):
        return not (target in self.immune_pokemon or target in self.temporary_immunity.keys() or target.team in self.immune_teams or target.is_invulnerable()) and self.active_cooldown <= 0 and self.alive

    def activate(self, target):
        self.inflict_knockback(target)
        if self.effect is not None:
            self.effect(self.effect_options, self.game, self.source, self.inflicted_by, target)
        self.temporary_immunity[target] = self.immune_timer

    def update(self):
        self.lifetime_lived += 1
        if self.lifetime_lived >= self.time_to_full_radius:
            if self.active_cooldown <= 0:
                if self.current_active_duration >= self.active_duration + self.active_growth_duration:
                    self.current_active_duration = 0
                    self.active_cooldown = self.max_active_cooldown
                else:
                    self.current_active_duration += 1
            else:
                self.active_cooldown -= 1
        for mon, timer in self.temporary_immunity.items():
            timer -= 1
            if timer <= 0:
                self.temporary_immunity.remove(mon)
        if self.lifetime <= 0:
            self.end_effect()
        else:
            self.lifetime -= 1

    def end_of_turn(self):
        pass

    def end_effect(self):
        self.game.hazards.remove(self)
        self.alive = False

    def draw(self):
        if self.alive:
            radius = self.get_radius()
            if radius > 0:
                self.game.draw_circle(self.position[0], self.position[1], radius, self.color)
            active_radius = self.get_active_radius()
            if active_radius > 0:
                self.game.draw_circle(self.position[0], self.position[1], active_radius, self.active_color)

    def is_colliding(self, target):
        if not target.is_intangible():
            distance = np.linalg.norm(self.position - target.position)
            # using 4/3 * target.radius to see if it makes the collisions look a bit better
            return distance < (self.get_active_radius() + (4 * (target.radius // 3)))

    def inflict_knockback(self, target):
        if self.knockback > 0:
            axis = (self.position - target.position) / np.linalg.norm(self.position - target.position)
            target.velocity = -axis * np.linalg.norm(target.velocity)
            target.current_speed += self.knockback

    def __str__(self):
        return f"{self.name} inflicted at ({self.position[0]}, {self.position[1]}) by {self.inflicted_by.name}'s {self.source.move.name}."

class Character:
    def __init__(
        self, game, name, team, level, stats, moves, types, image, teammate_id
    ):
        self.game = game
        self.npc = False
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
        self.base_stats = stats["base stats"]
        self.evs = stats["evs"]
        self.ivs = stats["ivs"]
        self.nature = stats["nature"]
        self.moves = moves
        self.cooldowns = [0, 0, 0, 0]
        self.types = types
        # speed is pixels/frame
        self.current_speed = 0
        self.direction = random.uniform(0, 359)
        # hitstop, intangibility, and invulnerability are measured in frames
        self.invulnerability = 0
        self.intangibility = 0
        self.hitstop = 0
        # insteading of adding a flat amount, acceleration and drag work changing the speed by a portion of the difference between current speed and target speed
        self.acceleration = 0.1
        self.drag = 0.1
        self.has_non_volatile_status = False
        self.effects = []
        self.max_hp = self.get_max_hp()
        self.hp = self.max_hp
        self.image_name = image
        self.get_image()
        self.hit_sound_to_play = None
        self.play_fainted_sound = False
        self.last_targeted_by = None
        self.last_move_used = None
        self.battle_stats = {
            "damage dealt": 0,
            "damage taken": 0,
            "healing given": 0,
            "healing received": 0,
            "kos": 0,
            "fainted": False,
            "time alive": 0,
            "moves used": 0}
        # attributes are recalculated whenever an effect is added or removed
        # if a move or effect requires an additional recalculation, just call recalculate
        # unmodified stats factor in base stat changes but not stages or other modifiers
        # mainly used for critical hits
        self.current_unmodified_stats = {}
        # modified stats include both all factors that would change a stat
        self.current_modified_stats = {}
        # types can also change and is checked whenever recalculate is called
        self.current_types = []
        self.locked_moves = [False, False, False, False]
        self.move_speed_modifier = 1
        self.current_base_speed = self.base_stats["SPE"]
        self.current_moves = [move for move in self.moves]
        self.recalculate()
        # moves start on partial cooldown, but not less than 1 second
        for i in range(len(self.moves)):
            self.on_cooldown(i)
            self.cooldowns[i] /= 2
            if self.cooldowns[i] > 0 and self.cooldowns[i] < 60:
                self.cooldowns[i] = 60
        self.cooldowns = [0,0,0,0]
        ui_x = honse_data.BASE_WIDTH * (self.teammate_id * 3) / 16
        ui_y = honse_data.BASE_HEIGHT - (
            (honse_data.BASE_HEIGHT / 8) * (2 - self.team)
        )
        self.ui_element = honse_data.UIElement(ui_x, ui_y, self)
        self.spawn_in()

    def recalculate(self):
        for stat in ["ATK", "DEF", "SPA", "SPD", "SPE"]:
            # this uses the calculate_modified_stat function despite being for "unmodified" stats
            # because unmodified for most purposes still includes base stat overrides, which is a type of modification
            self.current_unmodified_stats[stat] = self.calculate_modified_stat(stat=stat, include_stages=False, include_other_modifiers=False)
            self.current_modified_stats[stat] = self.calculate_modified_stat(stat)
        self.types = self.recalculate_types()
        self.current_base_speed = activate_effect(EffectTrigger.BASE_STAT_OVERRIDE, self, self.base_stats["SPE"], {"stat":"SPE"})
        for i in range(len(self.moves)):
            # check move override effects
            self.current_moves[i] = activate_effect(EffectTrigger.MOVE_OVERRIDE, self, self.moves[i])
            # check to see which moves are locked
            self.locked_moves[i] = activate_effect(EffectTrigger.MOVE_LOCK, self, False)
        self.move_speed_modifier = activate_effect(EffectTrigger.MOVE_SPEED_MODIFICATION, self, 1)

    def get_hp_as_percent(self):
        if self.is_fainted():
            return 0
        elif self.hp == self.max_hp:
            return 100
        return int(max(1, min(99, int(self.hp * 100 / self.max_hp))))

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
        image = Image.open(self.image_name).convert('RGBA')
        cropped_image = image.getbbox()
        cropped_image = image.crop(cropped_image)
        self.width, self.height = cropped_image.size
        self.team_circle_radius = math.ceil(max(self.width, self.height) / 2) + 3
        self.radius = self.team_circle_radius
        # the background is the team colored circle
        background_size = 2*self.team_circle_radius
        background_image = image = Image.new(
            mode="RGBA",
            size=(background_size, background_size),
            color=(0, 0, 0, 0),
        )
        color = (
                honse_data.TEAM_COLORS[self.team][0],
                honse_data.TEAM_COLORS[self.team][1],
                honse_data.TEAM_COLORS[self.team][2],
                85,
            )
        background_draw = ImageDraw.Draw(background_image, "RGBA")
        party_sprite_coords = (
            (background_size - self.width) // 2,
            (background_size - self.height) // 2
            )
        background_draw.ellipse((0, 0, background_size, background_size), fill=color)
        r, g, b, a = cropped_image.split()
        self.image = background_image.copy()
        self.image.paste(cropped_image, party_sprite_coords, cropped_image)
        intangible_image = Image.merge(
            "RGBA", (r, g, b, a.point(lambda x: int(x * 2 / 3)))
        )
        self.intangible_image = background_image.copy()
        self.intangible_image.paste(intangible_image, party_sprite_coords, intangible_image)
        self.fainted_image = Image.merge(
            "RGBA",
            (
                r,
                g.point(lambda x: int(x * 1 / 2)),
                b.point(lambda x: int(x * 1 / 2)),
                a.point(lambda x: int(x * 1 / 3)),
            ),
        )
        self.surface = honse_data.image_to_surface(self.image)
        self.intangible_surface = honse_data.image_to_surface(self.intangible_image)
        self.fainted_surface = honse_data.image_to_surface(self.fainted_image)

    def same_team(self, other):
        return self.team == other.team

    def get_types(self):
        return self.current_types

    def get_non_volatile_status(self):
        if self.has_non_volatile_status:
            try:
                return [effect for effect in self.effects if EffectTag.NON_VOLATILE in effect.tags][0]
            except IndexError:
                self.has_non_volatile_status = False

    def on_cooldown(self, move_id):
        try:
            self.cooldowns[move_id] = self.current_moves[move_id].cooldown
        except IndexError:
            pass

    def is_move_locked(self, move_id: int):
        try:
            return self.locked_moves[i]
        except IndexError:
            return False

    def tick_cooldowns(self, amount=1):
        for i, cooldown in enumerate(self.cooldowns):
            if cooldown > 0 and not self.is_move_locked(i):
                self.cooldowns[i] -= amount
            elif cooldown < 0:
                self.cooldowns[i] = 0

    def get_type_matchup(self, pkmn_type: PokemonType, type_overrides: dict|None = None):
        type_overrides = {} if type_overrides is None else type_overrides
        damage_numerator = 1
        damage_denominator = 1
        for t in self.get_types():
            if pkmn_type in type_overrides:
                if type_overrides[pkmn_type] == "immune":
                    return 0.125
                elif type_overrides[pkmn_type] == "weak":
                    damage_numerator *= 2
                    damage_denominator *= 1
                elif type_overrides[pkmn_type] == "resist":
                    damage_numerator *= 1
                    damage_denominator *= 2
            elif pkmn_type in t.immunities:
                return 0.125
            elif pkmn_type in t.weaknesses:
                damage_numerator *= 2
                damage_denominator *= 1
            elif pkmn_type in t.resistances:
                damage_numerator *= 1
                damage_denominator *= 2
        return damage_numerator / damage_denominator

    def is_fainted(self):
        if self.hp < 0:
            self.hp = 0
        return self.hp == 0

    def is_intangible(self):
        return self.intangibility > 0 or self.in_hitstop() or self.is_fainted()

    def is_invulnerable(self):
        return self.invulnerability > 0 or self.in_hitstop() or self.is_fainted()

    def in_hitstop(self):
        return self.hitstop > 0

    def tick_invulnerability(self):
        if self.invulnerability > 0:
            self.invulnerability -= 1
        if self.invulnerability < 0:
            self.invulnerability = 0

    def tick_intangibility(self):
        if self.intangibility > 0:
            self.intangibility -= 1
        if self.intangibility < 0:
            self.intangibility = 0

    def tick_hitstop(self):
        if self.hitstop > 0:
            self.hitstop -= 1
            if self.hitstop == 0 and self.hit_sound_to_play is not None:
                self.game.play_sound(self.hit_sound_to_play)
        if self.hitstop < 0:
            self.hitstop = 0
        return self.hitstop > 0

    def calculate_unmodified_stat(self, stat):
        base_stat = self.base_stats[stat]
        ev = self.evs[stat]
        iv = self.ivs[stat]
        nature = self.nature[stat]
        return other_stat_formula(base_stat, self.level, iv, ev, nature)

    def calculate_modified_stat(self, stat, include_base_stat_overrides=True, include_stages=True, include_other_modifiers=True):
        base_stat = self.base_stats[stat]
        if include_base_stat_overrides:
            base_stat = activate_effect(EffectTrigger.BASE_STAT_OVERRIDE, self, base_stat, {"stat":stat})
        stage = 0
        if include_stages:
            stage = activate_effect(EffectTrigger.STAGE_MODIFICATION, self, stage, {"stat":stat})
        ev = self.evs[stat]
        iv = self.ivs[stat]
        nature = self.nature[stat]
        stat_value = other_stat_formula(base_stat, self.level, iv, ev, nature)
        stage_modifier = stage_to_modifier(stage)
        stat_value *= stage_modifier
        if include_other_modifiers:
            stat_value *= activate_effect(EffectTrigger.STAT_MODIFICATION, self, 1, {"stat":stat})
        return stat_value

    def recalculate_types(self):
        types = activate_effect(
            effect_trigger=EffectTrigger.TYPE_OVERRIDE,
            character=self,
            starting_value=self.types)
        types = activate_effect(
            effect_trigger=EffectTrigger.TYPE_ADDITION,
            character=self,
            starting_value=self.types)
        return types

    def get_move(self, index):
        return self.current_moves[index]

    def get_max_hp(self):
        ev = self.evs["HP"]; iv = self.ivs["HP"]
        return hp_formula(self.base_stats["HP"], self.level, iv, ev)

    def get_move_speed(self):
        speed = speed_formula(self.current_base_speed) * self.move_speed_modifier 
        return max(1, speed)

    # there is support for acceleration/drag changes to be added, but idk if i will do it
    def get_acceleration(self):
        return self.acceleration

    def get_drag(self):
        return self.drag

    def update_current_speed(self):
        speed = self.get_move_speed()
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
        norm = np.linalg.norm(self.velocity)
        if norm == 0:
            np.zeros_like(self.velocity)
        else:
            self.velocity = (
                self.velocity / np.linalg.norm(self.velocity)
            ) * self.current_speed

    def use_move(self, target):
        successfully_moved = False
        if not self.is_fainted():
            for i in range(len(self.moves)):
                move = self.get_move(i)
                if self.cooldowns[i] == 0 and not self.is_move_locked(i):
                    if move.is_valid_target(self, target) == False:
                        continue
                    can_move = True
                    # if an effect that would block the move usage triggers, it returns True
                    can_move = not activate_effect(EffectTrigger.ON_TRY_USE_MOVE, self, False, {"move": move})
                    if can_move:
                        self.game.display_message(f"{self.name} used {move.name}!", 24, [0, 0, 0])
                        attack = move.on_use(self, target=target)
                        activate_effect(EffectTrigger.AFTER_USE_MOVE, self, effect_kwargs={"attack": attack})
                        successfully_moved = attack.success
                        if not successfully_moved:
                            self.game.display_message("But it failed!", self.text_size, [0,0,0])
                        else:
                            self.battle_stats["moves used"] += 1
                            self.last_move_used = attack
                    self.on_cooldown(i)
                    # todo
                    # moves that modify their accuracy conditionally will instead inflict a post move cooldown effect on its user
                    # after the move is put on cooldown, the effect will be triggered here
                    # this will modify the move's cooldown by either shortening it or applying a temporary move lock effect
                    # this is also used for transform. due to the reduced PP of all moves when transformed in vanilla
                    # transformed pokemons will have moves that they used temporarily locked by the transform effect
                    # IDEA:
                    # INSTEAD OF THIS, ADD AN EFFECT THAT MAKES COOLDOWNS TICK FASTER OR SLOWER UNDER CERTAIN CONDITIONS
                    # FOR EXAMPLE, THUNDER CAN RECHARGE AT 1.5x SPEED IN RAIN
                    if successfully_moved:
                        activate_effect(EffectTrigger.AFTER_MOVE_COOLDOWN, self, effect_kwargs={"attack":attack})
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
            self.game.play_sound("bounce")

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
            self.tick_hitstop()
        else:
            self.tick_intangibility()
            self.tick_invulnerability()
            self.update_current_speed()
        if self.is_fainted():
            self.cooldowns = [0, 0, 0, 0]
            if len(self.effects):
                for effect in self.effects:
                    self.remove_status(effect)
        else:
            self.tick_cooldowns()

    def move(self):
        frozen = False
        if self.in_hitstop() or self.current_speed == 0:
            frozen = True
        if self.play_fainted_sound and self.current_speed == 0:
            self.game.play_sound("In-Battle Faint No Health")
            self.play_fainted_sound = False
        if not frozen:
            cell_x = int(self.position[0]) // self.game.cell_size
            cell_y = int(self.position[1]) // self.game.cell_size
            # Lina code
            nearby_walls = sum(
                (
                    self.game.wall_grid.get((i, j), [])
                    for i in range(cell_x - 1, cell_x + 2)
                    for j in range(cell_y - 1, cell_y + 2)
                ),
                [],
            )
            for wall in nearby_walls:
                self.collide_with_wall(wall)
            self.position += self.velocity

    def draw(self):
        if self.is_fainted():
            surface = self.fainted_surface
            image = self.fainted_image
        elif (
            self.is_intangible() or self.is_invulnerable()
        ):
            surface = self.intangible_surface
            image = self.intangible_image
        else:
            surface = self.surface
            image = self.image
        self.game.draw_image(
            int((self.position[0] - (self.width / 2)) * self.game.width_ratio),
            int((self.position[1] - (self.height / 2)) * self.game.width_ratio),
            surface,
            image,
        )

    def do_damage(self, source, damage, direct_damage=False, silent=False):
        if self.is_fainted() or damage==0 or self.game.game_end:
            return 0
        if damage > self.hp:
            damage = self.hp
        self.hp -= damage
        self.battle_stats["damage taken"] += damage
        if source is not None and not self.same_team(source):
            source.battle_stats["damage dealt"] += damage
        if not silent:
            percent = int(max(1, (100 * damage) // self.max_hp))
            self.game.display_message(f"{self.name} took {percent} damage.", 16, [0, 0, 0])
            self.game.message_log.append([f"({percent}% = {damage}, {self.hp}/{self.max_hp})", False])
        if self.is_fainted():
            self.battle_stats["fainted"] = True
            if source is not None and not self.same_team(source):
                source.battle_stats["kos"] += 1
            self.play_fainted_sound = True
            self.game.display_message(f"{self.name} fainted!", 24, [127, 0, 0])
        return damage


    def do_healing(self, source, healing,  silent=False):
        if self.is_fainted() or healing==0 or self.game.game_end:
            return 0
        max_hp = self.max_hp
        if healing + self.hp > max_hp:
            healing = max_hp - self.hp
        self.hp += healing
        self.battle_stats["healing received"] += healing
        if source is not None and self.same_team(source):
            source.battle_stats["healing given"] += healing
        if not silent:
            percent = int(max(1, (100 * healing) // self.max_hp))
            self.game.display_message(f"{self.name} recovered {percent} HP.", 16, [0, 0, 0])
            self.game.message_log.append([f"({percent}% = {healing}, {self.hp}/{self.max_hp})", False])
        return healing

    def inflict_status(self, status):
        if self.is_fainted():
            return False
        self.effects.append(status)
        if EffectTag.NON_VOLATILE not in status.tags:
            self.ui_element.queue_status(status)
        else:
            self.has_non_volatile_status = True
        self.recalculate()
        self.game.message_log.append([f"{self.name} was inflicted with {type(status)} by {status.inflicted_by.name}'s {status.source.move.name}.", False])
        return True

    def remove_status(self, status):
        self.effects.remove(status)
        if EffectTag.NON_VOLATILE not in status.tags:
            self.ui_element.unqueue_status(status)
        else:
            self.has_non_volatile_status = False
        self.recalculate()
        self.game.message_log.append([f"{self.name}'s {type(status)} wore off.", False])

    def end_of_turn(self):
        for effect in self.effects:
            effect.end_of_turn()
            effect.update()


class MoveTarget(enum.Enum):
    USER = enum.auto()
    ENEMY = enum.auto()
    ALLY = enum.auto()
    OTHERS = enum.auto()
    OTHER_ALLIES = enum.auto()
    ALL = enum.auto()

class Move:
    def __init__(self,
                 name: str,
                 pkmn_type: PokemonType,
                 category: MoveCategories,
                 target: MoveTarget,
                 power: int,
                 options: "MoveOptions"):
        self.name = name
        self.type = pkmn_type
        self.category = category
        self.target = target
        self.power = power
        # secondaries and non_secondaries are mostly the same
        # both trigger after a move lands
        # non secondaries are guaranteed to trigger and secondaries may only have a chance to trigger
        # secondaries are effected by some things like sheer power if i end up deciding to implement abilities
        # when a move is used, it creates an attack_class. usually this is just Attack but some moves may inherit from Attack for unique effects
        self.secondary_effects = options.secondary_effects
        self.non_secondary_effects = options.non_secondary_effects
        self.accuracy = options.accuracy
        self.attack_class = options.attack_class
        self.crit_stage = options.crit_stage
        self.drain = options.drain
        self.recoil = options.recoil
        self.attack_stat_override = options.attack_stat_override
        self.defense_stat_override = options.defense_stat_override
        self.ignore_attack_modifiers = options.ignore_attack_modifiers
        self.ignore_defense_modifiers = options.ignore_defense_modifiers
        self.foul_play = options.foul_play
        self.effectiveness_overrides = options.effectiveness_overrides
        self.hitstop = options.hitstop
        self.base_knockback = options.base_knockback
        self.animation = options.animation
        self.sound = options.sound
        self.spread_radius = options.spread_radius
        self.spread_options = options.spread_options
        self.spread_can_hit_allies = options.spread_can_hit_allies
        self.spread_can_hit_enemies = options.spread_can_hit_enemies
        self.cooldown = options.cooldown
        if self.category == MoveCategories.STATUS:
            pass
        else:
            if self.base_knockback is None:
                self.base_knockback = self.type.base_knockback * self.power / 100
            if self.hitstop is None:
                self.hitstop = self.type.default_hitstop
            if self.animation is None:
                self.animation = self.type.default_animation
            if self.sound is None:
                self.sound = self.type.sound
        if self.cooldown is None:
            self.get_default_cooldown()

    def get_default_cooldown(self):
        # cooldown scales on power plus a flat 10 because i want high power moves to have better dps
        if self.power == 0:
            cooldown = 300
        else:
            cooldown = 60 * (self.power + 10) / 10
        modifier = 1
        if self.spread_radius > 0:
            modifier *= 1.5
        if self.accuracy < 100:
            modifier *= 1.25 * 100 / self.accuracy
        if self.crit_stage > 0:
            modifier *= 1.25
        if self.drain > 0:
            modifier *= 1.35
        if self.recoil > 0:
            modifier *= 0.8
        secondaries = self.secondary_effects + self.non_secondary_effects
        self_detrimental_cooldown_bonus = 0
        for effect_group in secondaries:
            chance = effect_group.chance
            for effect in effect_group.effects:
                affects_user = effect.affects_user
                effect_options = effect.options
                effect_object = effect.effect(effect_options)
                effect_value = effect_object.get_effect_value()
                effect_value *= chance
                # moves that do something bad to the user or something good to the opponent get a slight cooldown reduction
                # in cases where moves have multiple detrimental effects, only the most impactful one reduces the cooldown
                if affects_user and effect_value > 0:
                    effect_value *= 0.25
                    if effect_value > self_detrimental_cooldown_bonus:
                        self_detrimental_cooldown_bonus = effect_value
                elif not affects_user and effect_value < 0:
                    effect_value *= -0.25
                    if effect_value > self_detrimental_cooldown_bonus:
                        self_detrimental_cooldown_bonus = effect_value
                # moves that do something good to the user get a normal sized cooldown increase
                elif affects_user and effect_value < 0:
                    cooldown -= effect_value
                # moves that do something bad to the opponent get a normal sized cooldown increase
                else:
                    cooldown += effect_value
        cooldown -= self_detrimental_cooldown_bonus
        cooldown *= modifier
        cooldown *= self.type.cooldown_modifier
        self.cooldown = max(int(cooldown), 60)
        print(f"{self.name}'s cooldown: {self.cooldown/60}")

    # used to determine whether to use the move
    def is_valid_target(self, user, target):
        if self.target == MoveTarget.ENEMY:
            return not user.same_team(target)
        elif self.target == MoveTarget.ALLY:
            return user.same_team(target)
        else:
            return True

    # initial use is when this move is used normally (a character collides with another character and chooses this move to use)
    # when false, that means this is the result of a spread hit
    def on_use(self, user: Character, target: Character, initial_use=True):
        attack = self.attack_class(self, user, target, initial_use)
        attack.activate()
        return attack

class Attack:
    def __init__(self, move: Move, user: Character, target:Character, initial_use:bool):
        self.game = user.game
        self.move = move
        self.user = user
        self.target = target
        self.initial_use = initial_use
        self.power = self.move.power
        self.type = self.move.type
        self.attack_stat_override = self.move.attack_stat_override
        self.defense_stat_override = self.move.defense_stat_override
        self.ignore_attack_modifiers = self.move.ignore_attack_modifiers
        self.ignore_defense_modifiers = self.move.ignore_defense_modifiers
        self.foul_play = self.move.foul_play
        self.success = False

    def trigger_on_use_effects(self):
        activate_effect(
            effect_trigger=EffectTrigger.ON_USE_MOVE,
            character=self.user,
            effect_kwargs={"attack":self}
            )

    def trigger_on_hit_effects(self, user, target):
        if user is not target:
            activate_effect(
                effect_trigger=EffectTrigger.ON_LANDING_MOVE,
                character=user,
                effect_kwargs={"attack":self}
                )
            activate_effect(
                effect_trigger=EffectTrigger.ON_HIT_BY_MOVE,
                character=target,
                effect_kwargs={"attack":self}
                )

    def apply_secondaries(self, user: "Character", target: "Character"):
        for effect_group in self.move.secondary_effects:
            if random.random() <= effect_group.chance:
                for secondary in effect_group.effects:
                    if secondary.affects_user:
                        secondary.effect(secondary.options, self.game, self, user, user)
                    else:
                        secondary.effect(secondary.options, self.game, self, user, target)

    def apply_non_secondaries(self, user: "Character", target: "Character"):
        for effect_group in self.move.non_secondary_effects:
            for non_secondary in effect_group.effects:
                if non_secondary.affects_user:
                    non_secondary.effect(non_secondary.options, self.game, self, user, user)
                else:
                    non_secondary.effect(non_secondary.options, self.game, self, user, target)

    def create_spread_hazard(self, user, target, x, y):
        hazard_options = deepcopy(self.move.spread_options)
        if user is not target:
            hazard_options.immune_pokemon = [user, target]
        else:
            hazard_options.immune_pokemon = [user]
        hazard_options.immune_teams = []
        if not self.move.spread_can_hit_allies:
            hazard_options.immune_teams.append(user.team)
        if not self.move.spread_can_hit_enemies:
            enemy_teams = list(range(user.game.number_of_teams))
            enemy_teams.remove(user.team)
            hazard_options.immune_teams += enemy_teams
        hazard_options.color = self.type.hazard_color
        hazard_options.effect = MoveEffect
        hazard_options.effect_options = MoveEffectOptions(move=self.move)
        Hazard(hazard_options, (x, y), self.move.spread_radius, self.game, self, user)

    def play_effects(self, x: float, y: float):
        if self.move.sound is not None:
            self.game.play_sound(self.move.sound)
        if self.move.animation is not None:
            self.move.animation(self.game, x, y)

    def knockback_modifier(self, current_hp: int, damage: int):
        # knockback is multiplied by knockback scaling
        # knockback scaling is equal to 1+((knockback_scaling * damage)/current_hp)
        # damage cannot exceed current HP
        knockback_modification = 1 + (damage / max(damage, current_hp))
        return knockback_modification
   
    def activate(self):
        user = self.user
        if self.move.target == MoveTarget.USER:
            target = user
        else:
            target = self.target
        x, y = target.position[0], target.position[1]
        self.trigger_on_use_effects()
        self.play_effects(x, y)
        if self.power > 0 and self.move.category != MoveCategories.STATUS:
            # damage calc
            damage, crit = damage_formula(self, user, target)
            # display messages and vfx
            if crit:
                if self.move.spread_radius > 0:
                    user.game.display_message(f"A critical hit on {target.name}!", 16, [0, 0, 0])
                else:
                    user.game.display_message("A critical hit!", 16, [0, 0, 0])
            effectiveness_quote, effectiveness_sound = get_type_effectiveness_stuff(self, target)
            if effectiveness_quote:
                user.game.display_message(effectiveness_quote, 16, [0, 0, 0])
            target.hit_sound_to_play = effectiveness_sound
            # do damage
            damage = target.do_damage(user, damage)
            # knockback and hitstop
            knockback_mod = self.knockback_modifier(target.hp, damage)
            knockback = self.move.base_knockback * knockback_mod
            target.hitstop = self.move.hitstop
            target.current_speed += knockback
            # drain and recoil
            if self.move.drain > 0:
                healing = max(1, int(damage * self.move.drain))
                user.game.display_message(f"{target.name} had its energy drained!", 16, [0, 0, 0])
                user.do_healing(user, healing, silent=True)
            if self.move.recoil > 0:
                recoil = max(1, int(damage * self.move.recoil))
                user.game.display_message(f"{user.name} is damaged by recoil!", 16, [0, 0, 0])
                user.do_damage(user, recoil, silent=True)
            self.trigger_on_hit_effects(user, target)
        # secondaries and other effects
        self.apply_non_secondaries(user, target)
        self.apply_secondaries(user, target)
        if self.initial_use and self.move.spread_radius > 0:
            self.create_spread_hazard(user, target,x, y)
        self.success = True

# PLEASE READ THIS TO UNDERSTAND HOW SECONDARIES WORK
# Some moves have secondaries that apply at a random chance
# For example, Fire Fang has a 10% chance to burn, and a 10% chance to flinch
# These effects apply independently of each other. So one, both, or neither effect may occur.
# Some moves apply multiple effects that are dependant on each other however
# For example, Ancient Power has a 10% chance to raise every stat
# Because move speed is handled seperately, if an Ancient Power omniboost occurs, both a StatStageEffect and a MoveSpeedModificationEffect need to be applied
# This is because the move speed calculation can automatically take into account base speed changes but not speed stage changes
# thats why effects and effects_options here is a list
# for a move like AncientPower, you would put two MoveSecondary objects into one Secondary Group
# if you want the chances to be independant of each other (this is usually the case), use multiple MoveSecondaryGroup objects with one MoveSecondary object each
@dataclass
class MoveSecondary:
    effect: ...
    options: ...
    affects_user: bool
@dataclass  
class SecondaryGroup:
    effects: list["MoveSecondary"]
    chance: float = 1

@dataclass
class MoveOptions:
    accuracy: int = 100
    secondary_effects: list[SecondaryGroup] = field(default_factory=list)
    non_secondary_effects: list[SecondaryGroup] = field(default_factory=list)
    attack_class = Attack
    crit_stage: int = 0
    drain: float = 0
    recoil: float = 0
    attack_stat_override: str|None = None
    defense_stat_override: str|None = None
    ignore_attack_modifiers: bool = False
    ignore_defense_modifiers: bool = False
    foul_play: bool = False
    effectiveness_overrides: dict|None = None
    hitstop: int|None = None
    base_knockback: int|None = None
    animation: ... = None
    sound: str|None = None
    spread_radius: int = 0
    spread_options: ... = None
    spread_can_hit_allies: bool = True
    spread_can_hit_enemies: bool = True
    cooldown: int|None = None


MOVE_OPTIONS = {
    "confusion damage": MoveOptions(crit_stage=-1),
    "quick attack": MoveOptions(
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=CooldownReductionEffect,options=CooldownReductionEffectOptions(cooldown_reduction_amount=80),affects_user=True)]
            )]),
    "giga drain": MoveOptions(drain=0.5),
    "heat wave": MoveOptions(
        accuracy=90,
        secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=BurnEffect,options=DamagingNonVolatileEffectOptions(),affects_user=False)],
                chance=0.1)],
        spread_radius=120,
        spread_can_hit_allies=False,
        spread_options=HazardOptions(
                           lifetime=40,
                           hazard_set_radius_growth_time=10,
                           active_radius_growth_time=15,
                           active_full_radius_duration=15,
                           immune_timer=honse_data.A_LOT_OF_FRAMES)
        ),
    "water pulse": MoveOptions(
        accuracy=90,
        secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=ConfusionEffect,options=EffectOptions(),affects_user=False)],
                chance=0.2)],
        ),
    "aggregate": MoveOptions(
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=AggregateEffect,options=HazardClearEffectOptions(radius=200,clear_friendly_hazards=False),affects_user=True)]
                )],
        ),
    "heal bell": MoveOptions(
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=HealBellEffect,options=None,affects_user=True)]
                )],
        ),
    "belly drum": MoveOptions(
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=BellyDrumEffect,options=EffectOptions(),affects_user=True)]
                )]),
    "camouflage": MoveOptions(
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=CamouflageEffect,options=EffectOptions(lifetime=1800),affects_user=True)]
                )]),
    "block": MoveOptions(
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=MoveSpeedModificationEffect,options=MoveSpeedModificationEffectOptions(modifier=0.25),affects_user=False)]
                )]),
    "psyshock": MoveOptions(defense_stat_override="DEF"),
    "superpower": MoveOptions(
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=StatStageEffect,options=StatOptions(positive=False,stats={"ATK":-1,"DEF":-1}),affects_user=True)]
                )]),
    "blizzard": MoveOptions(
        accuracy=70,
        secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=FreezeEffect,options=DamagingNonVolatileEffectOptions(),affects_user=False)],
                chance=0.1)],
        spread_radius=120,
        spread_can_hit_allies=False,
        spread_options=HazardOptions(
                           lifetime=40,
                           hazard_set_radius_growth_time=10,
                           active_radius_growth_time=15,
                           active_full_radius_duration=15,
                           immune_timer=honse_data.A_LOT_OF_FRAMES)
        ),
    "thunder": MoveOptions(
        accuracy=70,
        secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=ParalysisEffect,options=DamagingNonVolatileEffectOptions(),affects_user=False)],
                chance=0.3)]
        )
    }
UNOBTAINABLE_MOVES = {
    "confusion damage": Move(
        name="confusion damage",
        pkmn_type=pokemon_types["Typeless"],
        category=MoveCategories.PHYSICAL,
        target=MoveTarget.USER,
        power=40,
        options=MOVE_OPTIONS["confusion damage"])
    }
MOVES = {
    "Quick Attack": Move(
        name="Quick Attack",
        pkmn_type=pokemon_types["Normal"],
        category=MoveCategories.PHYSICAL,
        target=MoveTarget.ENEMY,
        power=40,
        options=MOVE_OPTIONS["quick attack"]),
    "Giga Drain": Move(
        name="Giga Drain",
        pkmn_type=pokemon_types["Grass"],
        category=MoveCategories.SPECIAL,
        target=MoveTarget.ENEMY,
        power=75,
        options=MOVE_OPTIONS["giga drain"]),
    "Heat Wave": Move(
        name="Heat Wave",
        pkmn_type=pokemon_types["Fire"],
        category=MoveCategories.SPECIAL,
        target=MoveTarget.ENEMY,
        power=95,
        options=MOVE_OPTIONS["heat wave"]),
    "Water Pulse": Move(
        name="Water Pulse",
        pkmn_type=pokemon_types["Water"],
        category=MoveCategories.SPECIAL,
        target=MoveTarget.ENEMY,
        power=60,
        options=MOVE_OPTIONS["water pulse"]),
    "Psyshock": Move(
        name="Psyshock",
        pkmn_type=pokemon_types["Psychic"],
        category=MoveCategories.SPECIAL,
        target=MoveTarget.ENEMY,
        power=80,
        options=MOVE_OPTIONS["psyshock"]),
    "Superpower": Move(
        name="Superpower",
        pkmn_type=pokemon_types["Fighting"],
        category=MoveCategories.PHYSICAL,
        target=MoveTarget.ENEMY,
        power=120,
        options=MOVE_OPTIONS["superpower"]),
    "Thunder": Move(
        name="Thunder",
        pkmn_type=pokemon_types["Electric"],
        category=MoveCategories.SPECIAL,
        target=MoveTarget.ENEMY,
        power=110,
        options=MOVE_OPTIONS["thunder"]),
    "Blizzard": Move(
        name="Blizzard",
        pkmn_type=pokemon_types["Ice"],
        category=MoveCategories.SPECIAL,
        target=MoveTarget.ENEMY,
        power=110,
        options=MOVE_OPTIONS["blizzard"]),
    }
MANUALLY_IMPLEMENTED_STATUS_MOVES = {
    "Aggregate": Move(
        name="Aggregate",
        pkmn_type=pokemon_types["Normal"],
        category=MoveCategories.STATUS,
        target=MoveTarget.USER,
        power=0,
        options=MOVE_OPTIONS["aggregate"]),
    "Aromatherapy": Move(
        name="Aromatherapy",
        pkmn_type=pokemon_types["Grass"],
        category=MoveCategories.STATUS,
        target=MoveTarget.USER,
        power=0,
        options=MOVE_OPTIONS["heal bell"]),
    "Belly Drum": Move(
        name="Belly Drum",
        pkmn_type=pokemon_types["Normal"],
        category=MoveCategories.STATUS,
        target=MoveTarget.USER,
        power=0,
        options=MOVE_OPTIONS["belly drum"]),
    "Block": Move(
        name="Block",
        pkmn_type=pokemon_types["Normal"],
        category=MoveCategories.STATUS,
        target=MoveTarget.ENEMY,
        power=0,
        options=MOVE_OPTIONS["block"]),
    "Camouflage": Move(
        name="Camouflage",
        pkmn_type=pokemon_types["Normal"],
        category=MoveCategories.STATUS,
        target=MoveTarget.USER,
        power=0,
        options=MOVE_OPTIONS["camouflage"]),
    }

# some of these can be implemented later
DO_NOT_IMPLEMENT = [
    "After You",
    "Ally Switch",
    "Assist",
    "Baton Pass",
    "Bestow",
    "Celebrate"
    ]

with open("honse_moves.json", "r") as f:
    data = json.load(f)
    text = ""
    for move_name, move_dict in data.items():
        if len(move_dict["effects"]):
            continue
        text += move_name + "\n"
        for key, value in move_dict.items():
            text += f"\t{key}: {value}\n"
        '''
        if len(value["effects"]) == 0 and value["category"] == "Status":
            print(key)
        '''
    print(text)
    with open("empty_effects.txt", "w") as outfile:
        outfile.write(text)
