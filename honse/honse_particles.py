from contextlib import redirect_stderr
import pygame
import random
import math
import numpy as np
import honse_data
import os
from PIL import Image
from dataclasses import dataclass

#may break things
os.chdir(os.path.dirname(os.path.abspath(__file__)))
@dataclass
class ParticleOptions:
    lifetime: int|None = None
    death_function: tuple|None = None
    leave_trail_every_nth_frame: int = -1
    render_on_top: bool = False
    follow_character: ... = None
    follow_x_offset: int = 0
    follow_y_offset: int = 0
    reset_size_each_frame: bool = False
# lots of particle variables can be changed each frame by passing a function instead of a constant
# these functions must take two parameters.
# the first parameter is the frames the particle has been alive
# the first parameter is the frames the particle has been alive
# the second parameter is the the number of frames the particle has been alive / it's maximum lifetime. it will always be in the range of 0 to 1.
# the functions may use one, both, or neither of these parameters

class CircleParticle:
    def __init__(
        self,
        game,
        x: float,
        y: float,
        x_speed: ...,
        y_speed: ...,
        radius: ...,
        growth: ...,
        red: ...,
        green: ...,
        blue: ...,
        alpha: ...,
        options: ParticleOptions
    ):
        lifetime = options.lifetime
        self.death_function = options.death_function
        self.leave_trail_every_nth_frame = options.leave_trail_every_nth_frame
        self.render_on_top = options.render_on_top
        self.game = game
        self.x = x
        self.y = y
        self.radius = radius
        self.red = self.turn_into_function(red)
        self.green = self.turn_into_function(green)
        self.blue = self.turn_into_function(blue)
        self.alpha = self.turn_into_function(alpha)
        self.growth = self.turn_into_function(growth)
        self.x_speed = self.turn_into_function(x_speed)
        self.y_speed = self.turn_into_function(y_speed)
        # these are measured in frames
        self.max_lifetime = lifetime
        self.remaining_lifetime = lifetime
        self.lived_lifetime = 0
        self.color = (255, 255, 255, 255)
        self.follow_character = options.follow_character
        self.follow_x_offset = options.follow_x_offset
        self.follow_y_offset = options.follow_y_offset
        # used for animating while following a character
        self.x_movement_from_speed = 0
        self.y_movement_from_speed = 0
        # if True, radius or height and width will be set to 0 each frame before the growth function is applied
        self.reset_size_each_frame = options.reset_size_each_frame
        # leaves a trail every nth frame. -1 for no trail
        self.dead = True

    def turn_into_function(self, x):
        if type(x) in [int, float]:
            return lambda a, b: x
        else:
            return x

    def get_lifetime_remaining(self):
        if self.max_lifetime is not None:
            return self.remaining_lifetime / self.max_lifetime
        else:
            return 1

    def check_alive(self):
        if self.radius <= 0:
            return False
        elif self.max_lifetime is not None:
            return self.remaining_lifetime > 0
        return True

    def on_death(self):
        self.dead = True
        if self.death_function is not None:
            death_function = self.death_function[0]
            kwargs = self.death_function[1]
            call_death_function = True
            if "recursions_left" in kwargs:
                if kwargs["recursions_left"] <= 0:
                    call_death_function = False
                kwargs["recursions_left"] -= 1
            if call_death_function:
                death_function(self.game, self.x, self.y, **kwargs)

    def spawn_trail_particle(self):
        if self.leave_trail_every_nth_frame != -1 and self.lived_lifetime % self.leave_trail_every_nth_frame == 0:
            options = ParticleOptions(lifetime=self.max_lifetime)
            if type(self) == CircleParticle:
                particle = CircleParticle(
                    self.game,
                    self.x,self.y,
                    0,0,
                    self.radius,
                    self.growth,
                    self.red,
                    self.green,
                    self.blue,
                    self.alpha,
                    options=options)
            elif type(self) == RectParticle:
                particle = RectParticle(
                    self.game,
                    self.x,self.y,
                    0,0,
                    self.width,self.height,
                    self.x_growth,self.y_growth,
                    self.rotation_degrees,
                    self.red,
                    self.green,
                    self.blue,
                    self.alpha,
                    options=options)
            particle.lived_lifetime = self.lived_lifetime
            particle.remaining_lifetime = self.remaining_lifetime
            self.game.particle_spawner.add_particles(particle)

    def update_lifetime(self):
        self.lived_lifetime += 1
        if self.remaining_lifetime is not None:
            self.remaining_lifetime -= 1

    def update(self):
        lifetime_remaining = self.get_lifetime_remaining()
        self.update_size(lifetime_remaining)
        self.update_position(lifetime_remaining)
        self.update_color(lifetime_remaining)
        self.spawn_trail_particle()

    def update_position(self, lifetime_remaining):
        if self.follow_character is None:
            self.x += self.x_speed(self.lived_lifetime, lifetime_remaining)
            self.y += self.y_speed(self.lived_lifetime, lifetime_remaining)
        else:
            self.x_movement_from_speed += self.x_speed(self.lived_lifetime, lifetime_remaining)
            self.y_movement_from_speed += self.y_speed(self.lived_lifetime, lifetime_remaining)
            self.x = self.follow_character.position[0] + self.follow_x_offset + self.x_movement_from_speed
            self.y = self.follow_character.position[1] + self.follow_y_offset + self.y_movement_from_speed

    def update_size(self, lifetime_remaining):
        if self.reset_size_each_frame:
            self.radius = self.growth(self.lived_lifetime, lifetime_remaining)
        else:
            self.radius += self.growth(self.lived_lifetime, lifetime_remaining)

    def update_color(self, lifetime_remaining):
        self.color = (
            self.red(self.lived_lifetime, lifetime_remaining),
            self.green(self.lived_lifetime, lifetime_remaining),
            self.blue(self.lived_lifetime, lifetime_remaining),
            self.alpha(self.lived_lifetime, lifetime_remaining),
        )
    def draw(self):
        if self.radius >= 1:
            self.game.draw_circle(self.x, self.y, self.radius, self.color)


class RectParticle(CircleParticle):
    def __init__(
        self,
        game,
        x: float,
        y: float,
        x_speed: ...,
        y_speed: ...,
        width: ...,
        height: ...,
        x_growth: ...,
        y_growth: ...,
        rotation_degrees: ...,
        red: ...,
        green: ...,
        blue: ...,
        alpha: ...,
        options: ParticleOptions
    ):
        # width and height can be used as a function or you can use x_growth and y_growth to modify width and height
        # i do whatever is easiest for the given effect that i want to display
        self.width = width
        self.height = height
        self.x_growth = self.turn_into_function(x_growth)
        self.y_growth = self.turn_into_function(y_growth)
        self.rotation_degrees = self.turn_into_function(rotation_degrees)
        super().__init__(
            game,
            x,
            y,
            x_speed,
            y_speed,
            None,
            None,
            red,
            green,
            blue,
            alpha,
            options
        )

    def update_size(self, lifetime_remaining):
        if self.reset_size_each_frame:
            self.width = self.x_growth(self.lived_lifetime, lifetime_remaining)
            self.height = self.y_growth(self.lived_lifetime, lifetime_remaining)
        else:
            self.width += self.x_growth(self.lived_lifetime, lifetime_remaining)
            self.height += self.y_growth(self.lived_lifetime, lifetime_remaining)

    def check_alive(self):
        if self.height <= 0 or self.width <= 0:
            return False
        elif self.max_lifetime is not None:
            return self.remaining_lifetime > 0
        return True

    def draw(self):
        if self.width >= 1 and self.height >= 1:
            rotation = self.rotation_degrees(
                self.lived_lifetime, self.get_lifetime_remaining()
            )
            self.game.draw_rectangle(
                self.x, self.y, self.width, self.height, rotation, self.color
            )


class ImageParticle(RectParticle):
    def __init__(
        self,
        game,
        x,
        y,
        x_speed,
        y_speed,
        image_key,
        image_index,
        options: ParticleOptions,
        frame_length = 3
    ):
        super().__init__(
        game,
        x,
        y,
        x_speed,
        y_speed,
        1,
        1,
        0,
        0,
        0,
        255,
        255,
        255,
        255,
        options)
        self.image_key = image_key
        self.image_index = image_index
        self.frame_length = frame_length

    def update_size(self, lifetime_remaining):
        pass

    def update_color(self, lifetime_remaining):
        pass

    def update_sprite(self):
        if self.lived_lifetime > 0 and self.lived_lifetime % self.frame_length == 0 and self.image_index < len(self.game.particle_images[self.image_key])-1:
            self.image_index += 1

    def update(self):
        self.update_sprite()
        super().update()

    def draw(self):
        self.game.draw_image(self.x, self.y,
                             self.game.particle_surfaces[self.image_key][self.image_index],
                             self.game.particle_images[self.image_key][self.image_index])

class PunchParticle(ImageParticle):
    def __init__(self, game, x, y, options: ParticleOptions):
        key = "punch"
        index = 0
        super().__init__(game, x, y, 0, 0, key, index, options)
    
    def update_sprite(self):
        lifetime_remaining = self.get_lifetime_remaining()
        if lifetime_remaining > 0.5:
            self.image_index = 0
        elif lifetime_remaining > 0.375:
            self.image_index = 1
        elif lifetime_remaining > 0.25:
            self.image_index = 2
        elif lifetime_remaining > 0.125:
            self.image_index = 3
        else:
            self.image_index = 4

class RazorLeafParticle(ImageParticle):
    def __init__(self, game, x, y, mirror_mode: bool, options: ParticleOptions):
        key = "razor leaf transparent"
        index = 0
        self.mirror_mode = mirror_mode
        super().__init__(game, x, y, 0, 0, key, index, options)
    
    def update_sprite(self):
        self.image_index = ((self.lived_lifetime + (4 if self.mirror_mode else 0))//4) % 8

    def update_position(self, lifetime_remaining):
        angle = np.radians((540 * (1-lifetime_remaining)) % 360)
        speed = 3 + 6 * (1 + (1-lifetime_remaining))
        self.x += (np.cos(angle) * speed) * (-1 if self.mirror_mode else 1) * 1.5
        self.y += np.sin(angle) * (2 * speed / 3)

class IceParticle(ImageParticle):
    def __init__(self, game, x, y, options: ParticleOptions):
        key = "ice transparent"
        index = 0
        x -= 50
        y -= 60
        super().__init__(game, x, y, 0, 0, key, index, options)

    def update_sprite(self):
        # animation frame: duration in game frames
        # 1-3: 3 frames each
        if self.lived_lifetime <= 8:
            self.image_index = self.lived_lifetime // 3
        # 4: 6 frames
        elif self.lived_lifetime <= 14:
            self.image_index = 3
        # 5: 30 frames
        elif self.lived_lifetime <= 34:
            self.image_index = 4
        # 6: 9 frames
        elif self.lived_lifetime <= 43:
            self.image_index = 5
        # 7: 6 frames
        elif self.lived_lifetime <= 49:
            self.image_index = 6
        # 8: 12 fremes
        elif self.lived_lifetime <= 61:
            self.image_index = 7
        # 9: 9 frames
        elif self.lived_lifetime <= 69:
            self.image_index = 8
        # (still frame 9, but spawn ice shatter particles)
        elif self.lived_lifetime == 70:
            self.image_index = 8
            ice_shatter_animation(self.game, self.x, self.y)
        # 10-11: 2 frames each
        elif self.lived_lifetime <= 72:
            self.image_index = 9
        else:
            self.image_index

class ParticleSpawner:
    def __init__(self, game):
        self.particles = []
        self.game = game

    def emit(self, render_top=False):
        if self.particles:
            for particle in self.particles:
                if particle.render_on_top != render_top:
                    continue
                particle.draw()
                particle.update()
                particle.update_lifetime()

    def add_particles(self, particle):
        if type(particle) is list:
            self.particles += particle
        else:
            self.particles.append(particle)

    def delete_particles(self):
        for particle in self.particles:
            if particle.check_alive() == False:
                self.particles.remove(particle)
                particle.on_death()


def randomize_if_tuple(value):
    if type(value) is tuple:
        return random.randint(value[0], value[1])
    else:
        return value

# kwargs for animation functions
# usually these are unusued
# some functions use recursions_left
# this is used to make sure that particles that use a death function to spawn more particles upon death
# don't cause infinite recursion issues.
# each time the death function is called, recursions_left is decreased
# at 0, it stops calling the death function
# in some cases, other parameters will need to be passed to an animation function
# for example, character_to_follow can be used to specify that the animation should follow a character around
# when assigning a death function, please pay attention to the kwargs that you will need to pass to the function
def small_impact_animation(game, x, y, **kwargs):
    options = ParticleOptions(
        lifetime=10,
        render_on_top=True)
    for i in range(random.randint(6, 10)):
        size = random.randint(6, 10)
        speed = random.randint(4, 8) * random.choice([-1, 1])
        angle = random.randint(0, 359)
        x_speed = math.sin(angle) * speed
        y_speed = math.cos(angle) * speed
        particle = RectParticle(
            game,
            x,
            y,
            x_speed,
            y_speed,
            size,
            size,
            -0.4,
            -0.4,
            random.randint(0, 20),
            235,
            random.randint(100, 200),
            52,
            180,
            options
        )
        game.particle_spawner.add_particles(particle)

def impact_animation(game, x, y, **kwargs):
    options = ParticleOptions(
        lifetime=10,
        render_on_top=True)
    for i in range(random.randint(8, 12)):
        size = random.randint(8, 12)
        speed = random.randint(4, 8) * random.choice([-1, 1])
        angle = random.randint(0, 359)
        x_speed = math.sin(angle) * speed
        y_speed = math.cos(angle) * speed
        particle = RectParticle(
            game,
            x,
            y,
            x_speed,
            y_speed,
            size,
            size,
            -0.4,
            -0.4,
            random.randint(0, 20),
            235,
            random.randint(100, 200),
            52,
            255,
            options
        )
        game.particle_spawner.add_particles(particle)


def large_impact_animation(game, x, y, **kwargs):
    options = ParticleOptions(
        lifetime=10,
        render_on_top=True)
    for i in range(random.randint(20, 30)):
        size = random.randint(12, 16)
        speed = random.randint(4, 8) * random.choice([-1, 1])
        angle = random.randint(0, 359)
        x_speed = math.sin(angle) * speed
        y_speed = math.cos(angle) * speed
        particle = RectParticle(
            game,
            x,
            y,
            x_speed,
            y_speed,
            size,
            size,
            -0.4,
            -0.4,
            random.randint(0, 20),
            235,
            random.randint(100, 200),
            52,
            255,
            options,
        )
        game.particle_spawner.add_particles(particle)

def buff_animation(game, x, y, **kwargs):
    follow_character = kwargs.get("follow_character", None)
    buff_and_debuff_animation(game, x, y, 255, (50, 150), 25, True, follow_character)

def debuff_animation(game, x, y, **kwargs):
    follow_character = kwargs.get("follow_character", None)
    buff_and_debuff_animation(game, x, y, 25, (50, 150), 255, False, follow_character)

def buff_spawner_animation(game, x, y, follow_character=None):
    buff_animation(game, x, y, follow_character=follow_character)
    for i in range(2):
        options = ParticleOptions(
            lifetime=10*(i+1), 
            death_function=(buff_animation, {"follow_character": follow_character})
            )
        game.particle_spawner.add_particles(CircleParticle(
        game,
        x, y,
        0, 0, 1, 0,
        0, 0, 0, 0,
        options))

def debuff_spawner_animation(game, x, y, follow_character=None):
    debuff_animation(game, x, y, follow_character=follow_character)
    for i in range(2):
        options = ParticleOptions(
            lifetime=10*(i+1), 
            death_function=(debuff_animation, {"follow_character": follow_character})
            )
        game.particle_spawner.add_particles(CircleParticle(
        game,
        x, y,
        0, 0, 1, 0,
        0, 0, 0, 0,
        options))

def buff_and_debuff_animation(game, x, y, r, g, b, travel_upward:bool, follow_character):
    if travel_upward:
        y_speed = -8
        starting_y_offset = 60
    else:
        y_speed = 8
        starting_y_offset = -60
    particles_to_spawn = 15
    particle_width = 8
    # negative spacing for some overlap
    particle_spacing = -4
    total_width = (particle_width + particle_spacing) * particles_to_spawn
    for i in range(particles_to_spawn):
        starting_height_modifier = 3 * abs(particles_to_spawn//2 - i) * (-1 if not travel_upward else 1)
        options = ParticleOptions(
            lifetime=16,
            render_on_top=True,
            reset_size_each_frame=True,
            follow_character=follow_character,
            follow_y_offset=starting_y_offset + starting_height_modifier,
            follow_x_offset=-(total_width//2)+(i*(particle_width+particle_spacing)))
        
        # height ranges from 8 to 40. it grows until its peak at max_lifetime/2, and then shrinks
        x_growth = particle_width
        y_growth = lambda a, b: max(8, (8 + int(-128 * (b*b - b))))
        red = randomize_if_tuple(r)
        green = randomize_if_tuple(g)
        blue = randomize_if_tuple(b)
        alpha = lambda a, b: 127 if b >= 0.5 else max(1, int(2 * b * 127))
        particle = RectParticle(
            game,
            x+options.follow_x_offset, y+options.follow_y_offset,
            0, y_speed,
            0, 0,
            x_growth, y_growth,
            0,
            red, green, blue, alpha,
            options)
        game.particle_spawner.add_particles(particle)
        

def spark_animation(game, x, y, **kwargs):
    recursions_left = kwargs.get("recursions_left", 1)
    options = ParticleOptions(
        lifetime=10,
        death_function=(spark_animation, {"recursions_left": recursions_left}),
        render_on_top=True)
    for i in range(random.randint(3, 5)):
        size = random.randint(3, 4)
        speed = random.randint(2, 4) * random.choice([-1, 1])
        angle = random.randint(0, 359)
        x_speed = math.sin(angle) * speed
        y_speed = math.cos(angle) * speed
        particle = RectParticle(
            game,
            x,
            y,
            x_speed,
            y_speed,
            size,
            size,
            -0.2,
            -0.2,
            random.randint(0, 45),
            random.randint(235, 250),
            random.randint(185, 225),
            random.randint(20, 80),
            255,
            options
        )
        game.particle_spawner.add_particles(particle)


def electric_spark_animation(game, x, y, **kwargs):
    recursions_left = kwargs.get("recursions_left", 1)
    options = ParticleOptions(
        lifetime=15,
        death_function=(spark_animation, {"recursions_left": recursions_left}),
        render_on_top=True)
    for i in range(random.randint(4, 6)):
        size = random.randint(5, 8)
        speed = random.randint(6, 10) * random.choice([-1, 1])
        angle = random.randint(0, 359)
        x_speed = math.sin(angle) * speed
        y_speed = math.cos(angle) * speed
        particle = RectParticle(
            game,
            x,
            y,
            x_speed,
            y_speed,
            size,
            size,
            -0.2,
            -0.2,
            random.randint(0, 45),
            random.randint(235, 250),
            random.randint(185, 225),
            random.randint(20, 80),
            255,
            options
        )
        game.particle_spawner.add_particles(particle)


def splash_animation(game, x, y, **kwargs):
    lifetime = (24,36)
    for i in range(random.randint(8, 12)):
        options = ParticleOptions(
            lifetime=randomize_if_tuple(lifetime),
            render_on_top=True)
        size = random.randint(8, 12)
        x_speed = random.randint(4, 8) * random.choice([-1, 1])
        y_speed = lambda a, b: random.randint(20, 30) * (0.5 - b)
        particle = CircleParticle(
            game,
            x,
            y,
            x_speed,
            y_speed,
            size,
            -0.2,
            50,
            random.randint(70, 170),
            230,
            255,
            options
        )
        game.particle_spawner.add_particles(particle)

def droplet_animation(game, x, y):
    options = ParticleOptions(
        lifetime=15,
        death_function=(splash_animation, {"recursions_left": 1}),
        render_on_top=True)
    particle = CircleParticle(
        game,
        x,
        y-40,
        0,
        4,
        8,
        +0.2,
        50,
        random.randint(70, 170),
        230,
        255,
        options
    )
    game.particle_spawner.add_particles(particle)


def flame_animation(game, x, y):
    lifetime = (24,36)
    # smoke
    for i in range(random.randint(6, 10)):
        options = ParticleOptions(
            lifetime=randomize_if_tuple(lifetime))
        size = random.randint(18, 24)
        x_speed = random.randint(-2, 2)
        y_speed = -random.randint(3, 6)
        particle = CircleParticle(
            game,
            x,
            y,
            x_speed,
            y_speed,
            size,
            -0.2,
            0,
            0,
            0,
            127,
            options
    )
        game.particle_spawner.add_particles(particle)
    # flames
    for i in range(random.randint(16, 20)):
        options = ParticleOptions(
            lifetime=randomize_if_tuple(lifetime),
            death_function=(spark_animation, {"recursions_left": 1}),
            render_on_top=True
            )
        size = random.randint(12, 18)
        x_speed = random.randint(-2, 2)
        y_speed = -random.randint(4, 8)
        particle = CircleParticle(
            game,
            x + random.randint(-size, size),
            y + random.randint(-size, size),
            x_speed,
            y_speed,
            size,
            -0.8,
            245,
            lambda a, b: int(random.randint(33, 99) + (b*120)),
            34,
            180,
            options
        )
        game.particle_spawner.add_particles(particle)


def psychic_animation(game, x, y):
    options = ParticleOptions(
        lifetime=20,
        leave_trail_every_nth_frame=1,
        render_on_top=True
        )
    x_size = 10
    y_size = 6
    y_growth = lambda a, b: 0 if b > 0.5 else -y_size/options.lifetime
    x_speed = 6
    y_speed_left = lambda a, b: np.cos(np.radians(360*b*4)) * 12
    y_speed_right = lambda a, b: np.sin(np.radians(360*b*4)) * -12
    particle_count = 10
    for i in range(particle_count):
        particle_left = RectParticle(
            game,
            x-(x_speed*options.lifetime/2) - (x_size/2),
            y + (y_size*(i-(particle_count/2))),
            x_speed,
            y_speed_left,
            x_size, y_size,
            0, y_growth,
            0,
            200,
            66,
            245,
            85,
            options
        )
        particle_right = RectParticle(
            game,
            x+(x_speed*options.lifetime/2) + (x_size/2),
            y - (y_size*(i-(particle_count/2))),
            -x_speed,
            y_speed_right,
            x_size, y_size,
            0, y_growth,
            0,
            166,
            36,
            36,
            85,
            options
        )
        game.particle_spawner.add_particles(particle_left)
        game.particle_spawner.add_particles(particle_right)
    spawner_options = ParticleOptions(
        lifetime=options.lifetime,
        death_function=(small_impact_animation, {"recursions_left": 1}))
    impact_particle_spawner = CircleParticle(
        game,
        x, y,
        0, 0,
        1, 0,
        0, 0, 0, 0,
        options=spawner_options)
    game.particle_spawner.add_particles(impact_particle_spawner)


def ice_shatter_animation(game, x, y):
    options = ParticleOptions(
        lifetime=25,
        )
    for i in range(random.randint(12, 20)):
        size = random.randint(4, 30)
        x_speed = random.randint(1, 6) * random.choice([-1, 1])
        y_speed = random.randint(1, 6)
        rotation = random.randint(0,45)
        rotation_speed = random.randint(0,15)
        particle = RectParticle(
            game,
            x + random.randint(-5,5),
            y + random.randint(-20,20),
            x_speed,
            y_speed,
            size,
            size,
            -0.4,
            -0.4,
            lambda a, b: (rotation + a*rotation_speed) % 360,
            random.randint(175, 200),
            random.randint(200, 225),
            random.randint(225, 255),
            155,
            options
    )
        game.particle_spawner.add_particles(particle)

def bolt_animation(game, x, y):
    options = ParticleOptions(
        lifetime=30,
        render_on_top=True
        )
    game.particle_spawner.add_particles(ImageParticle(game, x-30, y-88, 0, 0, "thunderbolt", 0, options))

def barrier_animation(game, x, y, image_key="protect transparent", follow_character=None):
    options = ParticleOptions(
        lifetime=36,
        render_on_top=True,
        follow_character=follow_character,
        follow_x_offset = -24,
        follow_y_offset = -24
    )
    game.particle_spawner.add_particles(ImageParticle(game, x-24, y-24, 0, 0, image_key, 0, options, frame_length=2))


def ice_animation(game, x, y):
    options = ParticleOptions(
        lifetime=74,
        render_on_top=True
        )
    game.particle_spawner.add_particles(IceParticle(
        game, x, y, options))


def punch_animation(game, x, y, **kwargs):
    options = ParticleOptions(
        lifetime=20,
        render_on_top=True
        )
    spawner_options = ParticleOptions(
        lifetime=max(1, options.lifetime // 2),
        death_function=(small_impact_animation, {"recursions_left": 1})
        )
    game.particle_spawner.add_particles(PunchParticle(game, x, y, options))
    game.particle_spawner.add_particles(CircleParticle(
        game,
        x, y,
        0, 0, 1, 0,
        0, 0, 0, 0,
        spawner_options))

def razor_leaf_animation(game, x, y):
    leaf_image_size = 40
    offset = leaf_image_size // 2
    x -= offset
    # the leaves end up a somewhat below where they start
    y -= (offset+10)
    options = ParticleOptions(
        lifetime=20,
        render_on_top=True,
        death_function=(impact_animation, {"recursions_left": 1})
        )
    game.particle_spawner.add_particles(RazorLeafParticle(game, x, y, False, options))
    game.particle_spawner.add_particles(RazorLeafParticle(game, x, y, True, options))

def punch_spawner_animation(game, x, y):
    lifetime = (1, 12)
    for i in range(5):
        options = ParticleOptions(
            lifetime=randomize_if_tuple(lifetime), 
            death_function=(punch_animation, {"recursions_left": 1})
            )
        game.particle_spawner.add_particles(CircleParticle(
        game,
        x+random.randint(-30, 30), y+random.randint(-30, 30),
        0, 0, 1, 0,
        0, 0, 0, 0,
        options))
