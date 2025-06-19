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
    elif effectiveness < 0.25:
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
    move_text = f"Move: {attack_object.move.name}, Power: {attack_object.power}, Fixed Damage: {attack_object.fixed_damage_amount}"
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
    if attack_object.fixed_damage_amount == 0:
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
    else:
        crit_mod = 1
        initial_damage = attack_object.fixed_damage_amount
        spread_mod = 1
        type_effectiveness = defender.get_type_matchup(attack_object.type, attack_object.move.effectiveness_overrides)
        if type_effectiveness >= 0.25:
            type_effectiveness = 1
        stab_mod = 1
        random_mod = 1
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
    # triggers when attempting to use a move, before it is decided if the move will activate
    ON_TRY_USE_MOVE = enum.auto()
    # triggers at the start of using a move
    ON_USE_MOVE = enum.auto()
    ON_TARGETED_BY_MOVE = enum.auto()
    # triggers on a successful attack after damage and before secondaries
    ON_LANDING_MOVE = enum.auto()
    ON_HIT_BY_MOVE = enum.auto()
    # triggers after an attack, regardless of success
    AFTER_USE_MOVE = enum.auto()
    AFTER_TARGETED_BY_MOVE = enum.auto()
    # this does not trigger whenever a move goes on cooldown
    # it only triggers when a move goes on cooldown after it was used
    # this is primarily for effects that modify the cooldown of the move that was just used
    AFTER_MOVE_USE_COOLDOWN = enum.auto()
    MOVE_OVERRIDE = enum.auto()
    TYPE_OVERRIDE = enum.auto()
    TYPE_ADDITION = enum.auto()
    HEAL_BLOCK = enum.auto()
    TYPE_EFFECTIVENESS_OVERRIDE = enum.auto()
    # after damage message is sent, before "X fainted!" is sent
    ON_FAINT = enum.auto()

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
    AQUA_RING = enum.auto()
    PROTECT = enum.auto()
    ENDURE = enum.auto()
    BIDE = enum.auto()
    PARTIALLY_TRAPPED = enum.auto()
    CURSE = enum.auto()
    CHARGE = enum.auto()
    DEFENSE_CURL = enum.auto()
    ELECTRIFY = enum.auto()
    HELPING_HAND = enum.auto()
    CENTER_OF_ATTENTION = enum.auto()

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
            self.instant_effect()
            if EffectTrigger.INSTANT in self.triggers:
                success = True
            else:
                success = self.inflicted_upon.inflict_status(self)
        if success:
            self.after_infliction()
        return success

    # instant_effect is usually used by effects that do something and then immediately wear off
    # but is occasionally used by other effects such as center of attention
    # in this case, it still does something immediately, but it doesn't wear off right away
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
        self.inflicted_upon.recalculate()

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

    def on_removal(self):
        pass

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
class AquaRingEffectOptions:
    lifetime: int = 1800,
    healing: float = 1/64,
    cooldown: int = 40,
class AquaRingEffect(EffectInterface):
    def __init__(self,
             options: AquaRingEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "Aqua Ring"
        self.status_icon = "healing"
        self.healing = options.healing # decimal representing portion of max hp
        self.healing_cooldown = options.cooldown
        self.max_healing_cooldown = options.cooldown
        self.triggers = [EffectTrigger.END_OF_TURN]
        self.tags = [EffectTag.AQUA_RING]
        self.blocks = [EffectTag.AQUA_RING]
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return -2000

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} surrounded itself with a veil of water!", self.text_size, [0, 0, 0])

    def end_of_turn(self):
        if self.inflicted_by.is_fainted():
            self.lifetime = 0
        else:
            self.healing_cooldown -= 1
            if self.healing_cooldown <= 0 and not self.inflicted_upon.is_fainted():
                self.activate(EffectTrigger.END_OF_TURN, None)
                self.healing_cooldown = self.max_healing_cooldown

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.END_OF_TURN:
            self.inflicted_by.do_healing(self.inflicted_by, self.healing, silent=True)
        return input_value

@dataclass
class ProtectOptions:
    lifetime: int = 600
    unprotected_categories: list = field(default_factory=list)
    contact_effect: ... = None
    contact_effect_options: ... = None
class ProtectEffect(EffectInterface):
    def __init__(self,
             options: ProtectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "ProtectEffect"
        self.status_icon = "protect"
        self.activated = False
        self.activated_by = []
        self.triggers = [EffectTrigger.ON_TARGETED_BY_MOVE, EffectTrigger.AFTER_TARGETED_BY_MOVE]
        self.tags = [EffectTag.PROTECT]
        self.blocks = [EffectTag.PROTECT, EffectTag.ENDURE]
        self.overrides = [EffectTag.ENDURE]
        self.unprotected_categories = options.unprotected_categories
        self.contact_effect = options.contact_effect
        self.contact_effect_options = options.contact_effect_options
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return -900

    def after_infliction(self):
        super().after_infliction()

    def end_effect(self):
        if self.activated:
            locked_moves = []
            for move in self.inflicted_by.current_moves:
                if move.has_effect(tag=EffectTag.ENDURE) or move.has_effect(tag=EffectTag.PROTECT):
                    locked_moves.append(move)
            if len(locked_moves):
                options = MoveLockOptions(600, locked_moves)
                MoveLockEffect(options, self.game, self.source, self.inflicted_by, self.inflicted_by)
        super().end_effect()

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.ON_TARGETED_BY_MOVE:
            if kwargs["attack"].move.category not in self.unprotected_categories and kwargs["attack"].user is not self.inflicted_upon:
                kwargs["attack"].defender_protect = True
                self.activated = True
                if self.lifetime > 30:
                    self.lifetime = 30
                self.activated_by.append(kwargs["attack"])
        if effect == EffectTrigger.AFTER_TARGETED_BY_MOVE:
            if self.contact_effect is not None:
                attack = kwargs["attack"]
                if attack in self.activated_by and attack.contact and attack.protect_activated:
                    self.contact_effect(self.contact_effect_options, self.game, self.source, self.inflicted_by, attack.user)
        return input_value

class EndureEffect(EffectInterface):
    def __init__(self,
             options: EffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "EndureEffect"
        self.status_icon = "protect"
        self.triggers = [EffectTrigger.ON_TARGETED_BY_MOVE, EffectTrigger.AFTER_TARGETED_BY_MOVE]
        self.tags = [EffectTag.ENDURE]
        self.blocks = [EffectTag.ENDURE]
        self.overrides = []
        self.activated = False
        self.activated_by = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return -600

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} braced itself!", self.text_size, [0, 0, 0])

    def end_effect(self):
        if self.activated:
            locked_moves = []
            for move in self.inflicted_by.current_moves:
                if move.has_effect(tag=EffectTag.ENDURE) or move.has_effect(tag=EffectTag.PROTECT):
                    locked_moves.append(move)
            if len(locked_moves):
                options = MoveLockOptions(600, locked_moves)
                MoveLockEffect(options, self.game, self.source, self.inflicted_by, self.inflicted_by)
        super().end_effect()

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.ON_TARGETED_BY_MOVE:
            if kwargs["attack"].user is not self.inflicted_upon:
                kwargs["attack"].defender_endure = True
                self.activated_by.append(kwargs["attack"])
        if effect == EffectTrigger.AFTER_TARGETED_BY_MOVE:
            if kwargs["attack"] in self.activated_by and kwargs["attack"].endure_activated:
                self.activated = True
                if self.lifetime > 30:
                    self.lifetime = 30
        return input_value

class DestinyBondEffect(EffectInterface):
    def __init__(self,
             options: EffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "DestinyBondEffect"
        self.status_icon = "destiny bond"
        self.triggers = [EffectTrigger.ON_FAINT]
        self.tags = []
        self.blocks = []
        self.overrides = []
        self.activated = False
        self.activated_by = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return -1200

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} is trying to take its foe down with it!", self.text_size, [0, 0, 0])

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.ON_FAINT:
            attack = kwargs["attack"]
            if attack is not None:
                attacker = attack.user
                if not self.inflicted_upon.same_team(attacker):
                    self.activated = True
                    self.lifetime = 0
                    options = DamageEffectOptions(
                        damage=1,
                        percent_of_max_hp_damage=True,
                        message="USER took TARGET down with it!")
                    DamageEffect(options, self.game, self.source, self.inflicted_upon, attacker)
        return input_value

class GrudgeEffect(EffectInterface):
    def __init__(self,
             options: EffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "GrudgeEffect"
        self.status_icon = "destiny bond"
        self.triggers = [EffectTrigger.ON_FAINT]
        self.tags = []
        self.blocks = []
        self.overrides = []
        self.activated = False
        self.activated_by = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return -1200

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} wants the foe to bear a grudge!", self.text_size, [0, 0, 0])

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.ON_FAINT:
            attack = kwargs["attack"]
            if attack is not None:
                attacker = attack.user
                if not self.inflicted_upon.same_team(attacker):
                    self.activated = True
                    self.lifetime = 0
                    options = MoveLockOptions(
                        lifetime = honse_data.A_LOT_OF_FRAMES,
                        locked_moves= [attack.move])
                    MoveLockEffect(options, self.game, self.source, self.inflicted_upon, attacker)
                    self.game.display_message(f"{attack.move.name} was locked due to the grudge!", self.text_size, [0, 0, 0])
        return input_value

class DefenseCurlEffect(EffectInterface):
    def __init__(self,
             options: EffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.status_icon = "defense curl"
        self.name = "DefenseCurl"
        self.triggers = []
        self.tags = [EffectTag.DEFENSE_CURL]
        self.blocks = []
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

@dataclass
class CenterOfAttentionOptions:
    lifetime: int = 300
    radius: int = 300
class CenterOfAttentionEffect(EffectInterface):
    def __init__(self,
             options: EffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.status_icon = "spotlight"
        self.name = "CenterOfAttentionEffect"
        self.triggers = []
        self.tags = [EffectTag.CENTER_OF_ATTENTION]
        self.blocks = []
        self.overrides = []
        self.radius = options.radius
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} became the center of attention!", self.text_size, [0, 0, 0])

    def instant_effect(self):
        # only one center of attention at a time
        for character in self.game.characters:
            for effect in character.effects:
                if effect is self:
                    continue
                if EffectTag.CENTER_OF_ATTENTION in effect.tags:
                    effect.end_effect()
        self.display_inflicted_message()
        options = HazardOptions(
            # the lifetime is set to a lot of frames but the hazard will be ended when this effect wears off
            lifetime=honse_data.A_LOT_OF_FRAMES,
            center_on=self.inflicted_upon,
            hazard_set_radius_growth_time=30,
            active_full_radius_duration=honse_data.A_LOT_OF_FRAMES,
            active_radius_growth_time=1,
            color=(255,255,0,85),
            active_color=(255,255,255,32),
            immune_timer=5,
            immune_pokemon=[self.inflicted_upon]            )
        self.hazard = CenterOfAttentionHazard(options, self.inflicted_upon.position, self.radius, self.game, self.source, self.inflicted_by)

    def on_removal(self):
        self.hazard.end_effect()

@dataclass
class BasicDamagingEffectOptions:
    lifetime: int = 1800
    damage: float = 1/32
    cooldown: int = 300
    status_icon: str = ""
    status_name: str = ""
    tags: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    overrides: list = field(default_factory=list)
    infliction_message: str = ""
    activation_message: str = ""

@dataclass
class PoisonEffectOptions:
    lifetime: int = 1800
    damage: float = 1/16
    cooldown: int = 300
    badly_poisoned: bool = False
    damage_growth: float = 0

CURSE_DEFAULT_OPTIONS = BasicDamagingEffectOptions(damage=1/4,
                                                   cooldown=1350,
                                                   lifetime=5400,
                                                   status_icon="curse",
                                                   status_name="CurseEffect",
                                                   tags=[EffectTag.CURSE],
                                                   blocks=[EffectTag.CURSE],
                                                   infliction_message="USER cut its HP to curse TARGET!",
                                                   activation_message="TARGET is hurt by the curse!")
TOXIC_DEFAULT_OPTIONS = PoisonEffectOptions(damage=1/64, damage_growth=1/64, cooldown=225, badly_poisoned=True)
class DamagingVolatileEffect(EffectInterface):
    def __init__(self,
             options: BasicDamagingEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.status_icon = options.status_icon
        self.name = options.status_name
        self.damage = options.damage # decimal representing portion of max hp
        self.damage_cooldown = options.cooldown
        self.max_damage_cooldown = options.cooldown
        self.triggers = [EffectTrigger.END_OF_TURN]
        self.tags = options.tags
        self.blocks = options.blokcs
        self.overrides = options.overrides
        self.infliction_message = options.infliction_message
        self.activation_message = options.activation_message
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        damage = self.damage * (self.max_lifetime / self.max_damage_cooldown)
        return honse_data.MAX_EFFECT_VALUE * damage

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        self.display_message(self.infliction_message)

    def display_message(self, message):
        if len(message):
            try:
                user = self.inflicted_by.name
            except AttributeError:
                user = ""
            try:
                target = self.inflicted_upon.name
            except AttributeError:
                target = ""
            message = message.replace("USER", user).replace("TARGET", target)
            self.game.display_message(message, self.text_size, [0, 0, 0])

    def end_of_turn(self):
        self.damage_cooldown -= 1
        if self.damage_cooldown <= 0 and not self.inflicted_upon.is_fainted():
            self.activate(EffectTrigger.END_OF_TURN, None)
            self.damage_cooldown = self.max_damage_cooldown

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.END_OF_TURN:
            self.display_message(self.activation_message)
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
        return input_value

class BurnEffect(EffectInterface):
    def __init__(self,
             options: BasicDamagingEffectOptions,
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
                return self.stats[stat]
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
             options: BasicDamagingEffectOptions,
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
                return self.stats[stat]
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
             options: PoisonEffectOptions,
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
             options: None,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.status_icon = "paralysis"
        self.name = "ParalysisEffect"
        self.damage = 1/16 # decimal representing portion of max hp
        self.procs_remaining = 4
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
        super().__init__(game, source, inflicted_by, inflicted_upon)
        
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

    def update(self):
        if self.procs_remaining <= 0:
            self.lifetime = 0
        super().update()

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} was paralyzed!", self.text_size, [0, 0, 0])

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.AFTER_USE_MOVE:
            self.game.display_message(f"{self.inflicted_upon.name} is hurt by its paralysis!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
            self.procs_remaining -= 1
        elif effect == EffectTrigger.STAT_MODIFICATION:
            stat = kwargs["stat"]
            if stat in self.stats:
                return self.stats[stat]
            return input_value
        elif effect == EffectTrigger.MOVE_SPEED_MODIFICATION:
            return input_value * self.move_speed_modifier
        return input_value

class PartiallyTrappedEffect(EffectInterface):
    def __init__(self,
             options: BasicDamagingEffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.status_icon = "bound"
        self.name = "PartiallyTrappedEffect"
        self.damage = options.damage # decimal representing portion of max hp
        self.damage_cooldown = options.cooldown
        self.max_damage_cooldown = options.cooldown
        self.move_speed_modifier = 0.5
        self.triggers = [
            EffectTrigger.END_OF_TURN,
            EffectTrigger.MOVE_SPEED_MODIFICATION
            ]
        self.tags = [EffectTag.PARTIALLY_TRAPPED]
        self.blocks = [EffectTag.PARTIALLY_TRAPPED]
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return 600

    def can_inflict(self):
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
            self.game.display_message(f"{self.inflicted_upon.name} is hurt by {self.source.move.name}!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
        elif effect == EffectTrigger.MOVE_SPEED_MODIFICATION:
            if pokemon_types["Ghost"] not in self.inflicted_upon.get_types():
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
                return True
            else:
                return False
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
        return 600

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.MOVE_LOCK:
            return True
        return input_value

@dataclass
class MoveLockOptions:
    lifetime: int = 300
    # True locks all moves
    locked_moves: bool|list = True
class MoveLockEffect(EffectInterface):
    def __init__(self,
             options: MoveLockOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "MoveLockEffect"
        self.status_icon = "locked move"
        self.locked_moves = options.locked_moves
        self.triggers = [EffectTrigger.MOVE_LOCK]
        self.tags = []
        self.blocks = []
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)
        
    def get_effect_value(self):
        return self.lifetime // -4

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.MOVE_LOCK:
            if self.locked_moves is True:
                return True
            elif kwargs["move"] in self.locked_moves:
                return True
        return input_value

class ImprisonEffect(MoveLockEffect):
    def __init__(self,
        options: EffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "MoveLockEffect"
        self.status_icon = "locked move"
        self.locked_moves = inflicted_upon.current_moves
        self.triggers = [EffectTrigger.MOVE_LOCK]
        self.tags = []
        self.blocks = []
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)
        
    def get_effect_value(self):
        return self.lifetime // -4

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.MOVE_LOCK:
            if self.locked_moves is True:
                return True
            elif kwargs["move"] in self.locked_moves:
                return True
        return input_value


class BideEffect(EffectInterface):
    def __init__(self,
             options: None,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "BideEffect"
        self.status_icon = "locked move"
        self.triggers = [EffectTrigger.MOVE_LOCK, EffectTrigger.ON_HIT_BY_MOVE, EffectTrigger.ON_USE_MOVE, EffectTrigger.AFTER_USE_MOVE]
        self.tags = [EffectTag.BIDE]
        self.blocks = [EffectTag.BIDE]
        self.overrides = []
        self.stored_damage = 0
        self.used_bide = False
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon)

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.MOVE_LOCK:
            if kwargs["move"] is not MOVES["Bide"]:
                return True
        elif effect == EffectTrigger.ON_HIT_BY_MOVE:
            self.stored_damage += kwargs["attack"].damage_dealt
        elif effect == EffectTrigger.ON_USE_MOVE:
            kwargs["attack"].fixed_damage_amount = self.stored_damage * 2
            self.used_bide = True
        elif effect == EffectTrigger.AFTER_USE_MOVE:
            if self.used_bide:
                self.end_effect()
        return input_value

class MustRechargeEffect(MoveLockEffect):
    def __init__(self,
             options: EffectOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        options = MoveLockOptions(lifetime=options.lifetime)
        super().__init__(options=options, game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon)

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()
        
    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} must recharge!", self.text_size, [0, 0, 0])

    def get_effect_value(self):
        # having the recharge status decrease cooldowns for being a negative status feels weird, so this is 0
        return 0

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
                return self.stats[stat]
        return input_value

@dataclass
class CritRatioOptions:
    modifier: int
    lifetime: int = 1200
    message: str = ""
class CritRatioEffect(EffectInterface):
    def __init__(self,
             options: CritRatioOptions,
             game=None,
             source=None,
             inflicted_by=None,
             inflicted_upon=None
             ):
        self.name = "CritRatioEffect"
        if options.modifier > 0:
            self.status_icon = "stat boost"
        else:
            self.status_icon = "stat drop"
        self.modifier = options.modifier
        self.triggers = [EffectTrigger.CRIT_STAGE_MODIFICATION]
        self.tags = []
        self.blocks = []
        self.overrides = []
        self.message = options.message
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return -200 * self.modifier

    def after_infliction(self):
        self.display_inflicted_message()
        super().after_infliction()

    def display_inflicted_message(self):
        if len(self.message):
            try:
                user = self.inflicted_by.name
            except AttributeError:
                user = ""
            try:
                target = self.inflicted_upon.name
            except AttributeError:
                target = ""
            message = self.message.replace("USER", user).replace("TARGET", target)
            self.game.display_message(message, self.text_size, [0, 0, 0])

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.CRIT_STAGE_MODIFICATION:
            return input_value + self.modifier
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
            return input_value * self.modifier
        return input_value

class DragEffect(EffectInterface):
    def __init__(self,
            options: MoveSpeedModificationEffectOptions,
            game=None,
            source=None,
            inflicted_by=None,
            inflicted_upon=None
            ):
        self.name = "DragEffect"
        self.modifier = options.modifier
        self.status_icon = ""
        self.triggers = [EffectTrigger.DRAG_MODIFICATION]
        self.tags = []
        self.blocks = []
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.DRAG_MODIFICATION:
            return input_value * self.modifier
        return input_value

class AccelerationEffect(EffectInterface):
    def __init__(self,
            options: MoveSpeedModificationEffectOptions,
            game=None,
            source=None,
            inflicted_by=None,
            inflicted_upon=None
            ):
        self.name = "AccelerationEffect"
        self.modifier = options.modifier
        self.status_icon = ""
        self.triggers = [EffectTrigger.ACCELERATION_MODIFICATION]
        self.tags = []
        self.blocks = []
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.ACCELERATION_MODIFICATION:
            return input_value * self.modifier
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

@dataclass
class TypeEffectivenessOverrideOptions:
    lifetime: int = 1200
    type_overrides: dict = field(default_factory=dict)
class TypeEffectivenessOverrideEffect(EffectInterface):
    def __init__(self,
        options: TypeEffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        self.name = "TypeOverrideEffect"
        self.status_icon = "identified"
        self.triggers = [EffectTrigger.TYPE_EFFECTIVENESS_OVERRIDE]
        self.tags = []
        self.blocks = []
        self.overrides = []
        self.type_overrides = options.type_overrides
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return 0

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.TYPE_EFFECTIVENESS_OVERRIDE:
            input_value.update(self.type_overrides)
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
                for effect in self.inflicted_upon.effects:
                    if EffectTag.DEFENSE_CURL in effect.tags:
                        attack.power *= 2
                        break
        return input_value

class ChargeEffect(EffectInterface):
    def __init__(self,
        options: EffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        self.name = "ChargeEffect"
        self.status_icon = "charged"
        self.triggers = [EffectTrigger.ON_USE_MOVE]
        self.tags = [EffectTag.CHARGE]
        self.modifier = 2
        self.blocks = [EffectTag.CHARGE]
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return -300

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.ON_USE_MOVE:
            attack = kwargs["attack"]
            if attack.type == pokemon_types["Electric"]:
                attack.power *= self.modifier
        return input_value

class HelpingHandEffect(EffectInterface):
    def __init__(self,
        options: EffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        self.name = "HelpingHandEffect"
        self.status_icon = "stat boost"
        self.triggers = [EffectTrigger.ON_USE_MOVE]
        self.tags = [EffectTag.HELPING_HAND]
        self.modifier = 1.5
        self.blocks = [EffectTag.HELPING_HAND]
        self.overrides = []
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return -300

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_by.name} is ready to help {self.inflicted_upon.name}!", self.text_size, [0, 0, 0])

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.ON_USE_MOVE:
            attack = kwargs["attack"]
            if attack.category != MoveCategories.STATUS:
                attack.power *= self.modifier
                self.lifetime = 0
        return input_value

class Electrify(EffectInterface):
    def __init__(self,
        options: EffectOptions,
        game=None,
        source=None,
        inflicted_by=None,
        inflicted_upon=None
        ):
        self.name = "ChargeEffect"
        self.status_icon = "charged"
        self.triggers = [EffectTrigger.ON_USE_MOVE]
        self.tags = [EffectTag.ELECTRIFY]
        self.blocks = []
        self.overrides = [EffectTag.ELECTRIFY]
        super().__init__(game=game, source=source, inflicted_by=inflicted_by, inflicted_upon=inflicted_upon, lifetime=options.lifetime)

    def get_effect_value(self):
        return 0

    def activate(self, effect: EffectTrigger, input_value, **kwargs):
        if effect == EffectTrigger.ON_USE_MOVE:
            attack = kwargs["attack"]
            attack.type = pokemon_types["Electric"]
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
            try:
                target = self.inflicted_upon.name
            except AttributeError:
                target = ""
            message = self.message.replace("USER", user).replace("TARGET", target)
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
        immunity_wears_off = []
        for mon in self.temporary_immunity:
            self.temporary_immunity[mon] -= 1
            if self.temporary_immunity[mon] <= 0:
                immunity_wears_off.append(mon)
        for mon in immunity_wears_off:
            del self.temporary_immunity[mon]
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
            # using 3/4 * target.radius to see if it makes the collisions look a bit better
            return distance < (self.get_active_radius() + (3 * target.radius // 4))

    def inflict_knockback(self, target):
        if self.knockback > 0:
            axis = (self.position - target.position) / np.linalg.norm(self.position - target.position)
            target.velocity = -axis * np.linalg.norm(target.velocity)
            target.current_speed += self.knockback

    def __str__(self):
        return f"{self.name} inflicted at ({self.position[0]}, {self.position[1]}) by {self.inflicted_by.name}'s {self.source.move.name}."

class CenterOfAttentionHazard(Hazard):
    def inflict_knockback(self, target):
        if target.frames_since_collision_with_other_character < 60 or target.frames_tangible < 60:
            return
        if self.source.move.name == "Rage Powder" and pokemon_types["Grass"] in target.current_types:
            return
        distance = np.linalg.norm(self.position - target.position)
        target.velocity = ((self.position-target.position) / distance) * target.current_speed

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
        self.wall_bounce_attack_cooldown = 60
        self.tried_to_attack_this_frame = False
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
        self.drag_modifier = 1
        self.acceleration_modifier = 1
        self.recalculate()
        # these next two variables are used for center of effect hazards to ensure that a pokemon that was just dealt knockback is not pulled towards the center of effect
        # number of consecutive tangible frames
        self.frames_tangible = 0
        self.frames_since_collision_with_other_character = 0
        # moves start on partial cooldown, but not less than 1 second
        for i in range(len(self.moves)):
            self.on_cooldown(i)
            self.cooldowns[i] /= 4
            if self.cooldowns[i] > 0 and self.cooldowns[i] < 60:
                self.cooldowns[i] = 60
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
            self.locked_moves[i] = activate_effect(EffectTrigger.MOVE_LOCK, self, False, {"move":self.current_moves[i]})
        self.move_speed_modifier = activate_effect(EffectTrigger.MOVE_SPEED_MODIFICATION, self, 1)
        self.drag_modifier = activate_effect(EffectTrigger.DRAG_MODIFICATION, self, 1)
        self.acceleration_modifier = activate_effect(EffectTrigger.ACCELERATION_MODIFICATION, self, 1)
        self.current_types = activate_effect(EffectTrigger.TYPE_OVERRIDE, self, self.types)
        self.current_types = activate_effect(EffectTrigger.TYPE_ADDITION, self, self.current_types)

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
            return self.locked_moves[move_id]
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
        type_overrides = activate_effect(EffectTrigger.TYPE_EFFECTIVENESS_OVERRIDE, self, type_overrides)
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
        return int(stat_value)

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

    def get_acceleration(self):
        return self.acceleration * self.acceleration_modifier

    def get_drag(self):
        return self.drag * self.drag_modifier

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
        if not self.is_fainted() and not self.game.game_end and not self.tried_to_attack_this_frame:
            for i in range(len(self.moves)):
                move = self.get_move(i)
                if self.cooldowns[i] == 0 and not self.is_move_locked(i):
                    if move.is_valid_target(self, target) == False:
                        continue
                    self.tried_to_attack_this_frame = True
                    can_move = True
                    # if an effect that would block the move usage triggers, it returns True
                    can_move = not activate_effect(EffectTrigger.ON_TRY_USE_MOVE, self, False, {"move": move})
                    if can_move:
                        self.game.display_message(f"{self.name} used {move.name}!", 24, [0, 0, 0])
                        attack = move.on_use(self, target=target)
                        successfully_moved = attack.success
                        if successfully_moved:
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
                        activate_effect(EffectTrigger.AFTER_MOVE_USE_COOLDOWN, self, effect_kwargs={"attack":attack})
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
            self.use_move(self)

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

        self.frames_since_collision_with_other_character = 0
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
            if self.wall_bounce_attack_cooldown > 0:
                self.wall_bounce_attack_cooldown -= 1
            self.frames_since_collision_with_other_character += 1
            if self.is_intangible():
                self.frames_tangible = 0
            else:
                self.frames_tangible += 1

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

    def do_damage(self, source, damage, attack=None, silent=False):
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
            activate_effect(EffectTrigger.ON_FAINT, self, effect_kwargs={"attack": attack})
            self.game.display_message(f"{self.name} fainted!", 24, [127, 0, 0])
        return damage


    def do_healing(self, source, healing,  silent=False, bypass_heal_block=False):
        if self.is_fainted() or healing==0 or self.game.game_end:
            return 0
        # afaik nothing bypasses heal block other than z moves, but its good to have the option
        if not bypass_heal_block:
            heal_block_activated = activate_effect(EffectTrigger.HEAL_BLOCK, self, False)
            if heal_block_activated:
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
        self.game.message_log.append([f"{self.name} was inflicted with {type(status)} by {status.inflicted_by.name}'s {status.source.move.name}.", False])
        return True

    def remove_status(self, status):
        self.effects.remove(status)
        status.on_removal()
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
        self.contact = options.contact
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
            if self.base_knockback is None:
                self.base_knockback = 0
            if self.hitstop is None:
                self.hitstop = 30
            if self.animation is None:
                if self.target in [MoveTarget.USER, MoveTarget.ALLY]:
                    self.animation = honse_particles.buff_spawner_animation
                else:
                    self.animation = honse_particles.debuff_spawner_animation
            if self.sound is None:
                # todo add sounds here
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

    def has_effect(self, tag: EffectTag, affects_user: bool|None=None, search_secondaries: bool=True, search_non_secondaries: bool=True):
        effects_to_search = []
        if search_secondaries:
            effects_to_search += self.secondary_effects
        if search_non_secondaries:
            effects_to_search += self.non_secondary_effects
        for effect_group in effects_to_search:
            for effect in effect_group.effects:
                if effect.affects_user == affects_user or affects_user is None:
                    effect_object = effect.effect(effect.options)
                    if tag in effect_object.tags:
                        return True
        return False

    def get_default_cooldown(self):
        # cooldown scales on power plus a flat 10 because i want high power moves to have better dps
        if self.power == 0:
            cooldown = 240
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
        if self.target == MoveTarget.USER:
            return user is target
        elif self.target == MoveTarget.ENEMY:
            return not user.same_team(target)
        elif self.target == MoveTarget.ALLY:
            return user.same_team(target)
        elif self.target == MoveTarget.OTHERS:
            return user is not target
        else:
            return False

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
        self.contact = self.move.contact
        self.initial_use = initial_use
        self.fixed_damage_amount = 0
        self.damage_dealt = 0
        self.position = np.array([0, 0], dtype=float)
        self.power = self.move.power
        self.type = self.move.type
        self.attack_stat_override = self.move.attack_stat_override
        self.defense_stat_override = self.move.defense_stat_override
        self.ignore_attack_modifiers = self.move.ignore_attack_modifiers
        self.ignore_defense_modifiers = self.move.ignore_defense_modifiers
        self.foul_play = self.move.foul_play
        self.defender_protect = False
        self.defender_endure = False
        self.attacker_feint = False
        self.protect_activated = False
        self.endure_activated = False
        self.animation = self.move.animation
        self.sound = self.move.sound
        self.success = False
        self.failure_message = "But it failed!"
    
    def trigger_weather_effects(self):
        if self.game.weather == Weather.HARSH_SUNLIGHT:
            if self.move.category != MoveCategories.STATUS:
                if self.type == pokemon_types["Fire"]:
                    self.power *= 1.5
                elif self.type == pokemon_types["Water"]:
                    self.power *= 0.5
        elif self.game.weather == Weather.EXTREMELY_HARSH_SUNLIGHT:
            if self.move.category != MoveCategories.STATUS:
                if self.type == pokemon_types["Fire"]:
                    self.power *= 1.5
                elif self.type == pokemon_types["Water"]:
                    self.power = 0
                    self.failure_message = "The Water-type attack evaporated in the harsh sunlight!"
        elif self.game.weather == Weather.RAIN:
            if self.move.category != MoveCategories.STATUS:
                if self.type == pokemon_types["Water"]:
                    self.power *= 1.5
                elif self.type == pokemon_types["Fire"]:
                    self.power *= 0.5
        elif self.game.weather == Weather.HEAVY_RAIN:
            if self.move.category != MoveCategories.STATUS:
                if self.type == pokemon_types["Water"]:
                    self.power *= 1.5
                elif self.type == pokemon_types["Fire"]:
                    self.power = 0
                    self.failure_message = "The Fire-type attack fizzled out in the heavy rain!"

    def trigger_on_use_effects(self):
        activate_effect(
            effect_trigger=EffectTrigger.ON_USE_MOVE,
            character=self.user,
            effect_kwargs={"attack":self}
            )
        if self.user is not self.target:
            activate_effect(
                effect_trigger=EffectTrigger.ON_TARGETED_BY_MOVE,
                character=self.target,
                effect_kwargs={"attack":self}
                )

    def trigger_on_hit_effects(self):
        if self.user is not self.target:
            activate_effect(
                effect_trigger=EffectTrigger.ON_LANDING_MOVE,
                character=self.user,
                effect_kwargs={"attack":self}
                )
            activate_effect(
                effect_trigger=EffectTrigger.ON_HIT_BY_MOVE,
                character=self.target,
                effect_kwargs={"attack":self}
                )

    def trigger_after_use_effects(self):
        activate_effect(
            effect_trigger=EffectTrigger.AFTER_USE_MOVE,
            character=self.user,
            effect_kwargs={"attack":self}
            )
        if self.user is not self.target:
            activate_effect(
                effect_trigger=EffectTrigger.AFTER_TARGETED_BY_MOVE,
                character=self.target,
                effect_kwargs={"attack":self}
                )

    def apply_secondaries(self):
        for effect_group in self.move.secondary_effects:
            if random.random() <= effect_group.chance:
                for secondary in effect_group.effects:
                    if secondary.affects_user:
                        secondary.effect(secondary.options, self.game, self, self.user, self.user)
                    elif not self.protect_activated:
                        secondary.effect(secondary.options, self.game, self, self.user, self.target)

    def apply_non_secondaries(self):
        if self.damage_dealt > 0 or self.move.category == MoveCategories.STATUS:
            for effect_group in self.move.non_secondary_effects:
                for non_secondary in effect_group.effects:
                    if non_secondary.affects_user:
                        effect = non_secondary.effect(non_secondary.options, self.game, self, self.user, self.user)
                        if effect.success:
                            self.success = True
                    elif not self.protect_activated:
                        effect = non_secondary.effect(non_secondary.options, self.game, self, self.user, self.target)
                        if effect.success:
                            self.success = True

    def create_spread_hazard(self):
        if self.initial_use and self.move.spread_radius > 0:
            x, y = self.position[0], self.position[1]
            hazard_options = deepcopy(self.move.spread_options)
            if self.user is not self.target:
                hazard_options.immune_pokemon = [self.user, self.target]
            else:
                hazard_options.immune_pokemon = [self.user]
            hazard_options.immune_teams = []
            if not self.move.spread_can_hit_allies:
                hazard_options.immune_teams.append(self.user.team)
            if not self.move.spread_can_hit_enemies:
                enemy_teams = list(range(self.user.game.number_of_teams))
                enemy_teams.remove(self.user.team)
                hazard_options.immune_teams += enemy_teams
            hazard_options.color = self.type.hazard_color
            hazard_options.effect = MoveEffect
            hazard_options.effect_options = MoveEffectOptions(move=self.move)
            Hazard(hazard_options, (x, y), self.move.spread_radius, self.game, self, self.user)
            self.success = True

    def play_effects(self, follow_character=None):
        x, y = self.position[0], self.position[1]
        if self.sound is not None:
            self.game.play_sound(self.sound)
        if self.animation is not None:
            if follow_character is not None:
                print(self.move.name)
                self.animation(self.game, x, y, follow_character=follow_character)
            else:
                self.animation(self.game, x, y)

    def knockback_modifier(self, current_hp: int, damage: int):
        # knockback is multiplied by knockback scaling
        # knockback scaling is equal to 1+((knockback_scaling * damage)/current_hp)
        # damage cannot exceed current HP
        knockback_modification = 1 + (damage / max(1, damage, current_hp))
        return knockback_modification
   
    # all of the stuff that happens when a move is activated is broken up into small functions
    # the reason that things are so separated is so that moves with advanced effects can inherit
    # and overwrite the effects that they need to overwrite without touching anything they dont need to
    def activate(self):
        self.get_position()
        self.trigger_on_use_effects()
        self.activte_protect()
        self.do_damage()
        self.after_doing_damage()
        self.apply_non_secondaries()
        self.trigger_after_use_effects()
        self.create_spread_hazard()
        self.determine_effects_to_play()

    def get_position(self):
        self.position = self.target.position
        
    def activte_protect(self):
        self.protect_activated = self.defender_protect and not self.attacker_feint and self.user is not self.target
        if self.protect_activated:
            self.user.game.display_message(f"{self.target.name} protected itself!", 16, [0, 0, 0])
            self.failure_message = ""

    def do_damage(self):
        if (self.power > 0 or self.fixed_damage_amount > 0) and self.move.category != MoveCategories.STATUS and not self.protect_activated:
            # damage calc
            damage, crit = damage_formula(self, self.user, self.target)
            # display messages and vfx
            if crit:
                if self.move.spread_radius > 0:
                    self.user.game.display_message(f"A critical hit on {self.target.name}!", 16, [0, 0, 0])
                else:
                    self.user.game.display_message("A critical hit!", 16, [0, 0, 0])
            effectiveness_quote, effectiveness_sound = get_type_effectiveness_stuff(self, self.target)
            if effectiveness_quote:
                self.game.display_message(effectiveness_quote, 16, [0, 0, 0])
            self.target.hit_sound_to_play = effectiveness_sound
            # do check endure
            if damage >= self.target.hp and self.defender_endure:
                damage = self.target.hp - 1
                self.endure_activated = True
                self.game.display_message(f"{self.target.name} endured the hit!", 16, [0, 0, 0])
            self.damage_dealt = self.target.do_damage(self.user, damage, self)
            # knockback
            if self.damage_dealt > 0:
                knockback_mod = self.knockback_modifier(self.target.hp, damage)
                knockback = self.move.base_knockback * knockback_mod
                self.target.current_speed += knockback
                # drain and recoil
                if self.move.drain > 0:
                    healing = max(1, int(self.damage_dealt * self.move.drain))
                    if self.user.do_healing(self.user, healing, silent=True) > 0:
                        self.user.game.display_message(f"{self.target.name} had its energy drained!", 16, [0, 0, 0])
                if self.move.recoil > 0:
                    recoil = max(1, int(self.damage_dealt * self.move.recoil))
                    if self.user.do_damage(self.user, recoil, silent=True) > 0:
                        self.user.game.display_message(f"{self.user.name} is damaged by recoil!", 16, [0, 0, 0])
    
    def after_doing_damage(self):
        if self.damage_dealt > 0 or self.endure_activated:
            self.trigger_on_hit_effects()
            self.apply_secondaries()
            self.success = True

    def determine_effects_to_play(self):
        if self.protect_activated:
            self.animation = lambda game, x, y: honse_particles.barrier_animation(game, x, y, "protect transparent")
            self.sound = "Protect shield hit"
            self.target.hitstop = 36
            self.play_effects()
        elif self.success:
            if self.target is self.user:
                follow_character = self.user
            else:
                self.target.hitstop = self.move.hitstop
                follow_character = None
            self.play_effects(follow_character=follow_character)
        elif len(self.failure_message):
            self.game.display_message(self.failure_message, 16, [0,0,0])

class BideAttack(Attack):
    def activate(self):
        self.unleashing_bide = False
        for effect in self.user.effects:
            if EffectTag.BIDE in effect.tags:
                self.unleashing_bide = True
                break
        super().activate()

    def apply_non_secondaries(self):
        if not self.unleashing_bide:
            effect = BideEffect(None, self.game, self, self.user, self.user)
            if effect.success:
                self.game.display_message(f"{self.user.name} is storing energy!", 16, [0,0,0])
                self.success = True
        super().apply_non_secondaries()

    def determine_effects_to_play(self):
        if not self.unleashing_bide and self.success:
            self.animation = honse_particles.buff_spawner_animation
            self.play_effects(follow_character=self.user)
        else:
            super().determine_effects_to_play()

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
    attack_class: ... = Attack
    crit_stage: int = 0
    contact: bool = False
    drain: float = 0
    recoil: float = 0
    attack_stat_override: str|None = None
    defense_stat_override: str|None = None
    ignore_attack_modifiers: bool = False
    ignore_defense_modifiers: bool = False
    fixed_damage: bool = False
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
        contact=True,
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=CooldownReductionEffect,options=CooldownReductionEffectOptions(cooldown_reduction_amount=80),affects_user=True)]
            )]),
    "giga drain": MoveOptions(drain=0.5),
    "heat wave": MoveOptions(
        accuracy=90,
        secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=BurnEffect,options=BasicDamagingEffectOptions(),affects_user=False)],
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
        contact=True,
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=StatStageEffect,options=StatOptions(positive=False,stats={"ATK":-1,"DEF":-1}),affects_user=True)]
                )]),
    "blizzard": MoveOptions(
        accuracy=70,
        secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=FreezeEffect,options=BasicDamagingEffectOptions(),affects_user=False)],
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
                effects=[MoveSecondary(effect=ParalysisEffect,options=BasicDamagingEffectOptions(),affects_user=False)],
                chance=0.3)]
        ),
    "endure": MoveOptions(
        animation=honse_particles.buff_spawner_animation,
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=EndureEffect,options=EffectOptions(lifetime=600),affects_user=True)]
                )],
        ),
    "protect": MoveOptions(
        animation=honse_particles.barrier_animation,
        sound="Protect",
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=ProtectEffect,options=ProtectOptions(),affects_user=True)]
                )],
        ),
    "kings shield": MoveOptions(
        animation=honse_particles.barrier_animation,
        sound="Protect",
        non_secondary_effects=[
            SecondaryGroup(
                effects=[MoveSecondary(effect=ProtectEffect,
                                       options=ProtectOptions(
                                           unprotected_categories=[MoveCategories.STATUS],
                                           contact_effect=StatStageEffect,
                                           contact_effect_options=StatOptions(positive=False,stats={"ATK":-2})),
                                       affects_user=True)]
                )],
        ),
    "bide": MoveOptions(
        attack_class=BideAttack,
        cooldown=750),
    "follow me": MoveOptions(
        animation=honse_particles.buff_spawner_animation,
        cooldown=1200,
        non_secondary_effects=[
            SecondaryGroup(
                effects=[
                    MoveSecondary(effect=CooldownReductionEffect,options=CooldownReductionEffectOptions(cooldown_reduction_amount=30),affects_user=True),
                    MoveSecondary(effect=CenterOfAttentionEffect,options=CenterOfAttentionOptions(),affects_user=True)]
            )]
        ),
    "spotlight": MoveOptions(
        animation=honse_particles.debuff_spawner_animation,
        cooldown=1200,
        hitstop=30,
        non_secondary_effects=[
            SecondaryGroup(
                effects=[
                    MoveSecondary(effect=CenterOfAttentionEffect,options=CenterOfAttentionOptions(),affects_user=False)]
            )]
        ),
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
    "Protect": Move(
        name="Protect",
        pkmn_type=pokemon_types["Normal"],
        category=MoveCategories.STATUS,
        target=MoveTarget.USER,
        power=0,
        options=MOVE_OPTIONS["protect"]),
    "Endure": Move(
        name="Endure",
        pkmn_type=pokemon_types["Normal"],
        category=MoveCategories.STATUS,
        target=MoveTarget.USER,
        power=0,
        options=MOVE_OPTIONS["endure"]),
    "Bide": Move(
        name="Bide",
        pkmn_type=pokemon_types["Normal"],
        category=MoveCategories.PHYSICAL,
        target=MoveTarget.ENEMY,
        power=0,
        options=MOVE_OPTIONS["bide"]),
    "Follow Me": Move(
        name="Follow Me",
        pkmn_type=pokemon_types["Normal"],
        category=MoveCategories.STATUS,
        target=MoveTarget.USER,
        power=0,
        options=MOVE_OPTIONS["follow me"]),
    "Spotlight": Move(
        name="Spotlight",
        pkmn_type=pokemon_types["Normal"],
        category=MoveCategories.STATUS,
        target=MoveTarget.OTHERS,
        power=0,
        options=MOVE_OPTIONS["spotlight"]),
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
    "King's Shield": Move(
        name="King's Shield",
        pkmn_type=pokemon_types["Steel"],
        category=MoveCategories.STATUS,
        target=MoveTarget.USER,
        power=0,
        options=MOVE_OPTIONS["kings shield"]),
    
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
    unique_effects = []
    for move_name, move_dict in data.items():
        pass
    '''
        if len(move_dict["effects"]) == 0:
            continue
        for effect in move_dict["effects"]:
            exists = False
            for existing_effect in unique_effects:
                if existing_effect == effect:
                    exists = True
                    break
            if not exists:
                unique_effects.append(effect)

        text += move_name + "\n"
        for key, value in move_dict.items():
            text += f"\t{key}: {value}\n"
        if len(value["effects"]) == 0 and value["category"] == "Status":
            #print(key)
            pass
        '''
    '''
    with open("volatiles.txt", "w") as outfile:
        text = ""
        volatiles = []
        for effect in unique_effects:
            print(effect["name"])
            if effect["name"] == "Volatile Status":
                for detail in effect["details"]:
                    if detail not in volatiles:
                        volatiles.append(detail)
                        text += f"{detail}\n"

        outfile.write(text)
    '''