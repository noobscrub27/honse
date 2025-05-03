import random
import pygame
import numpy as np
import json
import base64
from io import BytesIO
from PIL import Image


# Initialize Pygame
pygame.init()
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Moving Balls with Vectors")
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
clock = pygame.time.Clock()


class Ball:
    def __init__(self, position, velocity, radius, color):
        self.position = np.array(position, dtype=float)
        self.velocity = np.array(velocity, dtype=float)
        self.radius = radius
        self.color = color

    def move(self):
        self.position += self.velocity

    def bounce(self):
        if self.position[0] - self.radius < 0 or self.position[0] + self.radius > WIDTH:
            self.velocity[0] *= -1
        if (
            self.position[1] - self.radius < 0
            or self.position[1] + self.radius > HEIGHT
        ):
            self.velocity[1] *= -1

    def draw(self, screen):
        pygame.draw.circle(screen, self.color, self.position.astype(int), self.radius)

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


def load_map(json_path, scale=1.0):
    with open(json_path, "r") as f:
        data = json.load(f)

    bg_img_data = base64.b64decode(data["image"])
    image = Image.open(BytesIO(bg_img_data))

    if scale != 1.0:
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.ANTIALIAS)

    background = pygame.image.fromstring(image.tobytes(), image.size, image.mode)

    walls = [
        {
            "x1": int(wall["x1"] * scale),
            "y1": int(wall["y1"] * scale),
            "x2": int(wall["x2"] * scale),
            "y2": int(wall["y2"] * scale),
            "nx": wall["nx"],
            "ny": wall["ny"],
        }
        for wall in data["walls"]
    ]

    areas = [
        {
            "x1": int(area["x1"] * scale),
            "y1": int(area["y1"] * scale),
            "x2": int(area["x2"] * scale),
            "y2": int(area["y2"] * scale),
        }
        for area in data["areas"]
    ]

    return walls, areas, background


def spawn_in_area(area):
    x = random.randint(area["x1"], area["x2"])
    y = random.randint(area["y1"], area["y2"])
    return [x, y]


def main():
    frame_count = 0
    
    N = 4

    walls, areas, background = load_map("map01.json", 1)

    balls = []
    for area in areas:
        print(area)
        for _ in range(N):
            position = spawn_in_area(area)
            angle = random.uniform(0, 2 * np.pi)
            velocity = [2 * np.cos(angle), 2 * np.sin(angle)]
            radius = random.randint(10, 20)
            color = (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )
            balls.append(Ball(position, velocity, radius, color))

    running = True
    while running:
        frame_count += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill(WHITE)

        screen.blit(background, (0, 0))
        #draw two areas, green and red
        area_a = areas[0]
        area_b = areas[1]
        pygame.draw.rect(
            screen,
            GREEN,
            (area_a["x1"], area_a["y1"], area_a["x2"] - area_a["x1"], area_a["y2"] - area_a["y1"]),
            2,
        )
        pygame.draw.rect(
            screen,
            RED,
            (area_b["x1"], area_b["y1"], area_b["x2"] - area_b["x1"], area_b["y2"] - area_b["y1"]),
            2,
        )
        
        for ball_1 in balls:
            for ball_2 in balls:
                if ball_1 != ball_2 and ball_1.is_colliding(ball_2):
                    ball_1.resolve_collision(ball_2)
            ball_1.move()
            ball_1.bounce()
            ball_1.draw(screen)
            for wall in walls:
                ball_1.collide_with_wall(wall)

        pygame.display.flip()

        clock.tick(60)
        if frame_count % 60 == 0:
            print(clock.get_fps())

    pygame.quit()


if __name__ == "__main__":
    main()
