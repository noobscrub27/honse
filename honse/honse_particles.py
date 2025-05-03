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
    def __init__(self, x, y, x_speed, y_speed, radius, growth, red, green, blue, alpha, lifetime=None):
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
        # this is a failsafe, and should always be changed later
        self.color = 'white'

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
        del self

    def update(self, game):
        lifetime_remaining = self.get_lifetime_remaining()
        self.x += game.scale_to_fps(self.x_speed(self.lived_lifetime, lifetime_remaining))
        self.y += game.scale_to_fps(self.y_speed(self.lived_lifetime, lifetime_remaining))
        self.update_size(lifetime_remaining)
        self.color = pygame.Color(
            self.red(self.lived_lifetime, lifetime_remaining),
            self.green(self.lived_lifetime, lifetime_remaining),
            self.blue(self.lived_lifetime, lifetime_remaining),
            self.alpha(self.lived_lifetime, lifetime_remaining))

    def draw(self, screen):
        pygame.draw.circle(screen, self.color, (self.x, self.y), int(self.radius))

class RectParticle(CircleParticle):
    def __init__(self, x, y, x_speed, y_speed, width, height, x_growth, y_growth, rotation_degrees, red, green, blue, alpha, lifetime=None):
        self.width = width
        self.height = height
        self.x_growth = self.turn_into_function(x_growth)
        self.y_growth = self.turn_into_function(y_growth)
        self.rotation_degrees = self.turn_into_function(rotation_degrees)
        super().__init__(x, y, x_speed, y_speed, None, None, red, green, blue, alpha, lifetime)

    def update_size(self, lifetime_remaining):
        self.width += self.x_growth(self.lived_lifetime, lifetime_remaining)
        self.height += self.y_growth(self.lived_lifetime, lifetime_remaining)

    def check_alive(self):
        if self.height <= 0 or self.width <= 0:
            return False
        elif self.max_lifetime is None:
            return self.remaining_lifetime > 0
        return True

    def draw(self, screen):
        rotation = self.rotation_degrees(self.lived_lifetime, self.get_lifetime_remaining())
        if rotation % 360 != 0:
            try:
                surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            except pygame.error:
                print((self.width, self.height))
                return
            surface.fill(self.color)
            surface = pygame.transform.rotate(surface, rotation)
            rect = surface.get_rect(center=(self.x,self.y))
            screen.blit(surface, (rect.x, rect.y)) 
        else:
            rect = pygame.Rect(0, 0, self.width, self.height)
            rect.center = (self.x, self.y)
            pygame.draw.rect(screen, self.color, rect)

class ParticleSpawner:
    def __init__(self, game):
        self.particles = []
        self.game = game

    def emit(self):
        if self.particles:
            self.delete_particles()
            for particle in self.particles:
                particle.draw(self.game.screen)
                particle.update(self.game)
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
def basic_collision(location, game):
    for i in range(random.randint(8,12)):
        size = random.randint(8,12)
        x_speed = random.randint(4, 8) * random.choice([-1, 1])
        y_speed = random.randint(4, 8) * random.choice([-1, 1])
        particle = RectParticle(
            location[0], location[1], x_speed, y_speed,
            size, size, -0.4, -0.4, random.randint(0,20),
            235, random.randint(100,200), 52, 255, 10)
            
        game.particle_spawner.add_particles(particle)