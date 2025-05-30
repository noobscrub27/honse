from collections import defaultdict
import os.path
import tempfile
import pygame

pygame.init()
pygame.font.init()
pygame.mixer.init()
import random
import math
import honse_data
import honse_pokemon
import honse_particles
import sys
import json
import numpy as np
import base64
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import cProfile
import functools
import os
import subprocess
import numpy as np
from pydub import AudioSegment
import datetime

#may break things
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Check https://habr.com/ru/articles/545850/
def to_numpy(im):
    im.load()
    # unpack data
    e = Image._getencoder(im.mode, 'raw', im.mode)
    e.setimage(im.im)

    # NumPy buffer for the result
    shape, typestr = Image._conv_type_shape(im)
    data = np.empty(shape, dtype=np.dtype(typestr))
    mem = data.data.cast('B', (data.data.nbytes,))

    bufsize, s, offset = 65536, 0, 0
    while not s:
        l, s, d = e.encode(bufsize)
        mem[offset:offset + len(d)] = d
        offset += len(d)
    if s < 0:
        raise RuntimeError("encoder error %d in tobytes" % s)
    return data

class HonseGame:
    def __init__(
        self,
        json_path,
        background,
        music_folder,
        pygame_mode,
        video_mode,
        width=1920,
        fps=60,
    ):
        self.pygame_mode = pygame_mode
        self.video_mode = video_mode
        self.game_end_timer = 300
        self.game_end = False
        self.SCREEN_WIDTH = width
        self.SCREEN_HEIGHT = int(width * 9/16)
        self.FRAMES_PER_SECOND = fps
        if self.pygame_mode:
            self.screen = pygame.display.set_mode((self.SCREEN_WIDTH , self.SCREEN_HEIGHT))
        else:
            self.screen = pygame.display.set_mode((self.SCREEN_WIDTH , self.SCREEN_HEIGHT), flags=pygame.HIDDEN)
        self.clock = pygame.time.Clock()
        self.running = True
        self.dt = 0
        self.frame_count = 0
        self.characters = []
        self.number_of_teams = 2
        self.hazards = []
        self.json_path = json_path
        self.particle_spawner = honse_particles.ParticleSpawner(self)
        self.temporary_particle_spawners = []
        self.cell_size = 30
        self.wall_grid = defaultdict(list)
        # message lists for rendering purposes
        self.current_frame_messages = []
        self.all_frame_messages = []
        # message log for other purposes
        # [message, dispalyed_to_users (bool)]
        self.message_log = []
        self.background = background
        self.current_frame_image = None
        self.current_frame_draw = None
        now = datetime.datetime.now()
        now_text = now.strftime("%m-%d-%Y %H-%M-%S ")
        self.video_out_path = os.path.join("output", now_text+"output.mp4")
        self.log_out_path = os.path.join("output", now_text+"log.txt")
        self.draw_every_nth_frame = 1
        music_folder = os.path.join("bgm", music_folder)
        files_in_music_folder = os.listdir(music_folder)
        self.music = os.path.join(music_folder, random.choice(files_in_music_folder))
        self.width_ratio = self.SCREEN_WIDTH / 1920
        self.sound_events = []
        self.particle_images = {}
        self.particle_surfaces = {}
        self.status_icon_images = {}
        self.status_icon_surfaces = {}
        # this is stored in the game bc i want all the statuses to update at the same time
        # i think it will look nice :)
        self.update_status_icons_in_n_frames = honse_data.STATUS_ICON_BLINK_LENGTH
        self.environment_type = honse_pokemon.ENVIRONMENTS["grass"]
        self.weather = honse_pokemon.Weather.CLEAR
        self.load_map()
        self.create_sounds()
        self.play_music()
        self.font_setup()
        self.load_status_icons()
        self.load_image_particles()
        
    def load_image_particles(self):
        path = os.path.join("vfx", "particles")
        self.particle_images["punch"] = [Image.open(os.path.join(path, "punch.png"))]
        self.particle_surfaces["punch"] = [honse_data.image_to_surface(self.particle_images["punch"][0])]
        for opacity in [80, 60, 40, 20]:
            self.particle_images["punch"].append(honse_data.alpha_change(self.particle_images["punch"][0].copy(), opacity))
            self.particle_surfaces["punch"].append(honse_data.image_to_surface(self.particle_images["punch"][-1]))
        razor_leaf = Image.open(os.path.join(path, "razor leaf.png"))
        transparent_razor_leaf = honse_data.alpha_change(razor_leaf.copy(), 75)
        self.particle_images["razor leaf"] = honse_data.from_sprite_sheet(razor_leaf, 40)
        self.particle_surfaces["razor leaf"] = [honse_data.image_to_surface(item) for item in self.particle_images["razor leaf"]]
        self.particle_images["razor leaf transparent"] = honse_data.from_sprite_sheet(transparent_razor_leaf, 40)
        self.particle_surfaces["razor leaf transparent"] = [honse_data.image_to_surface(item) for item in self.particle_images["razor leaf transparent"]]
        thunderbolt = Image.open(os.path.join(path, "thunderbolt.png"))
        self.particle_images["thunderbolt"] = honse_data.from_sprite_sheet(thunderbolt, 60)
        self.particle_surfaces["thunderbolt"] = [honse_data.image_to_surface(item) for item in self.particle_images["thunderbolt"]]
        ice = Image.open(os.path.join(path, "ice.png"))
        new_size = (int(ice.size[0]*1.5), int(ice.size[1]*1.5))
        ice = ice.resize(new_size)
        transparent_ice = honse_data.alpha_change(ice.copy(), 75)
        self.particle_images["ice"] = honse_data.from_sprite_sheet(ice, 120)
        self.particle_surfaces["ice"] = [honse_data.image_to_surface(item) for item in self.particle_images["ice"]]
        self.particle_images["ice transparent"] = honse_data.from_sprite_sheet(transparent_ice, 120)
        self.particle_surfaces["ice transparent"] = [honse_data.image_to_surface(item) for item in self.particle_images["ice transparent"]]
        
    def load_status_icons(self):
        path = os.path.join("vfx", "status icons")
        files = os.listdir(path)
        for file in files:
            no_file_extension = file.removesuffix(".png")
            file_path = os.path.join(path, file)
            self.status_icon_images[no_file_extension] = Image.open(file_path)
            self.status_icon_surfaces[no_file_extension] = honse_data.image_to_surface(self.status_icon_images[no_file_extension])

    def times_width_ratio(self, value):
        # is it faster to do it this way? idk!!!!
        # does it matter? i also dont know!!!!!!
        return value if self.width_ratio == 1 else int(max(1, value*self.width_ratio))

    def font_setup(self):
        # [pygame font, PIL font, height of font in pixels]
        self.message_fonts = {
            16: [
                pygame.font.Font(honse_data.FONT_NAME, self.times_width_ratio(16)),
                ImageFont.truetype(honse_data.FONT_NAME, self.times_width_ratio(16)),
            ],
            20: [
                pygame.font.Font(honse_data.FONT_NAME, self.times_width_ratio(20)),
                ImageFont.truetype(honse_data.FONT_NAME, self.times_width_ratio(20)),
            ],
            24: [
                pygame.font.Font(honse_data.FONT_NAME, self.times_width_ratio(24)),
                ImageFont.truetype(honse_data.FONT_NAME, self.times_width_ratio(24)),
            ],
            28: [
                pygame.font.Font(honse_data.FONT_NAME, self.times_width_ratio(28)),
                ImageFont.truetype(honse_data.FONT_NAME, self.times_width_ratio(28)),
            ],
            48: [
                pygame.font.Font(honse_data.FONT_NAME, self.times_width_ratio(48)),
                ImageFont.truetype(honse_data.FONT_NAME, self.times_width_ratio(48)),
            ],
        }
        for value in self.message_fonts.values():
            # im like 90% sure that ascent + descent is the same as font size
            # but just in case it doesnt hurt to do it this way
            value.append(value[0].get_ascent() - value[0].get_descent())
        self.message_y_offset = 5
        self.message_x_offset = 10

    def play_music(self):
        if self.pygame_mode:
            pygame.mixer.music.load(self.music)
            pygame.mixer.music.play(0)
        if self.video_mode:
            pass
            # i'll get to you
            #
            # no need :3 - lina

    def create_sounds(self):
        DIR = "sfx_wave"
        files = os.listdir(DIR)
        self.sounds = {}
        for file in files:
            no_file_extension = file.removesuffix(".mp3").removesuffix(".wav")
            file_path = os.path.join(DIR, file)
            self.sounds[no_file_extension] = [
                file_path,
                pygame.mixer.Sound(file_path)
                ]

    def play_sound(self, sound, repeat=0):
        if self.pygame_mode:
            self.sounds[sound][1].play(repeat)
        if self.video_mode:
            self.sound_events.append(
                (self.frame_count, sound, repeat)
            )

    def save_into_ffmpeg(self, frame):
        # frame.show()
        # exit()
        frame_array = to_numpy(frame)
        frame_bytes = memoryview(frame_array)

        try:
            self.video_writer.stdin.write(frame_bytes)
        except BrokenPipeError:
            print("Broken pipe error: FFmpeg process may have terminated.")
        except Exception as e:
            print(f"Error writing to FFmpeg stdin: {e}")

    
    def render_audio(self) -> None:
        # Abandon hope, all ye who enter here
        # - Lina
        SR          = 44_100             
        FPS         = self.FRAMES_PER_SECOND
        FRAME_SIZE  = SR // FPS             
        HEADROOM_DB = -9               
        LIMIT_PAD   = 0.97    
        SFX_GAIN_DB = -3  
        
        def seg_to_float(seg: AudioSegment) -> np.ndarray:
            seg = seg.fade_in(5).fade_out(5)  # small 5ms fades to reduce clicks
                                              # bounce.mp3 >:)
            pcm = np.array(seg.get_array_of_samples(), dtype=np.float32)
            pcm = pcm.reshape(-1, seg.channels) / 32_768.0
            if seg.channels == 1:
                pcm = np.repeat(pcm, 2, axis=1)
            return pcm

        def soft_limiter(x: np.ndarray, threshold=0.9):
            return np.tanh(x / threshold) * threshold
        total_frames   = self.frame_count + 1
        total_samples  = total_frames * FRAME_SIZE
        master         = np.zeros((total_samples, 2), dtype=np.float32)

        
        bg_seg = (AudioSegment
                .from_file(self.music)
                .set_frame_rate(SR)
                .set_channels(2)
                .apply_gain(HEADROOM_DB))

        bg = seg_to_float(bg_seg)
        loops_needed = math.ceil(total_samples / len(bg))
        master += np.tile(bg, (loops_needed, 1))[:total_samples]

        sfx_cache: dict[str, np.ndarray] = {}

        def load_sfx(name: str) -> np.ndarray:
            if name not in sfx_cache:
                #print("Loading sound effect:", name)
                seg = (AudioSegment
                    .from_file(self.sounds[name][0])
                    .set_frame_rate(SR)
                    .set_channels(2)
                    .fade_in(10)
                    .fade_out(10)
                    .low_pass_filter(15000)
                    .normalize(headroom=3.0)
                    .apply_gain(HEADROOM_DB + SFX_GAIN_DB))
                sfx_cache[name] = seg_to_float(seg)
            return sfx_cache[name]

        for frame_idx, name, repeat in self.sound_events:
            start = frame_idx * FRAME_SIZE
            sfx   = load_sfx(name)

            for i in range(repeat + 1):
                off = start + i * len(sfx)
                if off >= total_samples:
                    break
                end   = min(off + len(sfx), total_samples)
                block = sfx[:end - off]
                master[off:end] += block

        master = soft_limiter(master)

        dither = np.random.uniform(-1e-4, 1e-4, size=master.shape)
        pcm16 = ((master + dither) * 32767.0).clip(-32768, 32767).astype('<i2')
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
            AudioSegment(
            pcm16.tobytes(),
            frame_rate=SR,
            sample_width=2,
            channels=2
            ).export(tmpfile.name, format="wav")
            self.audio_tempfile = tmpfile.name
        
    def first_draw(self):
        if self.video_mode:
            image = Image.new(
                mode="RGBA",
                size=(self.SCREEN_WIDTH, self.SCREEN_HEIGHT),
                color=(255, 255, 255, 255),
            )
            image.paste(self.background_image, (0, 0))
            draw = ImageDraw.Draw(image, "RGBA")
            for character in self.characters:
                character.ui_element.first_draw(draw)
            self.background_image = image
            temp_video_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            self.video_tempfile = temp_video_file.name
            self.video_writer = subprocess.Popen(
                [
                    "ffmpeg",
                    "-y",

                    # VIDEO -------------
                    "-f", "rawvideo", "-pix_fmt", "rgba",
                    "-s", f"{self.SCREEN_WIDTH}x{self.SCREEN_HEIGHT}",
                    "-r", str(self.FRAMES_PER_SECOND / self.draw_every_nth_frame),
                    "-i", "-",          

                    # OUTPUT ------------
                    "-vf", "format=yuv420p",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "192k",
                    self.video_tempfile
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            
            self.current_frame_image = Image.new(
                "RGBA", (self.SCREEN_WIDTH, self.SCREEN_HEIGHT)
            )
            self.current_frame_draw = ImageDraw.Draw(self.current_frame_image)

    def show_display(self):
        if self.pygame_mode:
            pygame.display.flip()
        if self.video_mode and self.current_frame_image is not None:
            self.save_into_ffmpeg(self.current_frame_image)

    def draw_background(self):
        if self.pygame_mode:
            self.screen.fill("white")
            self.screen.blit(self.background_surface, (0, 0))
        if self.video_mode:
            self.current_frame_image.paste(self.background_image)

    def draw_circle(self, x, y, radius, rgba):
        x = self.times_width_ratio(x)
        y = self.times_width_ratio(y)
        size = (radius*2, radius*2)
        radius = self.times_width_ratio(radius)
        if self.pygame_mode:
            color = pygame.Color(rgba[0], rgba[1], rgba[2], rgba[3])
            if rgba[3] != 255:
                circle_surface = pygame.Surface(
                    (radius * 2, radius * 2), pygame.SRCALPHA
                )
                pygame.draw.circle(circle_surface, color, (radius, radius), radius)
                self.screen.blit(circle_surface, (x - radius, y - radius))
            else:
                pygame.draw.circle(self.screen, color, (x, y), int(radius))
        if self.video_mode: 
            if rgba[3] == 255:
                self.current_frame_draw.ellipse(
                    (x - radius, y - radius, x + radius, y + radius), fill=rgba
                )
                return size
            # Doing alpha-composite magic here
            # - lina
            min_x = max(0, int(x - radius))
            min_y = max(0, int(y - radius))
            max_x = min(self.SCREEN_WIDTH, int(x + radius))
            max_y = min(self.SCREEN_HEIGHT, int(y + radius))
            box_width = max_x - min_x
            box_height = max_y - min_y
            if box_width <= 0 or box_height <= 0:
                return size
            overlay = Image.new("RGBA", (box_width, box_height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay, "RGBA")
            draw.ellipse((0, 0, box_width - 1, box_height - 1), fill=rgba)

            region = self.current_frame_image.crop((min_x, min_y, max_x, max_y))
            blended = Image.alpha_composite(region, overlay)
            self.current_frame_image.paste(blended, (min_x, min_y))
        return size

    # https://stackoverflow.com/questions/34747946/rotating-a-square-in-pil
    # answer by Sparkler
    # im not sure but i think this code is no longer used since lina fixed this function
    # but it was used at one point so im keeping the citation for now
    def draw_rectangle(self, x_pos, y_pos, width, height, rotation, rgba):
        size = (width, height)
        x_pos = self.times_width_ratio(x_pos)
        y_pos = self.times_width_ratio(y_pos)
        width = self.times_width_ratio(width)
        height = self.times_width_ratio(height)
        if self.pygame_mode:
            color = pygame.Color(rgba[0], rgba[1], rgba[2], rgba[3])
            if rotation % 360 != 0:
                surface = pygame.Surface((width, height), pygame.SRCALPHA)
                surface.fill(color)
                surface = pygame.transform.rotate(surface, rotation)
                rect = surface.get_rect(center=(x_pos, y_pos))
                self.screen.blit(surface, (rect.x, rect.y))
            else:
                if rgba[3] != 255:
                    rect_surface = pygame.Surface((width, height), pygame.SRCALPHA)
                    rect = pygame.Rect(0, 0, width, height)
                    pygame.draw.rect(rect_surface, color, rect)
                    self.screen.blit(rect_surface, (x_pos, y_pos))
                else:
                    rect = pygame.Rect(x_pos, y_pos, width, height)
                    pygame.draw.rect(self.screen, color, rect)
        if self.video_mode:
            if rotation % 360 == 0:
                verticies = [
                    (x_pos, y_pos),
                    (x_pos + width, y_pos),
                    (x_pos + width, y_pos + height),
                    (x_pos, y_pos + height),
                ]
            else:
                rotation_radians = np.radians(rotation)
                c, s = math.cos(rotation_radians), math.sin(rotation_radians)
                rectCoords = [
                    (width / 2.0, height / 2.0),
                    (width / 2.0, -height / 2.0),
                    (-width / 2.0, -height / 2.0),
                    (-width / 2.0, height / 2.0),
                ]
                verticies = [
                    (c * x - s * y + x_pos, s * x + c * y + y_pos)
                    for (x, y) in rectCoords
                ]
                
            if rgba[3] == 255:
                self.current_frame_draw.polygon(verticies, fill=rgba)
                return size
            # omg doing alpha-composite magic here too
            # - lina
            # ty!!! :)
            xs, ys = zip(*verticies)
            min_x, max_x = int(min(xs)), int(max(xs))
            min_y, max_y = int(min(ys)), int(max(ys))
            min_x = max(0, min_x)
            min_y = max(0, min_y)
            max_x = min(self.SCREEN_WIDTH, max_x)
            max_y = min(self.SCREEN_HEIGHT, max_y)
            if max_x <= min_x or max_y <= min_y:
                return size

            box_width = max_x - min_x
            box_height = max_y - min_y

            overlay = Image.new("RGBA", (box_width, box_height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay, "RGBA")
            shifted_verts = [(x - min_x, y - min_y) for x, y in verticies]
            draw.polygon(shifted_verts, fill=rgba)

            region = self.current_frame_image.crop((min_x, min_y, max_x, max_y))
            blended = Image.alpha_composite(region, overlay)
            self.current_frame_image.paste(blended, (min_x, min_y))
        return size

    def draw_image(self, x, y, pygame_surface, pil_image):
        if self.pygame_mode:
            self.screen.blit(pygame_surface, (x, y))
        if self.video_mode:
            self.current_frame_image.paste(pil_image, (int(x), int(y)), pil_image)
        return pil_image.size

    @functools.lru_cache(maxsize=512)
    def get_text_image(self, text, font_key, r, g, b, a):
        font = self.message_fonts[font_key][1]
        empty = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(empty)
        size = draw.textbbox((0, 0), text, font=font)
        width, height = size[2] - size[0], size[3] - size[1]
        img = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(img)
        draw.text((-size[0], -size[1]), text, (r, g, b, a), font=font)
        return img, (width, height)

    def draw_text(self, x, y, text, font_key, r, g, b, a):
        x = self.times_width_ratio(x)
        y = self.times_width_ratio(y)
        if self.pygame_mode:
            color = pygame.Color(r, g, b)
            text_surface = self.message_fonts[font_key][0].render(text, False, color)
            text_surface.set_alpha(a)
            self.screen.blit(text_surface, (x, y))
        if self.video_mode:
            img, size = self.get_text_image(text, font_key, r, g, b, a)
            self.current_frame_image.paste(img, (int(x), int(y)), img)
        else:
            size = (text_surface.get_width() * 1920 / self.SCREEN_WIDTH,
             text_surface.get_height() * 1080 / self.SCREEN_HEIGHT)
        return size

    def check_game_end(self):
        team1_alive = len(
            [
                character
                for character in self.characters
                if character.team == 0 and not character.is_fainted()
            ]
        )
        team2_alive = len(
            [
                character
                for character in self.characters
                if character.team == 1 and not character.is_fainted()
            ]
        )
        if not team1_alive and team2_alive:
            self.display_message("Team 2 wins!", 48, honse_data.TEAM_COLORS[1])
            self.game_end = True
        elif not team2_alive and team1_alive:
            self.display_message("Team 1 wins!", 48, honse_data.TEAM_COLORS[0])
            self.game_end = True
        elif not team2_alive and not team1_alive:
            self.display_message("Tie!", 48, [0, 0, 0])
            self.game_end = True

    def add_character(self, name, team, level, stats, moves, types, image):
        number_of_teammates = len([i for i in self.characters if i.team == team])
        character = honse_pokemon.Character(
            self, name, team, level, stats, moves, types, image, number_of_teammates
        )
        self.characters.append(character)

    def display_message(self, text, font_index, RGBA):
        self.message_log.append([text, True])
        self.current_frame_messages.append([text, font_index, RGBA])

    def render_all_messages(self):
        # this is where the next text box should be drawn
        y = honse_data.BASE_HEIGHT
        if len(self.current_frame_messages):
            reversed_copy = [msg for msg in self.current_frame_messages]
            reversed_copy.reverse()
            self.current_frame_messages = []
            self.all_frame_messages = [reversed_copy] + self.all_frame_messages
        frames_since_most_recent_frame = 0
        for frame_of_messages in self.all_frame_messages:
            for message_data in frame_of_messages:
                message = message_data[0]
                font_key = message_data[1]
                r = message_data[2][0]
                g = message_data[2][1]
                b = message_data[2][2]
                if frames_since_most_recent_frame == 0:
                    a = 255
                else:
                    a = max(127, (192 - 16 * frames_since_most_recent_frame))
                x = int(honse_data.BASE_WIDTH * 0.75) + self.message_x_offset
                y -= self.message_y_offset + self.message_fonts[font_key][2]
                if y < 0:
                    return
                self.draw_text(x, y, message, font_key, r, g, b, a)
                y -= self.message_y_offset
            frames_since_most_recent_frame += 1

    # Lina functions start here
    def grid_coord(self, x, y):
        return int(x) // self.cell_size, int(y) // self.cell_size

    def cells_wall_crosses(self, x1, y1, x2, y2):
        cells = set()
        steps = int(max(abs(x2 - x1), abs(y2 - y1)) / self.cell_size) + 1
        for i in range(steps + 1):
            t = i / steps
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            cells.add(self.grid_coord(x, y))
        return cells

    def load_map(self, scale=1.0):
        with open(self.json_path, "r") as f:
            data = json.load(f)
        bg_img_data = base64.b64decode(data["image"])
        image = Image.open(BytesIO(bg_img_data))
        if scale != 1.0:
            new_size = (int(image.width * scale), int(image.height * scale))
            image = image.resize(new_size, Image.ANTIALIAS)
        if self.background is None:
            self.background_surface = pygame.image.fromstring(
                image.tobytes(), image.size, image.mode
            )
            self.background_image = Image.open(BytesIO(image.tobytes()))
        else:
            self.background_surface = pygame.image.load(self.background)
            self.background_image = Image.open(self.background).convert("RGBA")

        self.walls = [
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
        self.areas = [
            {
                "x1": int(area["x1"] * scale),
                "y1": int(area["y1"] * scale),
                "x2": int(area["x2"] * scale),
                "y2": int(area["y2"] * scale),
            }
            for area in data["areas"]
        ]
        for wall in self.walls:
            x1, y1 = wall["x1"], wall["y1"]
            x2, y2 = wall["x2"], wall["y2"]
            cells = self.cells_wall_crosses(x1, y1, x2, y2)
            for cell in cells:
                self.wall_grid[cell].append(wall)

    def spawn_in_area(self, area_index):
        x = random.randint(self.areas[area_index]["x1"], self.areas[area_index]["x2"])
        y = random.randint(self.areas[area_index]["y1"], self.areas[area_index]["y2"])
        return [x, y]

    # Lina functions end here

    def main_loop(self):
        self.first_draw()
        average_fps = []
        try:
            while self.running:
                self.frame_count += 1
                if not self.game_end:
                    if self.frame_count == honse_data.SUDDEN_DEATH_FRAMES:
                        self.display_message("Sudden death!", 48, [127, 0, 0])
                    if self.frame_count >= honse_data.SUDDEN_DEATH_FRAMES:
                        meteor_frequency = max(30, 300 // (2 ** (self.frame_count // honse_data.SUDDEN_DEATH_FRAMES)))
                        if self.frame_count % meteor_frequency == 0:
                            radius = 100
                            max_x = ((3 * 1920) // 4) - radius
                            max_y = ((3 * 1080) // 4) - radius
                            damage_options = honse_pokemon.DamageEffectOptions(
                                damage=1/4,
                                percent_of_max_hp_damage=True,
                                message="A falling meteor hit TARGET!",
                                sound="Hit Normal Damage")
                            hazard_options = honse_pokemon.HazardOptions(
                                lifetime=180,
                                hazard_set_radius_growth_time=90,
                                active_radius_growth_time=60,
                                active_full_radius_duration=30,
                                knockback=5,
                                immune_timer=45,
                                effect=honse_pokemon.DamageEffect,
                                effect_options=damage_options)
                            honse_pokemon.Hazard(
                                options=hazard_options,
                                position=(random.randint(radius, max_x), random.randint(radius, max_y)),
                                radius=radius,
                                game=self)
                if len(self.message_log) and self.message_log[-1][0].startswith("##### FRAME "):
                    self.message_log[-1][0] = f"##### FRAME {self.frame_count} #####"
                else:
                    self.message_log.append([f"##### FRAME {self.frame_count} #####", False])
                # poll for events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        sys.exit()

                self.draw_background()

                # delete particles
                self.particle_spawner.delete_particles()
                # draw particles that display on bottom
                self.particle_spawner.emit()
                for spawner in self.temporary_particle_spawners:
                    spawner.delete_particles()
                    spawner.emit()

                change_status_icon_this_frame = False
                self.update_status_icons_in_n_frames -= 1
                if self.update_status_icons_in_n_frames <= 0:
                    self.update_status_icons_in_n_frames = honse_data.STATUS_ICON_BLINK_LENGTH
                    change_status_icon_this_frame = True
                # update ui
                for character in self.characters:
                    if change_status_icon_this_frame:
                        character.ui_element.next_status_icon()
                    character.ui_element.display()

                # sort by speed
                tangible_characters = filter(
                    lambda c: not c.is_intangible(), self.characters
                )
                tangible_characters = sorted(
                    tangible_characters, key=lambda x: x.current_modified_stats["SPE"], reverse=True
                )

                collisions = []
                for character in tangible_characters:
                    for other_character in tangible_characters:
                        if other_character is character:
                            continue
                        if character.is_colliding(other_character):
                            character.use_move(other_character)
                            collisions.append([character, other_character])

                for collision in collisions:
                    collision[0].resolve_collision(collision[1])

                # update sorted list
                speed_sorted_characters = sorted(
                    self.characters, key=lambda x: x.current_modified_stats["SPE"], reverse=True
                )

                # check hazards
                for hazard in self.hazards:
                    for character in speed_sorted_characters:
                        if hazard.can_activate(character) and hazard.is_colliding(character):
                            hazard.activate(character)
                # update loop
                for character in speed_sorted_characters:
                    character.update()
                for hazard in self.hazards:
                    hazard.update()

                # move loop
                for character in speed_sorted_characters:
                    character.move()
                for hazard in self.hazards:
                    hazard.move()

                # end of turn effects
                for character in speed_sorted_characters:
                    character.end_of_turn()

                # draw loop
                # draw hazards
                for hazard in self.hazards:
                    hazard.draw()
                # fainted characters should appear below other characters. Draw them first
                for character in sorted(
                    self.characters, key=lambda x: 0 if x.is_fainted() else 1
                ):
                    character.draw()

                # draw particles that display on top
                self.particle_spawner.emit(True)
                for spawner in self.temporary_particle_spawners:
                    spawner.emit(True)

                if not self.game_end:
                    self.check_game_end()

                self.render_all_messages()
                if self.running and self.frame_count % self.draw_every_nth_frame == 0:
                    self.show_display()

                if self.pygame_mode:
                    self.clock.tick(self.FRAMES_PER_SECOND)
                else:
                    self.clock.tick(0)
                average_fps.append(self.clock.get_fps())
                '''
                if self.frame_count % honse_data.FRAMES_PER_SECOND == 0:
                    print(f"FPS: {np.mean(average_fps)}")
                    average_fps = []
                '''

                if self.game_end:
                    self.game_end_timer -= 1
                    if self.game_end_timer < 0:
                        self.running = False
        except KeyboardInterrupt:
            self.running = False
        finally:
            # i commented out some of these print statements for now
            # i think we're at the point where most of the basic functionality is consistently working as expected
            # so i don't want to outright delete these print logs as we may need them later
            # we should be safe not to have all of them on screen each run
            # especially now that ive added a way to run the game dozens of times for testing reasons
            print(f"Game complete! Average FPS: {np.mean(average_fps)}")
            with open(self.log_out_path, "w") as f:
                for message in self.message_log:
                    f.write(message[0]+"\n")
            if self.video_mode:
                try:
                    self.video_writer.stdin.close()
                    #print("Closed FFmpeg stdin.")
                except Exception as e:
                    print(f"Failed to close FFmpeg stdin: {e}")
                try:
                    #print("Waiting for FFmpeg to finish")
                    self.video_writer.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print("FFmpeg did not terminate in time, killing it.")
                    self.video_writer.kill()

                if self.video_writer.returncode != 0:
                    print(
                        "FFmpeg returned non-zero exit status:",
                        self.video_writer.returncode,
                    )
                else:
                    print("FFmpeg finished successfully.")
                #print("Rendering audio")
                self.render_audio()
                #print("Adding audio to video")
                subprocess.run([
                    "ffmpeg",
                    "-y",
                    "-i", self.video_tempfile,
                    "-i", self.audio_tempfile,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    self.video_out_path
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                print("Audio added to video")
                
def get_test_stats(base_stats):
    stat_names = ["HP", "ATK", "DEF", "SPA", "SPD", "SPE"]
    stats = {
        "base stats": base_stats,
        "ivs": {stat: random.randint(0, 31) for stat in stat_names},
        "evs": {stat: 0 for stat in stat_names},
        "nature": random.choice(list(honse_data.NATURES.values()))
            }
    ev_budget = 510
    random.shuffle(stat_names)
    for stat in stat_names:
        evs = random.randint(0, min(255, ev_budget))
        ev_budget -= evs
        stats["evs"][stat] = evs
        if ev_budget == 0:
            break
    return stats
    

test_pokemon = {
    "Saurbot": {
        "stats": {"HP": 77, "ATK": 5, "DEF": 107, "SPA": 5, "SPD": 104, "SPE": 20},
        "types": [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]],
        "file": "bob.png"},
    "Saur": {
        "stats": {"HP": 114, "ATK": 44, "DEF": 104, "SPA": 95, "SPD": 138, "SPE": 55},
        "types": [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Poison"]],
        "file": "saur.png"},
    "Apollo": {
        "stats": {"HP": 88, "ATK": 119, "DEF": 103, "SPA": 117, "SPD": 101, "SPE": 94},
        "types": [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Ghost"]],
        "file": "apollo.png"},
    "Dragonite": {
        "stats": {"HP": 91, "ATK": 134, "DEF": 95, "SPA": 100, "SPD": 100, "SPE": 80},
        "types": [honse_pokemon.pokemon_types["Dragon"], honse_pokemon.pokemon_types["Flying"]],
        "file": "dragonite.png"},
    "Alakazam": {
        "stats": {"HP": 55, "ATK": 50, "DEF": 45, "SPA": 135, "SPD": 95, "SPE": 120},
        "types": [honse_pokemon.pokemon_types["Psychic"]],
        "file": "alakazam.png"},
    "Warwolf": {
        "stats": {"HP": 106, "ATK": 116, "DEF": 69, "SPA": 46, "SPD": 87, "SPE": 96},
        "types": [honse_pokemon.pokemon_types["Ice"], honse_pokemon.pokemon_types["Dark"]],
        "file": "warwolf.png"},
    "Sudowoodo": {
        "stats": {"HP": 80, "ATK": 115, "DEF": 125, "SPA": 30, "SPD": 65, "SPE": 55},
        "types": [honse_pokemon.pokemon_types["Rock"]],
        "file": "sudowoodo.png"},
    "Croconaw": {
        "stats": {"HP": 75, "ATK": 90, "DEF": 85, "SPA": 59, "SPD": 68, "SPE": 68},
        "types": [honse_pokemon.pokemon_types["Water"]],
        "file": "croconaw.png"},
    "Drowzee": {
        "stats": {"HP": 67, "ATK": 79, "DEF": 61, "SPA": 64, "SPD": 94, "SPE": 42},
        "types": [honse_pokemon.pokemon_types["Psychic"]],
        "file": "drowzee.png"},
    "Luxio": {
        "stats": {"HP": 70, "ATK": 105, "DEF": 60, "SPA": 85, "SPD": 60, "SPE": 70},
        "types": [honse_pokemon.pokemon_types["Electric"], honse_pokemon.pokemon_types["Dark"]],
        "file": "luxio.png"},
    "Riolu": {
        "stats": {"HP": 50, "ATK": 75, "DEF": 45, "SPA": 45, "SPD": 45, "SPE": 70},
        "types": [honse_pokemon.pokemon_types["Fighting"]],
        "file": "riolu.png"},
    "Manaphy": {
        "stats": {"HP": 100, "ATK": 100, "DEF": 100, "SPA": 100, "SPD": 100, "SPE": 100},
        "types": [honse_pokemon.pokemon_types["Water"]],
        "file": "manaphy.png"},
    "Steelix": {
        "stats": {"HP": 75, "ATK": 95, "DEF": 200, "SPA": 50, "SPD": 75, "SPE": 25},
        "types": [honse_pokemon.pokemon_types["Steel"], honse_pokemon.pokemon_types["Ground"]],
        "file": "steelix.png"},
    "Camerupt": {
        "stats": {"HP": 100, "ATK": 110, "DEF": 75, "SPA": 125, "SPD": 90, "SPE": 40},
        "types": [honse_pokemon.pokemon_types["Fire"], honse_pokemon.pokemon_types["Ground"]],
        "file": "camerupt.png"},
    }
def play_game(games_to_play):
    for i in range(games_to_play):
        print(f"Starting game {i+1}/{games_to_play}.")
        combatants = random.sample(list(test_pokemon.keys()), 8)
        

        # i am lazy and dont want to resize the map rn
        # plz pass in a map that is 3/4 the size of height and width for the second parameter
        game = HonseGame("map03.json", "map03.png", "wild", True, True)
        for i, character in enumerate(combatants):
            if i < 4:
                team = 0
            elif i < 8:
                team = 1
            else:
                team = random.randint(0, 1)
            game.add_character(
                character,
                team,
                100,
                get_test_stats(test_pokemon[character]["stats"]),
                random.sample(list(honse_pokemon.MOVES.values()), 4),
                test_pokemon[character]["types"],
                test_pokemon[character]["file"]
                )
        game.main_loop()
    print(honse_data.BUG_FINDER.get_found_bugs())
cProfile.run("play_game(1)", sort="cumtime", filename="res")

import pstats

p = pstats.Stats("res")
p.strip_dirs()
p.sort_stats("cumulative").print_stats(40)
pygame.quit()

