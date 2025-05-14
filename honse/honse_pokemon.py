from ast import Dict
from io import BytesIO
import pygame
import random
import math
import honse_data
import honse_particles
import enum
import numpy as np
from PIL import Image, ImageDraw
import os

#may break things
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class MoveCategories(enum.Enum):
    PHYSICAL = 0
    SPECIAL = 1
    STATUS = 2

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


def damage_formula(move, attacker, defender, **kwargs):
    if "spread" in kwargs:
        spread = kwargs["spread"]
    else:
        spread = False
    if "attack_override" in kwargs:
        attack_stat = kwargs["attack_override"]
    else:
        attack_stat = "SPA" if move.category == MoveCategories.SPECIAL else "ATK"
    if "defense_override" in kwargs:
        defense_stat = kwargs["defense_override"]
    else:
        defense_stat = "SPD" if move.category == MoveCategories.SPECIAL else "DEF"
    if "ignore_attack_modifiers" in kwargs:
        ignore_attack_modifiers = kwargs["ignore_attack_modifiers"]
    else:
        ignore_attack_modifiers = False
    if "ignore_defense_modifiers" in kwargs:
        ignore_defense_modifiers = kwargs["ignore_defense_modifiers"]
    else:
        ignore_defense_modifiers = False
    if "foul_play" in kwargs and kwargs["foul_play"]:
        attack = defender.get_modified_stat(attack_stat)
        unmodified_attack = defender.get_modified_stat(attack_stat, True)
    else:
        attack = attacker.get_modified_stat(attack_stat)
        unmodified_attack = attacker.get_modified_stat(attack_stat, True)
    defense = defender.get_modified_stat(defense_stat)
    unmodified_defense = defender.get_modified_stat(defense_stat, True)
    crit_mod = attacker.crit_calc(move, defender)
    if crit_mod > 1:
        attack = max(attack, unmodified_attack)
        defense = min(defense, unmodified_defense)
    damage = (
        ((((2 * attacker.level) / 5) + 2) * move.current_bp * (attack / defense)) / 50
    ) + 2
    # spread is only true for the non-primary target of spread moves
    damage *= crit_mod
    if spread:
        damage *= 0.5
    damage *= defender.get_type_matchup(move.type)
    if move.type in attacker.types:
        damage *= 1.5
    damage *= random.randint(85, 100) / 100
    return max(1, math.floor(damage)), crit_mod > 1


class EffectTypes(enum.Enum):
    NON_VOLATILE = 0
    ATTACK_MODIFICATION = 1
    DEFENSE_MODIFICATION = 2
    SPECIAL_ATTACK_MODIFICATION = 3
    SPECIAL_DEFENSE_MODIFICATION = 4
    SPEED_MODIFICATION = 5
    ACCELERATION_MODIFICATION = 6
    DRAG_MODIFICATION = 7
    END_OF_TURN = 8
    MOVE_SPEED_MODIFICATION = 9
    BASE_ATTACK_OVERRIDE = 10
    BASE_DEFENSE_OVERRIDE = 11
    BASE_SPECIAL_ATTACK_OVERRIDE = 12
    BASE_SPECIAL_DEFENSE_OVERRIDE = 13
    BASE_SPEED_OVERRIDE = 14
    MOVE_LOCK = 15
    BEFORE_ATTACK = 16
    AFTER_ATTACK = 17
    CRIT_STAGE = 18
    CRIT_RESIST = 19
    CRIT_DAMAGE = 20
    ATTACK_STAGE = 21
    DEFENSE_STAGE = 22
    SPECIAL_ATTACK_STAGE = 23
    SPECIAL_DEFENSE_STAGE = 24
    SPEED_STAGE = 25
    COOLDOWN_REDUCTION = 26
    TARGET_BASE_POWER_MODIFICATION = 27
    ATTACKER_BASE_POWER_MODIFICATION = 28

STAT_EFFECTS = {
    "ATK": {"override": EffectTypes.BASE_ATTACK_OVERRIDE,
            "modification": EffectTypes.ATTACK_MODIFICATION,
            "stage": EffectTypes.ATTACK_STAGE},
    "DEF": {"override": EffectTypes.BASE_DEFENSE_OVERRIDE,
            "modification": EffectTypes.DEFENSE_MODIFICATION,
            "stage": EffectTypes.DEFENSE_STAGE},
    "SPA": {"override": EffectTypes.BASE_SPECIAL_ATTACK_OVERRIDE,
            "modification": EffectTypes.SPECIAL_ATTACK_MODIFICATION,
            "stage": EffectTypes.SPECIAL_ATTACK_STAGE},
    "SPD": {"override": EffectTypes.BASE_SPECIAL_DEFENSE_OVERRIDE,
            "modification": EffectTypes.SPECIAL_DEFENSE_MODIFICATION,
            "stage": EffectTypes.SPECIAL_ATTACK_STAGE},
    "SPE": {"override": EffectTypes.BASE_SPEED_OVERRIDE,
            "modification": EffectTypes.SPEED_MODIFICATION,
            "stage": EffectTypes.SPEED_STAGE}}
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
pokemon_types["Water"].default_hitstop = 20
pokemon_types["Grass"].default_hitstop = 25
pokemon_types["Electric"].default_hitstop = 45
pokemon_types["Psychic"].default_hitstop = 20
pokemon_types["Ice"].default_hitstop = 60
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
pokemon_types["Water"].default_animation = honse_particles.splash_animation
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

class Effect:
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        self.text_size = 16
        if not hasattr(self, "effect_types"):
            self.effect_types = []
        if inflicted_by is not None:
            self.game = inflicted_by.game
        else:
            # this will only happen when getting effect value
            self.game = None
        self.inflicted_by = inflicted_by
        self.inflicted_upon = inflicted_upon
        self.lifetime = honse_data.A_LOT_OF_FRAMES
        if "lifetime" in kwargs:
            self.lifetime = kwargs["lifetime"]
        self.max_lifetime = self.lifetime
        if "status_icon" in kwargs:
            self.status_icon = kwargs["status_icon"]
        if "source" in kwargs:
            self.source = kwargs["source"]
        else:
            self.source = None
        if "get_effect_value" in kwargs and kwargs["get_effect_value"]:
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

    def infliction(self):
        success = self.inflicted_upon.inflict_status(self)
        if success:
            self.display_inflicted_message()
        return success

    def display_inflicted_message(self):
        pass

    def activate(self, effect, **kwargs):
        pass

    def update(self):
        if self.lifetime <= 0:
            self.end_effect()
        else:
            self.lifetime -= 1

    def end_of_turn(self):
        pass

    def end_effect(self):
        self.inflicted_upon.remove_status(self)

class LeechSeedEffect(Effect):
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        self.damage = 1/16 # decimal representing portion of max hp
        self.damage_countdown = 300
        self.max_damage_countdown = 300
        self.effect_types = [EffectTypes.END_OF_TURN]
        super().__init__(inflicted_by, inflicted_upon, lifetime=1800, status_icon="seeded", **kwargs)

    def get_effect_value(self):
        return 900

    def infliction(self):
        success = False
        if len([effect for effect in self.inflicted_upon.effects if type(effect) is type(self)]) == 0:
            success = self.inflicted_upon.inflict_status(self)
        if success:
            self.display_inflicted_message()
        return success

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} was seeded!", self.text_size, [0, 0, 0])

    def end_of_turn(self):
        self.damage_countdown -= 1
        if self.damage_countdown <= 0 and not self.inflicted_upon.is_fainted():
            self.activate(EffectTypes.END_OF_TURN)
            self.damage_countdown = self.max_damage_countdown

    def activate(self, effect, **kwargs):
        if effect == EffectTypes.END_OF_TURN:
            self.game.display_message(f"{self.inflicted_upon.name}'s health is sapped by Leech Seed!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            healing = self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
            self.inflicted_by.do_healing(self.inflicted_by, healing, silent=True)

class BurnEffect(Effect):
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        self.damage = 1/16 # decimal representing portion of max hp
        self.damage_countdown = 300
        self.max_damage_countdown = 300
        self.effect_types = [
            EffectTypes.END_OF_TURN,
            EffectTypes.ATTACK_MODIFICATION,
            EffectTypes.NON_VOLATILE
        ]
        super().__init__(inflicted_by, inflicted_upon, lifetime=1800, status_icon="burn", **kwargs)
        
    def get_effect_value(self):
        return 900

    def infliction(self):
        if pokemon_types["Fire"] in self.inflicted_upon.types:
            success = False
        else:
            success = self.inflicted_upon.inflict_status(self)
        if success:
            self.display_inflicted_message()
        return success

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} was burned!", self.text_size, [0, 0, 0])

    def end_of_turn(self):
        self.damage_countdown -= 1
        if self.damage_countdown <= 0 and not self.inflicted_upon.is_fainted():
            self.activate(EffectTypes.END_OF_TURN)
            self.damage_countdown = self.max_damage_countdown

    def activate(self, effect, **kwargs):
        if effect == EffectTypes.END_OF_TURN:
            self.game.display_message(f"{self.inflicted_upon.name} is hurt by its burn!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
        elif effect == EffectTypes.ATTACK_MODIFICATION:
            return kwargs["stat"] // 2

class FreezeEffect(Effect):
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        self.damage = 1/16 # decimal representing portion of max hp
        self.damage_countdown = 300
        self.max_damage_countdown = 300
        self.effect_types = [
            EffectTypes.END_OF_TURN,
            EffectTypes.SPECIAL_ATTACK_MODIFICATION,
            EffectTypes.NON_VOLATILE
        ]
        super().__init__(inflicted_by, inflicted_upon, lifetime=1800, status_icon="freeze", **kwargs)
        
    def get_effect_value(self):
        return 900

    def infliction(self):
        if pokemon_types["Ice"] in self.inflicted_upon.types:
            success = False
        else:
            success = self.inflicted_upon.inflict_status(self)
        if success:
            self.display_inflicted_message()
        return success

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} was frozen!", self.text_size, [0, 0, 0])

    def end_of_turn(self):
        self.damage_countdown -= 1
        if self.damage_countdown <= 0 and not self.inflicted_upon.is_fainted():
            self.activate(EffectTypes.END_OF_TURN)
            self.damage_countdown = self.max_damage_countdown

    def activate(self, effect, **kwargs):
        if effect == EffectTypes.END_OF_TURN:
            self.game.display_message(f"{self.inflicted_upon.name} is hurt by its frostbite!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
        elif effect == EffectTypes.SPECIAL_ATTACK_MODIFICATION:
            return kwargs["stat"] // 2

class ConfusionEffect(Effect):
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        self.confusion_chance = 1/3
        self.effect_types = [
            EffectTypes.BEFORE_ATTACK,
            EffectTypes.NON_VOLATILE
        ]
        super().__init__(inflicted_by, inflicted_upon, lifetime=1800, status_icon="confused", **kwargs)
        

    def get_effect_value(self):
        return 900

    def infliction(self):
        success = False
        if len([effect for effect in self.inflicted_upon.effects if type(effect) is type(self)]) == 0:
            success = self.inflicted_upon.inflict_status(self)
        if success:
            self.display_inflicted_message()
        return success

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} became confused!", self.text_size, [0, 0, 0])

    def activate(self, effect, **kwargs):
        if effect == EffectTypes.BEFORE_ATTACK:
            self.game.display_message(f"{self.inflicted_upon.name} is confused!", self.text_size, [0, 0, 0])
            if random.random() <= self.confusion_chance:
                self.game.display_message(f"It hurt itself in confusion!", self.text_size, [0, 0, 0])
                damage, crit = damage_formula(unobtainable_moves["confusion damage"], self.inflicted_upon, self.inflicted_upon, ignore_attack_modifiers=True, ignore_defense_modifiers=True)
                self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
                return True
            else:
                return False


class MustRechargeEffect(Effect):
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        if "lifetime" not in kwargs:
            super().__init__(inflicted_by, inflicted_upon, **kwargs, lifetime=300, status_icon="locked move")
        else:
            super().__init__(inflicted_by, inflicted_upon, **kwargs, status_icon="locked move")
        self.effect_types = [EffectTypes.MOVE_LOCK]

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} must recharge!", self.text_size, [0, 0, 0])

    def get_effect_value(self):
        # having the recharge status decrease cooldowns for being a negative status feels weird, so this is 0
        return 0

    def activate(self, effect, **kwargs):
        if effect == EffectTypes.MOVE_LOCK:
            return True

class ParalysisEffect(Effect):
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        self.damage = 1/16 # decimal representing portion of max hp
        self.effect_types = [
            EffectTypes.AFTER_ATTACK,
            EffectTypes.SPEED_MODIFICATION,
            EffectTypes.MOVE_SPEED_MODIFICATION,
            EffectTypes.NON_VOLATILE
        ]
        super().__init__(inflicted_by, inflicted_upon, lifetime=1800, status_icon="paralysis", **kwargs)
        

    def get_effect_value(self):
        return 900

    def infliction(self):
        if (pokemon_types["Electric"] in self.inflicted_upon.types) or (pokemon_types in self.inflicted_upon.types and type(self.source) == Move and self.source.type == pokemon_types["Electric"]):
            success = False
        else:
            success = self.inflicted_upon.inflict_status(self)
        if success:
            self.display_inflicted_message()
        return success

    def display_inflicted_message(self):
        self.game.display_message(f"{self.inflicted_upon.name} was paralyzed!", self.text_size, [0, 0, 0])

    def activate(self, effect, **kwargs):
        if effect == EffectTypes.AFTER_ATTACK:
            self.game.display_message(f"{self.inflicted_upon.name} is hurt by its paralysis!", self.text_size, [0, 0, 0])
            damage = self.inflicted_upon.max_hp * self.damage
            damage = min(damage, self.inflicted_upon.hp)
            self.inflicted_upon.do_damage(self.inflicted_by, damage, silent=True)
        elif effect == EffectTypes.SPEED_MODIFICATION:
            return kwargs["stat"] // 2
        elif effect == EffectTypes.MOVE_SPEED_MODIFICATION:
            return kwargs["stat"] // 2

class StatStageEffect(Effect):
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        self.stage = kwargs["stage"]
        if self.stage < 1:
            self.status_icon = "stat drop"
        else:
            self.status_icon = "stat boost"
        self.stat = kwargs["stat"]
        self.effect_types = [
            STAT_EFFECTS[self.stat]["stage"]
            ]
        super().__init__(inflicted_by, inflicted_upon, **kwargs)
        

    def get_effect_value(self):
        modifier = stage_to_modifier(self.stage)
        if modifier < 1:
            return (0.5/modifier) * self.max_lifetime
        else:
            return (modifier/2) * self.max_lifetime

    def display_inflicted_message(self):
        if self.stage < 0:
            boost_descriptor = "fell"
            if self.stage == -2:
                boost_descriptor += " harshly"
            elif self.stage <= -3:
                boost_descriptor += "severely"
        else:
            boost_descriptor = "rose"
            if self.stage == 2:
                boost_descriptor += " sharply"
            elif self.stage >= 3:
                boost_descriptor += "drastically"

        self.game.display_message(f"{self.inflicted_upon.name}'s {STAT_NAMES[self.stat].lower()} {boost_descriptor}!", self.text_size, [0, 0, 0])

    def activate(self, effect, **kwargs):
        if effect in self.effect_types:
            return self.stage

class MoveSpeedModificationEffect(Effect):
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        self.modifier = kwargs["modifier"]
        if self.modifier < 1:
            self.status_icon = "stat drop"
        else:
            self.status_icon = "stat boost"
        self.effect_types = [
            EffectTypes.MOVE_SPEED_MODIFICATION
            ]
        super().__init__(inflicted_by, inflicted_upon, **kwargs)
        

    def get_effect_value(self):
        if self.modifier < 1:
            return (0.5/self.modifier) * self.max_lifetime
        else:
            return (self.modifier/2) * self.max_lifetime

    def display_inflicted_message(self):
        if self.modifier < 1:
            boost_descriptor = "slowed"
        else:
            boost_descriptor = "hastened"

        self.game.display_message(f"{self.inflicted_upon.name} was {boost_descriptor}!", self.text_size, [0, 0, 0])

    def activate(self, effect, **kwargs):
        if effect in self.effect_types:
            return self.modifier * kwargs["stat"]

# reduces all cooldowns by a flat amount, then wears off
class CooldownReductionEffect(Effect):
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        if "reduction_amount" in kwargs:
            self.reduction_amount = kwargs["reduction_amount"]
        else:
            self.reduction_amount = kwargs["reduction_amount"]
        self.effect_types = [
            EffectTypes.COOLDOWN_REDUCTION
        ]
        super().__init__(inflicted_by, inflicted_upon, lifetime=1, **kwargs)
        
    def get_effect_value(self):
        return -1 * self.reduction_amount

    def infliction(self):
        self.inflicted_upon.tick_cooldowns(self.reduction_amount)

# locks all moves except for the affected move.
# the affected move gets 2x power. this power is double every time the move is used.
# after 5 uses, the effect wears off
class RolloutEffect(Effect):
    def __init__(self, inflicted_by, inflicted_upon, **kwargs):
        if "move_name" in kwargs:
            self.affected_move = kwargs["move_name"]
        else:
            self.affected_move = ""
        self.modifier = 2
        self.effect_types = [
            EffectTypes.ATTACKER_BASE_POWER_MODIFICATION,
            EffectTypes.MOVE_LOCK
        ]
        super().__init__(inflicted_by, inflicted_upon, status_icon="locked move", **kwargs)

    def get_effect_value(self):
        return -180

    def infliction(self):
        success = False
        similar_effects = [effect for effect in self.inflicted_upon.effects if type(effect) is type(self)]
        if len(similar_effects) == 0:
            success = self.inflicted_upon.inflict_status(self)
        else:
            similar_effects[0].modifier *= 2 
        if success:
            self.display_inflicted_message()
        return success

    def update(self):
        if self.modifier > 16:
            self.lifetime = 0
        super().update()

    def activate(self, effect, **kwargs):
        if effect == EffectTypes.MOVE_LOCK:
            move_id = kwargs["move_id"]
            if self.inflicted_upon.moves[move_id].name != self.affected_move:
                return True
            else:
                return False
        elif effect == EffectTypes.ATTACKER_BASE_POWER_MODIFICATION:
            move = kwargs["move"]
            if move.name == self.affected_move:
                return self.modifier
            else:
                return 1

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
        # moves start on partial cooldown, but not less than 3 seconds
        # for i in range(len(self.moves)):
        #     self.on_cooldown(i)
        #     self.cooldowns[i] /= 2
        #     if self.cooldowns[i] > 0 and self.cooldowns[i] < 180:
        #         self.cooldowns[i] = 180
        self.types = types
        # speed is pixels/frame
        self.current_speed = 0
        self.direction = random.uniform(0, 360)
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
        ui_x = honse_data.BASE_WIDTH * (self.teammate_id * 3) / 16
        ui_y = honse_data.BASE_HEIGHT - (
            (honse_data.BASE_HEIGHT / 8) * (2 - self.team)
        )
        self.ui_element = honse_data.UIElement(ui_x, ui_y, self)
        self.hit_sound_to_play = None
        self.play_fainted_sound = False
        self.battle_stats = {
            "damage dealt": 0,
            "damage taken": 0,
            "healing given": 0,
            "healing received": 0,
            "kos": 0,
            "fainted": False,
            "time alive": 0,
            "moves used": 0}
        self.spawn_in()

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

    def get_non_volatile_status(self):
        if self.has_non_volatile_status:
            try:
                return [effect for effect in self.effects if EffectTypes.NON_VOLATILE in effect.effect_types][0]
            except IndexError:
                self.has_non_volatile_status = False

    def on_cooldown(self, move_id):
        try:
            self.cooldowns[move_id] = self.moves[move_id].cooldown
        except IndexError:
            pass

    def is_move_locked(self, move_id: int):
        try:
            for effect in self.effects:
                if EffectTypes.MOVE_LOCK in effect.effect_types:
                    return effect.activate(EffectTypes.MOVE_LOCK, move_id=move_id)
        except IndexError:
            return False

    def tick_cooldowns(self, amount=1):
        for i, cooldown in enumerate(self.cooldowns):
            if cooldown > 0 and not self.is_move_locked(i):
                self.cooldowns[i] -= amount
            elif cooldown < 0:
                self.cooldowns[i] = 0

    def get_type_matchup(self, pkmn_type: PokemonType):
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

    def get_modified_stat(self, stat, ignore_modifications=False):
        override = STAT_EFFECTS[stat]["override"]
        modification = STAT_EFFECTS[stat]["stage"]
        base_stat = self.apply_other_modifiers(override, self.base_stats[stat])
        ev = self.evs[stat]; iv = self.ivs[stat]; nature = self.nature[stat]
        unmodified_stat = other_stat_formula(base_stat, self.level, iv, ev, nature)
        if ignore_modifications:
            return max(1, int(unmodified_stat))
        modified_stat = self.apply_stat_stages(modification, unmodified_stat)
        modified_stat = self.apply_other_modifiers(modification, modified_stat)
        return max(1, int(modified_stat))

    def apply_stat_stages(self, effect_type, stat):
        stage = 0
        for effect in self.effects:
            if effect_type in effect.effect_types:
                stage += effect.activate(effect_type)
        stat *= stage_to_modifier(stage)
        return max(1, int(stat))

    def apply_other_modifiers(self, effect_type, stat):
        for effect in self.effects:
            if effect_type in effect.effect_types:
                stat = effect.activate(effect_type, stat=stat)
        return max(1, int(stat))

    def get_max_hp(self):
        ev = self.evs["HP"]; iv = self.ivs["HP"]
        return hp_formula(self.base_stats["HP"], self.level, iv, ev)

    def get_attack(self, ignore_modifications=False):
        return self.get_modified_stat("ATK", ignore_modifications)

    def get_defense(self, ignore_modifications=False):
        return self.get_modified_stat("DEF", ignore_modifications)

    def get_special_attack(self, ignore_modifications=False):
        return self.get_modified_stat("SPA", ignore_modifications)

    def get_special_defense(self, ignore_modifications=False):
        return self.get_modified_stat("SPD", ignore_modifications)

    def get_speed(self, ignore_modifications=False):
        return self.get_modified_stat("SPE", ignore_modifications)

    def get_move_speed(self):
        base_stat = self.apply_other_modifiers(EffectTypes.BASE_SPEED_OVERRIDE, self.base_stats["SPE"])
        speed = speed_formula(base_stat)
        return max(1, self.apply_other_modifiers(EffectTypes.MOVE_SPEED_MODIFICATION, speed))

    def get_acceleration(self):
        return self.apply_stat_stages(
            EffectTypes.ACCELERATION_MODIFICATION, self.acceleration
        )

    def get_drag(self):
        return self.apply_stat_stages(EffectTypes.DRAG_MODIFICATION, self.drag)

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
        if not self.is_fainted():
            for i, move in enumerate(self.moves):
                if self.cooldowns[i] == 0 and not self.is_move_locked(i):
                    if move.is_valid_target(self.same_team(target)) == False:
                        continue
                    can_move = True
                    for effect in self.effects:
                        if EffectTypes.BEFORE_ATTACK in effect.effect_types:
                            activated = effect.activate(EffectTypes.BEFORE_ATTACK)
                            if activated:
                                can_move = False
                    if can_move:
                        self.game.display_message(f"{self.name} used {move.name}!", 24, [0, 0, 0])
                        success = move.on_use(self, target=target)
                        for effect in self.effects:
                            if EffectTypes.AFTER_ATTACK in effect.effect_types:
                                return effect.activate(EffectTypes.AFTER_ATTACK)
                        if not success:
                            self.game.display_message("But it failed!", self.text_size, [0,0,0])
                        else:
                            self.battle_stats["moves used"] += 1
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
                print(self.effects)

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
            self.is_intangible() or self.is_invulnerabile()
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

    def do_damage(self, source, damage, **kwargs):
        if self.is_fainted() or damage==0:
            return 0
        if damage > self.hp:
            damage = self.hp
        self.hp -= damage
        self.battle_stats["damage taken"] += damage
        if not self.same_team(source):
            source.battle_stats["damage dealt"] += damage
        if "silent" not in kwargs:
            percent = int(max(1, (100 * damage) // self.max_hp))
            self.game.display_message(f"{self.name} took {percent} damage.", 16, [0, 0, 0])
        if self.is_fainted():
            self.battle_stats["fainted"] = True
            if not self.same_team(source):
                source.battle_stats["kos"] += 1
            self.play_fainted_sound = True
            self.game.display_message(f"{self.name} fainted!", 24, [127, 0, 0])
        return damage


    def do_healing(self, source, healing, **kwargs):
        if self.is_fainted() or healing==0:
            return 0
        max_hp = self.max_hp
        if healing + self.hp > max_hp:
            healing = max_hp - self.hp
        self.hp += healing
        self.battle_stats["healing received"] += healing
        if self.same_team(source):
            source.battle_stats["healing given"] += healing
        if "silent" not in kwargs:
            percent = int(max(1, (100 * healing) // self.max_hp))
            self.game.display_message(f"{self.name} recovered {percent} HP.", 16, [0, 0, 0])
        return healing

    def inflict_status(self, status):
        if self.is_fainted():
            return False
        if EffectTypes.NON_VOLATILE in status.effect_types and self.has_non_volatile_status:
            return False
        self.effects.append(status)
        if EffectTypes.NON_VOLATILE not in status.effect_types:
            self.ui_element.queue_status(status)
        else:
            self.has_non_volatile_status = True
        return True

    def remove_status(self, status):
        self.effects.remove(status)
        if EffectTypes.NON_VOLATILE not in status.effect_types:
            self.ui_element.unqueue_status(status)
        else:
            self.has_non_volatile_status = False

    def end_of_turn(self):
        for effect in self.effects:
            effect.end_of_turn()
            effect.update()

    def crit_calc(self, move, target):
        crit_stage = move.crit_stage
        damage_mod = 1.5
        # if the crit stage is < 0 at any point in the process, return 1 (normal damage)
        if crit_stage < 0:
            return 1
        for effect in self.effects:
            if EffectTypes.CRIT_STAGE in effect.effect_types:
                crit_stage = effect.activate(EffectTypes.CRIT_STAGE, stat=crit_stage)
        if crit_stage < 0:
            return 1
        for effect in target.effects:
            if EffectTypes.CRIT_RESIST in effect.effect_types:
                crit_stage = effect.activate(EffectTypes.CRIT_RESIST, stat=crit_stage)
        if crit_stage < 0:
            return 1
        for effect in target.effects:
            if EffectTypes.CRIT_DAMAGE in effect.effect_types:
                damage_mod = effect.activate(EffectTypes.CRIT_DAMAGE, stat=damage_mod)
        if crit_stage >= 3:
            return damage_mod
        elif crit_stage == 2:
            return damage_mod if random.random() <= 0.5 else 1
        elif crit_stage == 1:
            return damage_mod if random.random() <= 0.125 else 1
        else:
            return damage_mod if random.random() <= 1/24 else 1


class MoveTarget(enum.Enum):
    NORMAL = 0,
    USER = 1

class Move:
    def __init__(self,
                 name: str,
                 pkmn_type: PokemonType,
                 category: MoveCategories,
                 **kwargs):
        self.name = name
        self.type = pkmn_type
        self.category = category
        if not hasattr(self, "target"):
            if "target" in kwargs:
                self.target = kwargs["target"]
            else:
                self.target = MoveTarget.USER
        if "cooldown" in kwargs:
            self.cooldown = kwargs["cooldown"]
        else:
            self.cooldown = 60
        if "move_effects" in kwargs:
            self.move_effects = kwargs["move_effects"]
        else:
            self.move_effects = []
        if not hasattr(self, "animation"):
            if "animation" in kwargs:
                self.animation = kwargs["animation"]
            else:
                self.animation = None
        if not hasattr(self, "power"):
            self.power = 0
        if "animation_length" in kwargs:
            self.animation_length = kwargs["animation_length"]
        else:
            self.animation_length = None
        if not hasattr(self, "sound"):
            if "sound" in kwargs:
                self.sound = kwargs["sound"]
            else:
                self.sound = None
        if "targets_self" in kwargs:
            self.targets_self = kwargs["targets_self"]
        else:
            self.targets_self = True
        self.current_bp = self.power
        if "cooldown" not in kwargs:
            self.get_default_cooldown(**kwargs)

    def get_default_cooldown(self, **kwargs):
        # cooldown scales on power plus a flat 20 because i want high power moves to have better dps
        cooldown = 60 * (self.power + 20) / 10
        modifier = 1
        if "spread_radius" in kwargs:
            modifier *= 1.5
        if "accuracy" in kwargs:
            modifier *= 100 / kwargs["accuracy"]
        if self.crit_stage > 0:
            modifier *= 1.25
        if self.drain > 0:
            modifier *= 1.25
        if self.recoil > 0:
            modifier *= 0.75
        if hasattr(self, "secondaries"):
            secondaries = self.secondaries + self.move_effects
        else:
            secondaries = [] + self.move_effects
        for item in secondaries:
            effect = item["effect"]
            affects_user = item["affects user"]
            try:
                chance = item["chance"]
            except KeyError:
                chance = 100
            kwargs = item["kwargs"]
            effect_value = effect(None, None, get_effect_value=True, **kwargs)
            effect_value = effect_value.get_effect_value()
            effect_value *= chance / 100
            # moves that do something bad to the user or something good to the opponent get a slight cooldown reduction
            if affects_user and effect_value > 0:
                cooldown -= effect_value * 0.15
            elif not affects_user and effect_value < 0:
                cooldown += effect_value * 0.15
            else:
                cooldown += effect_value
        cooldown *= modifier
        cooldown *= self.type.cooldown_modifier
        self.cooldown = max(int(cooldown), 60)

    def play_effects(self, user: Character, x: float, y: float):
        if self.sound is not None:
            user.game.play_sound(self.sound)
        if self.animation is not None:
            if self.animation_length is not None:
                self.animation(user.game, x, y, self.animation_length)
            else:
                self.animation(user.game, x, y)

    def apply_move_effects(self, user, target):
        for effect in self.move_effects:
            if effect["affects user"]:
                effect["effect"](user, user, **effect["kwargs"], source=self)
            else:
                effect["effect"](user, target, **effect["kwargs"], source=self)

    def on_use(self, user: Character, **kwargs):
        if self.target == MoveTarget.NORMAL:
            target = kwargs["target"]
        elif self.target == MoveTarget.USER:
            target = user
        self.play_effects(user, user.position[0], user.position[1])
        self.apply_move_effects(user, target)
        return False

    def is_valid_target(self, teammates: bool):
        if teammates:
            return self.target in [MoveTarget.USER]
        else:
            return self.target in [MoveTarget.USER, MoveTarget.NORMAL]

# secondaries and move effects (move effects dont have chance since theyre guaranteed)
# {effect: effect, chance: %, affects user: bool, kwargs: dict}
class BasicAttack(Move):
    def __init__(
        self,
        name: str,
        pkmn_type: PokemonType,
        category: MoveCategories,
        power: int,
        **kwargs
    ):
        if "target" in kwargs:
            self.target = kwargs["target"]
        else:
            self.target = MoveTarget.NORMAL
        if "secondaries" in kwargs:
            self.secondaries = kwargs["secondaries"]
        else:
            self.secondaries = []
        # -1 crit stage: never crit
        # 3 crit stage: always crit
        if "crit_stage" in kwargs:
            self.crit_stage = kwargs["crit_stage"]
        else:
            self.crit_stage = 0
        if "drain" in kwargs:
            self.drain = kwargs["drain"]
        else:
            self.drain = 0
        if "recoil" in kwargs:
            self.recoil = kwargs["recoil"]
        else:
            self.recoil = 0
        if "invulnerability" in kwargs:
            self.invulnerability = kwargs["invulnerability"]
        else:
            self.invulnerability = 0
        if "knockback_scaling" in kwargs:
            self.knockback_scaling = kwargs["knockback_scaling"]
        else:
            self.knockback_scaling = 1
        if "spread_radius" in kwargs:
            self.spread_radius = kwargs["spread_radius"]
        else:
            self.spread_radius = None
        if "damage_formula_kwargs" in kwargs:
            self.damage_formula_kwargs = kwargs["damage_formula_kwargs"]
        else:
            self.damage_formula_kwargs = {}
        self.power = power
        super().__init__(name, pkmn_type, category, **kwargs)
        if "hitstop" in kwargs:
            self.hitstop = kwargs["hitstop"]
        else:
            self.hitstop = self.type.default_hitstop
        if "base_knockback" in kwargs:
            self.base_knockback = kwargs["base_knockback"]
        else:
            self.base_knockback = self.type.base_knockback * self.power / 50
        if "animation" not in kwargs:
            self.animation = self.type.default_animation
        if "sound" not in kwargs:
            self.sound = self.type.sound

    def knockback_modifier(self, current_hp: int, damage: int):
        # knockback is multiplied by knockback scaling
        # knockback scaling is equal to 1+((knockback_scaling * damage)/current_hp)
        # damage cannot exceed current HP
        # this is also used for hitstop
        knockback_modification = 1 + ((self.knockback_scaling * damage) / max(1,current_hp))
        return knockback_modification

    def apply_secondaries(self, user, target):
        chances = []
        effects = []
        last_cutoff = 0
        for effect in self.secondaries:
            current_cutoff = last_cutoff + effect["chance"]
            last_cutoff = current_cutoff
            chances.append(current_cutoff)
            effects.append({"effect": effect["effect"], "affects user": effect["affects user"], "kwargs": effect["kwargs"]})
        roll = random.randint(1, 100)
        for i, chance in enumerate(chances):
            if roll <= chance:
                if effects[i]["affects user"]:
                    effects[i]["effect"](user, user, **effects[i]["kwargs"], source=self)
                else:
                    effects[i]["effect"](user, target, **effects[i]["kwargs"], source=self)
                break

    def apply_power_modifiers(self, user, target):
        self.current_bp = self.power
        for effect in user.effects:
            if EffectTypes.ATTACKER_BASE_POWER_MODIFICATION in effect.effect_types:
                self.current_bp *= effect.activate(EffectTypes.ATTACKER_BASE_POWER_MODIFICATION, move=self, user=user, target=target)
        for effect in target.effects:
            if EffectTypes.TARGET_BASE_POWER_MODIFICATION in effect.effect_types:
                self.current_bp *= effect.activate(EffectTypes.TARGET_BASE_POWER_MODIFICATION, move=self, user=user, target=target)
        self.current_bp = max(1, self.current_bp)

    def on_use(self, user: Character, **kwargs):
        self.current_bp = self.power
        if self.target == MoveTarget.NORMAL:
            target = kwargs["target"]
        elif self.target == MoveTarget.USER:
            target = user
        self.apply_power_modifiers(user, target)
        # damage calc
        damage, crit = damage_formula(self, user, target)
        # display messages and vfx
        self.play_effects(user, target.position[0], target.position[1])
        if crit:
            if self.spread_radius is not None:
                user.game.display_message(f"A critical hit on {target.name}!", 16, [0, 0, 0])
            else:
                user.game.display_message("A critical hit!", 16, [0, 0, 0])
        effectiveness_quote, effectiveness_sound = get_type_effectiveness_stuff(self, target)
        if effectiveness_quote:
            user.game.display_message(effectiveness_quote, 16, [0, 0, 0])
        target.hit_sound_to_play = effectiveness_sound
        # do damage
        damage = target.do_damage(user, damage, **self.damage_formula_kwargs)
        # knockback and hitstop
        knockback_mod = self.knockback_modifier(target.hp, damage)
        knockback = self.base_knockback * knockback_mod
        target.hitstop = self.hitstop
        target.current_speed += knockback
        # drain and recoil
        if self.drain > 0:
            healing = min(1, damage * self.drain)
            user.game.display_message(f"{target.name} had its energy drained!", 16, [0, 0, 0])
            user.do_healing(user, healing, silent=True)
        if self.recoil > 0:
            recoil = min(1, damage * self.recoil)
            user.game.display_message(f"{user.name} is damaged by recoil!", 16, [0, 0, 0])
            user.do_damage(user, recoil, silent=True)
        # secondaries and other effects
        self.apply_move_effects(user, target)
        self.apply_secondaries(user, target)
        self.current_bp = self.power
        return True

unobtainable_moves = {
    "confusion damage": BasicAttack(
        "confusion damage",
        pokemon_types["Typeless"],
        MoveCategories.PHYSICAL,
        40,
        crit_stage=-1)
    }

moves = {
    "Tackle": BasicAttack(
        "Tackle",
        pokemon_types["Normal"],
        MoveCategories.PHYSICAL,
        40),
    "Boomburst": BasicAttack(
        "Boomburst",
        pokemon_types["Normal"],
        MoveCategories.SPECIAL,
        140),
    "Body Slam": BasicAttack(
        "Body Slam",
        pokemon_types["Normal"],
        MoveCategories.PHYSICAL,
        85,
        secondaries=[{
            "effect": ParalysisEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 30}
        ]),
    "Take Down": BasicAttack(
        "Take Down",
        pokemon_types["Normal"],
        MoveCategories.PHYSICAL,
        90,
        accuracy=85,
        recoil=0.25),
    "Giga Impact": BasicAttack(
        "Giga Impact",
        pokemon_types["Normal"],
        MoveCategories.PHYSICAL,
        150,
        accuracy=90,
        move_effects=[{
            "effect": MustRechargeEffect,
            "affects user": True,
            "kwargs": {}}
        ]),
    "Hyper Beam": BasicAttack(
        "Hyper Beam",
        pokemon_types["Normal"],
        MoveCategories.SPECIAL,
        150,
        accuracy=90,
        move_effects=[{
            "effect": MustRechargeEffect,
            "affects user": True,
            "kwargs": {}}
        ]),
    "Ember": BasicAttack(
        "Ember",
        pokemon_types["Fire"],
        MoveCategories.SPECIAL,
        40,
        secondaries=[{
            "effect": BurnEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 10}
        ]),
    "Flamethrower": BasicAttack(
        "Flamethrower",
        pokemon_types["Fire"],
        MoveCategories.SPECIAL,
        90,
        secondaries=[{
            "effect": BurnEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 10}
        ]),
    "Flame Wheel": BasicAttack(
        "Flame Wheel",
        pokemon_types["Fire"],
        MoveCategories.PHYSICAL,
        85,
        secondaries=[{
            "effect": BurnEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 10}
        ]),
    "Fire Blast": BasicAttack(
        "Fire Blast",
        pokemon_types["Fire"],
        MoveCategories.SPECIAL,
        110,
        accuracy=85,
        secondaries=[{
            "effect": BurnEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 10}
        ]),
    "Infero": BasicAttack(
        "Inferno",
        pokemon_types["Fire"],
        MoveCategories.SPECIAL,
        100,
        accuracy=50,
        secondaries=[{
            "effect": BurnEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 100}
        ]),
    "Blast Burn": BasicAttack(
        "Hyper Beam",
        pokemon_types["Fire"],
        MoveCategories.SPECIAL,
        150,
        accuracy=90,
        move_effects=[{
            "effect": MustRechargeEffect,
            "affects user": True,
            "kwargs": {}}
        ]),
    "Water Gun": BasicAttack(
        "Water Gun",
        pokemon_types["Water"],
        MoveCategories.SPECIAL,
        40),
    "Scald": BasicAttack(
        "Scald",
        pokemon_types["Water"],
        MoveCategories.SPECIAL,
        80,
        secondaries=[{
            "effect": BurnEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 30}
        ]),
    "Hydro Pump": BasicAttack(
        "Hydro Pump",
        pokemon_types["Water"],
        MoveCategories.SPECIAL,
        110,
        accuracy=80),
    "Aqua Tail": BasicAttack(
        "Aqua Tail",
        pokemon_types["Water"],
        MoveCategories.PHYSICAL,
        90,
        accuracy=90),
    "Hydro Cannon": BasicAttack(
        "Hydro Cannon",
        pokemon_types["Water"],
        MoveCategories.SPECIAL,
        150,
        accuracy=90,
        move_effects=[{
            "effect": MustRechargeEffect,
            "affects user": True,
            "kwargs": {}}
        ]),
    "Water Pulse": BasicAttack(
        "Water Pulse",
        pokemon_types["Water"],
        MoveCategories.SPECIAL,
        60,
        secondaries=[{
            "effect": ConfusionEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 20}
        ]),
    "Vine Whip": BasicAttack(
        "Vine Whip",
        pokemon_types["Grass"],
        MoveCategories.PHYSICAL,
        45),
    "Giga Drain": BasicAttack(
        "Giga Drain",
        pokemon_types["Grass"],
        MoveCategories.SPECIAL,
        75,
        drain=0.5),
    "Biddy Bud": BasicAttack(
        "Biddy Bud",
        pokemon_types["Grass"],
        MoveCategories.SPECIAL,
        60,
        secondaries=[{
            "effect": LeechSeedEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 100}
        ]),
    "Frenzy Plant": BasicAttack(
        "Frenzy Plant",
        pokemon_types["Grass"],
        MoveCategories.SPECIAL,
        150,
        accuracy=90,
        move_effects=[{
            "effect": MustRechargeEffect,
            "affects user": True,
            "kwargs": {}}
        ]),
    "Razor Leaf": BasicAttack(
        "Razor Leaf",
        pokemon_types["Grass"],
        MoveCategories.PHYSICAL,
        55,
        accuracy=95,
        crit_stage=1),
    "Power Whip": BasicAttack(
        "Power Whip",
        pokemon_types["Grass"],
        MoveCategories.PHYSICAL,
        120,
        accuracy=85),
    "Nuzzle": BasicAttack(
        "Nuzzle",
        pokemon_types["Electric"],
        MoveCategories.PHYSICAL,
        20,
        secondaries=[{
            "effect": ParalysisEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 100}
        ]),
    "Spark": BasicAttack(
        "Spark",
        pokemon_types["Electric"],
        MoveCategories.PHYSICAL,
        65,
        secondaries=[{
            "effect": ParalysisEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 30}
        ]),
    "Zap Cannon": BasicAttack(
        "Zap Cannon",
        pokemon_types["Electric"],
        MoveCategories.SPECIAL,
        100,
        accuracy=50,
        secondaries=[{
            "effect": ParalysisEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 100}
        ]),
    "Thunderbolt": BasicAttack(
        "Thunderbolt",
        pokemon_types["Electric"],
        MoveCategories.SPECIAL,
        90,
        secondaries=[{
            "effect": ParalysisEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 10}
        ]),
    "Thunder": BasicAttack(
        "Thunder",
        pokemon_types["Electric"],
        MoveCategories.SPECIAL,
        110,
        accuracy=70,
        secondaries=[{
            "effect": ParalysisEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 30}
        ]),
    "Volt Tackle": BasicAttack(
        "Volt Tackle",
        pokemon_types["Electric"],
        MoveCategories.PHYSICAL,
        120,
        recoil=0.33,
        secondaries=[{
            "effect": ParalysisEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 10}
        ]),
    "Aurora Beam": BasicAttack(
        "Aurora Beam",
        pokemon_types["Ice"],
        MoveCategories.SPECIAL,
        65,
        secondaries=[{
            "effect": StatStageEffect,
            "affects user": False,
            "kwargs": {"stage": -1, "stat": "ATK", "lifetime": 1800},
            "chance": 10}
        ]),
    "Ice Beam": BasicAttack(
        "Ice Beam",
        pokemon_types["Ice"],
        MoveCategories.SPECIAL,
        90,
        secondaries=[{
            "effect": FreezeEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 10}
        ]),
    "Ice Hammer": BasicAttack(
        "Ice Hammer",
        pokemon_types["Ice"],
        MoveCategories.PHYSICAL,
        100,
        accuracy=90,
        move_effects=[{
            "effect": StatStageEffect,
            "affects user": True,
            "kwargs": {"stage": -1, "stat": "SPE", "lifetime": 900}},
           {"effect": MoveSpeedModificationEffect,
            "affects user": True,
            "kwargs": {"modifier": 2/3, "lifetime": 900}}]
        ),
    "Ice Shard": BasicAttack(
        "Ice Shard",
        pokemon_types["Ice"],
        MoveCategories.PHYSICAL,
        40,
        move_effects=[{
            "effect": CooldownReductionEffect,
            "affects user": True,
            "kwargs": {"reduction_amount": 180}}]
        ),
    "Ice Ball": BasicAttack(
        "Ice Ball",
        pokemon_types["Ice"],
        MoveCategories.PHYSICAL,
        30,
        accuracy=90,
        move_effects=[{
            "effect": RolloutEffect,
            "affects user": True,
            "kwargs": {"move_name": "Ice Ball"}}]
        ),
    "Ice Punch": BasicAttack(
        "Ice Punch",
        pokemon_types["Ice"],
        MoveCategories.PHYSICAL,
        75,
        secondaries=[{
            "effect": FreezeEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 10}
        ]),
    "Focus Blast": BasicAttack(
        "Focus Blast",
        pokemon_types["Fighting"],
        MoveCategories.SPECIAL,
        120,
        accuracy=70,
        secondaries=[{
            "effect": StatStageEffect,
            "affects user": False,
            "kwargs": {"stage": -1, "stat": "SPD", "lifetime": 1800},
            "chance": 10}
        ]),
    "Dynamic Punch": BasicAttack(
        "Dynamic Punch",
        pokemon_types["Fighting"],
        MoveCategories.PHYSICAL,
        100,
        accuracy=50,
        secondaries=[{
            "effect": ConfusionEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 100}
        ]),
    "Cross Chop": BasicAttack(
        "Cross Chop",
        pokemon_types["Fighting"],
        MoveCategories.PHYSICAL,
        100,
        accuracy=80,
        crit_stage=1),
    "Close Combat": BasicAttack(
        "Close Combat",
        pokemon_types["Fighting"],
        MoveCategories.PHYSICAL,
        120,
        move_effects=[{
            "effect": StatStageEffect,
            "affects user": True,
            "kwargs": {"stage": -1, "stat": "DEF", "lifetime": 1200}},
           {"effect": StatStageEffect,
            "affects user": True,
            "kwargs": {"stage": -1, "stat": "SPD", "lifetime": 1200}}]
        ),
    "Superpower": BasicAttack(
        "Superpower",
        pokemon_types["Fighting"],
        MoveCategories.PHYSICAL,
        120,
        move_effects=[{
            "effect": StatStageEffect,
            "affects user": True,
            "kwargs": {"stage": -1, "stat": "ATK", "lifetime": 1200}},
           {"effect": StatStageEffect,
            "affects user": True,
            "kwargs": {"stage": -1, "stat": "DEF", "lifetime": 1200}}]
        ),
    "Submission": BasicAttack(
        "Submission",
        pokemon_types["Fighting"],
        MoveCategories.PHYSICAL,
        100,
        recoil=0.25
        ),
    "Barrage": BasicAttack(
        "Barrage",
        pokemon_types["Psychic"],
        MoveCategories.PHYSICAL,
        25
    ),
    "Confusion": BasicAttack(
        "Confusion",
        pokemon_types["Psychic"],
        MoveCategories.SPECIAL,
        50,
        secondaries=[{
            "effect": ConfusionEffect,
            "affects user": False,
            "kwargs": {},
            "chance": 10}
        ]),
    "Psychic": BasicAttack(
        "Psychic",
        pokemon_types["Psychic"],
        MoveCategories.SPECIAL,
        90,
        secondaries=[{
            "effect": StatStageEffect,
            "affects user": False,
            "kwargs": {"stage": -1, "stat": "SPD", "lifetime": 1800},
            "chance": 10}
        ]),
    "Lunatic Eyes": BasicAttack(
        "Lunatic Eyes",
        pokemon_types["Psychic"],
        MoveCategories.SPECIAL,
        70,
        secondaries=[{
            "effect": StatStageEffect,
            "affects user": False,
            "kwargs": {"stage": -2, "stat": "ATK", "lifetime": 1200},
            "chance": 100}
        ]),
    "Cosmic Spin": BasicAttack(
        "Cosmic Spin",
        pokemon_types["Psychic"],
        MoveCategories.PHYSICAL,
        70,
        secondaries=[{
            "effect": StatStageEffect,
            "affects user": False,
            "kwargs": {"stage": -2, "stat": "SPA", "lifetime": 1200},
            "chance": 100}
        ]),
    "Psyshock": BasicAttack(
        "Psyshock",
        pokemon_types["Psychic"],
        MoveCategories.SPECIAL,
        80,
        damage_formula_kwargs={"defense_override": "DEF"}),
}
