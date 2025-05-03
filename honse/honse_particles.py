import pygame
import random
import math

import honse_data

# lots of particle variables can be changed each frame by passing a function instead of a constant
# these functions must take two parameters.
# the first parameter is the frames the particle has been alive
# the second parameter is the the number of frames the particle has been alive / it's maximum lifetime. it will always be in the range of 0 to 1.
# the functions may use one, both, or neither of these parameters
class CircleParticle:
    def __init__(self, game, x, y, x_speed, y_speed, radius, growth, red, green, blue, alpha, lifetime=None, death_function=None):
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
        self.color = (255,255,255,255)
        self.death_function = death_function

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
        elif self.max_lifetime is None:
            return self.remaining_lifetime > 0
        return True


    def kill(self):
        if self.death_function is not None:
            self.death_function(self.game, self.x, self.y)
        del self

    def update(self):
        lifetime_remaining = self.get_lifetime_remaining()
        self.x += self.x_speed(self.lived_lifetime, lifetime_remaining)
        self.y += self.y_speed(self.lived_lifetime, lifetime_remaining)
        self.update_size(lifetime_remaining)
        self.color = (
            self.red(self.lived_lifetime, lifetime_remaining),
            self.green(self.lived_lifetime, lifetime_remaining),
            self.blue(self.lived_lifetime, lifetime_remaining),
            self.alpha(self.lived_lifetime, lifetime_remaining))

    def draw(self):
        if self.radius >= 1:
            self.game.draw_circle(self.x, self.y, self.radius, self.color)

class RectParticle(CircleParticle):
    def __init__(self, game, x, y, x_speed, y_speed, width, height, x_growth, y_growth, rotation_degrees, red, green, blue, alpha, lifetime=None, death_function=None):
        self.width = width
        self.height = height
        self.x_growth = self.turn_into_function(x_growth)
        self.y_growth = self.turn_into_function(y_growth)
        self.rotation_degrees = self.turn_into_function(rotation_degrees)
        super().__init__(game, x, y, x_speed, y_speed, None, None, red, green, blue, alpha, lifetime, death_function)

    def update_size(self, lifetime_remaining):
        self.width += self.x_growth(self.lived_lifetime, lifetime_remaining)
        self.height += self.y_growth(self.lived_lifetime, lifetime_remaining)

    def check_alive(self):
        if self.height <= 0 or self.width <= 0:
            return False
        elif self.max_lifetime is None:
            return self.remaining_lifetime > 0
        return True

    def draw(self):
        if self.width >= 1 and self.height >= 1:
            rotation = self.rotation_degrees(self.lived_lifetime, self.get_lifetime_remaining())
            self.game.draw_rectangle(self.x, self.y, self.width, self.height, rotation, self.color)

class ParticleSpawner:
    def __init__(self, game):
        self.particles = []
        self.game = game

    def emit(self):
        if self.particles:
            self.delete_particles()
            for particle in self.particles:
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
'''
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

'''

def impact_animation(game, x, y):
    for i in range(random.randint(8,12)):
        size = random.randint(8,12)
        x_speed = random.randint(4, 8) * random.choice([-1, 1])
        y_speed = random.randint(4, 8) * random.choice([-1, 1])
        particle = RectParticle(
            game, x, y, x_speed, y_speed,
            size, size, -0.4, -0.4, random.randint(0,20),
            235, random.randint(100,200), 52, 255, 10)
        game.particle_spawner.add_particles(particle)

def large_impact_animation(game, x, y):
    for i in range(random.randint(20,30)):
        size = random.randint(12,16)
        x_speed = random.randint(4, 8) * random.choice([-1, 1])
        y_speed = random.randint(4, 8) * random.choice([-1, 1])
        particle = RectParticle(
            game, x, y, x_speed, y_speed,
            size, size, -0.4, -0.4, random.randint(0,20),
            235, random.randint(100,200), 52, 255, 10)
        game.particle_spawner.add_particles(particle)


def spark_animation(game, x, y):
    for i in range(random.randint(3,5)):
        size = random.randint(3,4)
        x_speed = random.randint(2, 4) * random.choice([-1, 1])
        y_speed = random.randint(2, 4) * random.choice([-1, 1])
        particle = RectParticle(
            game, x, y, x_speed, y_speed,
            size, size, -0.2, -0.2, random.randint(0,45),
            random.randint(235,250), random.randint(185,225), random.randint(20,80), 255, 10)
        game.particle_spawner.add_particles(particle)

def splash_animation(game, x, y):
    for i in range(random.randint(8,12)):
        size = random.randint(8,12)
        x_speed = random.randint(4, 8) * random.choice([-1, 1])
        y_speed = lambda a, b: random.randint(20, 30) * (0.5-b)
        particle = CircleParticle(
            game, x, y, x_speed, y_speed, size, -0.2,
            50, random.randint(70,170), 230, 255, random.randint(24,36))
        game.particle_spawner.add_particles(particle)

def flame_animation(game, x, y):
    for i in range(random.randint(8,12)):
        size = random.randint(8,12)
        x_speed = random.randint(4, 8) * random.choice([-1, 1])
        y_speed = lambda a, b: random.randint(20, 30) * (0.5-b)
        particle = CircleParticle(
            x, y, x_speed, y_speed, size, -0.2,
            50, random.randint(70,170), 230, 255, random.randint(24,36))
        game.particle_spawner.add_particles(particle)