from contextlib import redirect_stderr
import pygame
import random
import math
import numpy as np
import honse_data


# lots of particle variables can be changed each frame by passing a function instead of a constant
# these functions must take two parameters.
# the first parameter is the frames the particle has been alive
# the second parameter is the the number of frames the particle has been alive / it's maximum lifetime. it will always be in the range of 0 to 1.
# the functions may use one, both, or neither of these parameters
class CircleParticle:
    def __init__(
        self,
        game,
        x,
        y,
        x_speed,
        y_speed,
        radius,
        growth,
        red,
        green,
        blue,
        alpha,
        **kwargs
    ):
        lifetime = None
        if "lifetime" in kwargs:
            lifetime = kwargs["lifetime"]
        self.death_function = None
        if "death_function" in kwargs:
            self.death_function = kwargs["death_function"]
        self.leave_trail_every_nth_frame = -1
        if "leave_trail_every_nth_frame" in kwargs:
            self.leave_trail_every_nth_frame = kwargs["leave_trail_every_nth_frame"]
        self.render_on_top = False
        if "render_on_top" in kwargs:
            self.render_on_top = kwargs["render_on_top"]
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
        # leaves a trail every nth frame. -1 for no trail


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

    def update_size(self, lifetime_remaining):
        self.radius += self.growth(self.lived_lifetime, lifetime_remaining)

    def update_lifetime(self):
        self.lived_lifetime += 1
        if self.remaining_lifetime is not None:
            self.remaining_lifetime -= 1

    def check_alive(self):
        if self.radius <= 0:
            return False
        elif self.max_lifetime is not None:
            return self.remaining_lifetime > 0
        return True

    def kill(self):
        if self.death_function is not None:
            death_function = self.death_function[0]
            recursions_left = self.death_function[1]
            if recursions_left > 0:
                recursions_left -= 1
                death_function(self.game, self.x, self.y, recursion_count=recursions_left)
        del self

    def spawn_trail_particle(self):
        if self.leave_trail_every_nth_frame != -1 and self.lived_lifetime % self.leave_trail_every_nth_frame == 0:
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
                    lifetime=self.max_lifetime)
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
                    lifetime=self.max_lifetime)
            particle.lived_lifetime = self.lived_lifetime
            particle.remaining_lifetime = self.remaining_lifetime
            self.game.particle_spawner.add_particles(particle)

    def update(self):
        lifetime_remaining = self.get_lifetime_remaining()
        self.x += self.x_speed(self.lived_lifetime, lifetime_remaining)
        self.y += self.y_speed(self.lived_lifetime, lifetime_remaining)
        self.update_size(lifetime_remaining)
        self.color = (
            self.red(self.lived_lifetime, lifetime_remaining),
            self.green(self.lived_lifetime, lifetime_remaining),
            self.blue(self.lived_lifetime, lifetime_remaining),
            self.alpha(self.lived_lifetime, lifetime_remaining),
        )
        self.spawn_trail_particle()

    def draw(self):
        if self.radius >= 1:
            self.game.draw_circle(self.x, self.y, self.radius, self.color)


class RectParticle(CircleParticle):
    def __init__(
        self,
        game,
        x,
        y,
        x_speed,
        y_speed,
        width,
        height,
        x_growth,
        y_growth,
        rotation_degrees,
        red,
        green,
        blue,
        alpha,
        **kwargs
    ):
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
            **kwargs
        )

    def update_size(self, lifetime_remaining):
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
                particle.kill()


"""
class SlashParticleSpawner(ParticleSpawner):
    def __init__(self, x, y, x_speed, y_speed, radius, growth, red, green, blue, alpha, particle_lifetime, spawner_lifetime):
        super().__init__()
        self.x = x
        self.y = y
        self.x_speed = x_speed
        self.y_speed = y_speed
        self.radius = radius
        self.growth = growth
        self.red = red
        self.green = green
        self.blue = blue
        self.alpha = alpha
        if type(particle_lifetime) is int:
            self.particle_lifetime = lambda x: particle_lifetime
        else:
            self.particle_lifetime = particle_lifetime
        self.spawner_lifetime = spawner_lifetime
        self.spawner_max_lifetime = spawner_lifetime
        temporary_particle_spawners.append(self)

    def emit(self, screen):
        if self.spawner_lifetime > 0:
            particle = CircleParticle(
                self.x, self.y, self.x_speed, self.y_speed,
                self.radius, self.growth,
                self.red, self.green, self.blue, self.alpha,
                self.particle_lifetime(self.spawner_lifetime/self.spawner_max_lifetime))
            self.add_particles(particle)
        super().emit(screen)
        self.spawner_lifetime -= 1
        if self.spawner_lifetime <= 0 and len(self.particles) == 0:
            temporary_particle_spawners.remove(self)
            del self

"""
def randomize_if_tuple(value):
    if type(value) is tuple:
        return random.randint(value[0], value[1])
    else:
        return value

def impact_animation(game, x, y, **kwargs):
    lifetime = 10
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    for i in range(random.randint(8, 12)):
        size = random.randint(8, 12)
        x_speed = random.randint(4, 8) * random.choice([-1, 1])
        y_speed = random.randint(4, 8) * random.choice([-1, 1])
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
            lifetime=randomize_if_tuple(lifetime),
            render_on_top=True
        )
        game.particle_spawner.add_particles(particle)


def large_impact_animation(game, x, y, **kwargs):
    lifetime = 10
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    for i in range(random.randint(20, 30)):
        size = random.randint(12, 16)
        x_speed = random.randint(4, 8) * random.choice([-1, 1])
        y_speed = random.randint(4, 8) * random.choice([-1, 1])
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
            lifetime=randomize_if_tuple(lifetime),
        )
        game.particle_spawner.add_particles(particle)


def spark_animation(game, x, y, **kwargs):
    lifetime = 10
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    for i in range(random.randint(3, 5)):
        size = random.randint(3, 4)
        x_speed = random.randint(2, 4) * random.choice([-1, 1])
        y_speed = random.randint(2, 4) * random.choice([-1, 1])
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
            lifetime=randomize_if_tuple(lifetime),
            death_function=(spark_animation, recursion_count)
        )
        game.particle_spawner.add_particles(particle)


def electric_spark_animation(game, x, y, **kwargs):
    lifetime = 15
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    for i in range(random.randint(3, 5)):
        size = random.randint(5, 8)
        speed = random.randint(2, 4)
        x_speed = speed * random.choice([-1, 1])
        y_speed = speed * random.choice([-1, 1])
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
            lifetime=randomize_if_tuple(lifetime),
            death_function=(spark_animation, recursion_count)
        )
        game.particle_spawner.add_particles(particle)


def splash_animation(game, x, y, **kwargs):
    lifetime = (24,36)
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    for i in range(random.randint(8, 12)):
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
            lifetime=randomize_if_tuple(lifetime)
        )
        game.particle_spawner.add_particles(particle)


def flame_animation(game, x, y, **kwargs):
    lifetime = (24,36)
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
        print(recursion_count)
    # smoke
    for i in range(random.randint(8, 12)):
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
            64,
            lifetime=randomize_if_tuple(lifetime)
    )
        game.particle_spawner.add_particles(particle)
    # flames
    for i in range(random.randint(20, 28)):
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
            lifetime=randomize_if_tuple(lifetime),
            death_function=(spark_animation, recursion_count)
        )
        game.particle_spawner.add_particles(particle)


def psychic_animation(game, x, y, **kwargs):
    lifetime = 12
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    x_size = 10
    y_size = 6
    y_growth = lambda a, b: 0 if b > 0.5 else -y_size/lifetime
    x_speed = 6
    y_speed_left = lambda a, b: np.cos(np.radians(360*b*4)) * 8
    y_speed_right = lambda a, b: np.sin(np.radians(360*b*4)) * -8
    particle_count = 10
    highest_lifetime = lifetime[1] if type(lifetime) is tuple else lifetime
    for i in range(particle_count):
        particle_left = RectParticle(
            game,
            x-(x_speed*highest_lifetime/2) - (x_size/2),
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
            lifetime=randomize_if_tuple(lifetime),
            leave_trail_every_nth_frame=1,
            render_on_top=True
        )
        particle_right = RectParticle(
            game,
            x+(x_speed*highest_lifetime/2) + (x_size/2),
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
            lifetime=randomize_if_tuple(lifetime),
            leave_trail_every_nth_frame=1,
        )
        game.particle_spawner.add_particles(particle_left)
        game.particle_spawner.add_particles(particle_right)
    impact_particle_spawner = CircleParticle(
        game,
        x, y,
        0, 0,
        1, 0,
        0, 0, 0, 0,
        lifetime=lifetime[1] if type(lifetime) is tuple else lifetime,
        death_animation=(spark_animation, 1))
    game.particle_spawner.add_particles(impact_particle_spawner)


def ice_shatter_animation(game, x, y, **kwargs):
    lifetime = 10
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    for i in range(random.randint(4, 8)):
        size = random.randint(8, 24)
        x_speed = random.randint(4, 8) * random.choice([-1, 1])
        y_speed = random.randint(4, 8) * random.choice([-1, 1])
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
            random.randint(0,45),
            60,
            random.randint(185, 250),
            random.randint(215, 250),
            155,
            lifetime=randomize_if_tuple(lifetime)
    )
        game.particle_spawner.add_particles(particle)


def ice_animation(game, x, y, **kwargs):
    lifetime = 30
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    growth = 2
    angle = random.randint(35,55)
    for i in range(12, 18):
        size = random.randint(15, 30)
        particle = RectParticle(
            game,
            x + random.randint(-size,size*2),
            y + random.randint(-size,size*2),
            -growth/2,
            -growth/2,
            size,
            size,
            growth,
            growth,
            angle,
            60,
            random.randint(185, 250),
            random.randint(215, 250),
            random.randint(45, 90),
            lifetime=randomize_if_tuple(lifetime),
            death_animation=(ice_shatter_animation, recursion_count),
            render_on_top=random.random() > 0.5
        )
        angle += 45
        game.particle_spawner.add_particles(particle)

def bolt_animation(game, x, y, **kwargs):
    lifetime = 24
    recursion_count = 3
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    lifetime = randomize_if_tuple(lifetime)
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    height = 120
    bolt_spawn = y-(3*height//4)
    width = 12
    r = lambda a, b: 240 if a % 12 >= 4 else 230
    g = lambda a, b: 223 if a % 12 >= 4 else 205
    b = lambda a, b: 117 if a % 12 >= 4 else 44
    x_speed = lambda a, b: random.randint(-8, 8) if a % 2 and random.random() < 0.5 else 0
    bolt_particle = RectParticle(
        game,
        x-width//2, bolt_spawn, x_speed, 0,
        width, height, 0, 0, 0,
        r, g, b, 180,
        lifetime=lifetime,
        render_on_top=True)
    for i in range(lifetime//2):
        game.particle_spawner.add_particles(CircleParticle(
            game,
            x, bolt_spawn+height, 0, 0, 1, 0,
            0, 0, 0, 0,
            lifetime=max(1,i*2), 
            death_function=(electric_spark_animation, 1),
            render_on_top=True))
    sparkle_spawner = CircleParticle(
        game,
        x, bolt_spawn+height, 0, 0, 1, 0,
        0, 0, 0, 0,
        lifetime=lifetime, 
        death_function=(electric_spark_animation, recursion_count),
        render_on_top=True)
    game.particle_spawner.add_particles(bolt_particle)
    game.particle_spawner.add_particles(sparkle_spawner)


def punch_animation(game, x, y, **kwargs):
    lifetime = 24
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    x_size = 40
    y_size = 30
    negative_rotation = random.choice([-1, 1])
    rotation = lambda a, b: (negative_rotation * 15) - (negative_rotation * 15 * b * 4) if b > 0.75 else 0
    highest_lifetime = lifetime[1] if type(lifetime) is tuple else lifetime
    game.particle_spawner.add_particles(RectParticle(
        game,
        x-x_size//2,
        y-y_size//2,
        0,
        0,
        x_size, y_size,
        lambda a, b: 0 if b > 0.25 else -x_size/10,
        lambda a, b: 0 if b > 0.25 else -y_size/10,
        rotation,
        235, 134, 26,
        85,
        lifetime=randomize_if_tuple(lifetime[1] if type(lifetime) is tuple else lifetime),
        leave_trail_every_nth_frame=1,
        render_on_top=True
    ))
    impact_animation(game, x, y)

def punch_spawner_animation(game, x, y, **kwargs):
    lifetime = (1, 12)
    recursion_count = 1
    if lifetime in kwargs:
        lifetime = kwargs["lifetime"]
    if "recursion_count" in kwargs:
        recursion_count = kwargs["recursion_count"]
    for i in range(5):
        x = x + random.randint(-20, 20)
        y = y + random.randint(-15, 15)
        game.particle_spawner.add_particles(CircleParticle(
        game,
        x, y, 0, 0, 1, 0,
        0, 0, 0, 0,
        lifetime=randomize_if_tuple(lifetime), 
        death_function=(punch_animation, recursion_count)))
