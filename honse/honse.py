from collections import defaultdict
from email.policy import default
import tempfile
import pygame
import random
import math
import honse_data
import honse_pokemon
import honse_particles
import sys
import json
import numpy as np
import base64
from PIL import Image, ImageDraw
from io import BytesIO
import cProfile
import functools
import os
import subprocess
import numpy as np
from pydub import AudioSegment
import datetime
import pstats
import colorsys
from video_uploader import video_uploader

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
        json_path: str,
        background: str,
        background_bw: str,
        music_folder: str,
        teams: list,
        pygame_mode: bool,
        video_mode: bool,
        environment: honse_pokemon.Environments,
        encounter_type: honse_pokemon.EncounterTypes,
        default_weather: honse_pokemon.Weather,
        daytime: bool,
        width: int = 1920,
        fps: int = 60,
        zoom_level: float = 1
    ):
        self.success = False
        self.background_bw = Image.open(background_bw).convert("1")
        self.game_complete_text = ""
        self.pygame_mode = pygame_mode and honse_data.PYGAME_ENABLED
        self.video_mode = video_mode
        self.game_end_timer = 300
        self.game_end = False
        self.SCREEN_WIDTH = width
        self.SCREEN_HEIGHT = int(width * 9/16)
        self.width_ratio = self.SCREEN_WIDTH / 1920
        self.FRAMES_PER_SECOND = fps
        self.zoom_level = zoom_level
        # this needs to be done before the characters are added because each character's ui needs access to the fonts
        self.font_setup()
        if self.pygame_mode:
            self.screen = pygame.display.set_mode((self.SCREEN_WIDTH , self.SCREEN_HEIGHT))
            self.clock = pygame.time.Clock()
        else:
            #self.screen = pygame.display.set_mode((self.SCREEN_WIDTH , self.SCREEN_HEIGHT), flags=pygame.HIDDEN)
            self.screen = None
            self.clock = None
        self.running = True
        self.frame_count = 0
        self.teams = teams
        self.characters = []
        ui_width = 240
        ui_padding = 5
        ui_options = honse_data.UIElementOptions(width=ui_width)
        current_x = self.SCREEN_WIDTH - (ui_width + ui_padding)
        current_y = ui_padding
        largest_ui_height = 0
        for i, team in enumerate(self.teams):
            team.team_id = i
            team.in_battle = True
            team.game = self
            for mon in team.pokemon:
                self.characters.append(mon.to_character(
                    game=self,
                    team=team,
                    ui_x=0, ui_y=0,
                    ui_options=ui_options))
                if self.characters[-1].ui_element.height > largest_ui_height:
                    largest_ui_height = self.characters[-1].ui_element.height
        for mon in self.characters:
            mon.ui_element.x = current_x
            mon.ui_element.y = current_y
            current_y += ui_padding + largest_ui_height
            if current_y + largest_ui_height + ui_padding > self.SCREEN_HEIGHT:
                current_x -= (ui_width + ui_padding)
                current_y = ui_padding
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
        self.video_out_path = honse_data.get_absolute_path(os.path.join("output", now_text+"output.mp4"))
        self.log_out_path = honse_data.get_absolute_path(os.path.join("output", now_text+"log.txt"))
        self.draw_every_nth_frame = 1
        music_folder = honse_data.get_absolute_path(os.path.join("bgm", music_folder))
        files_in_music_folder = os.listdir(music_folder)
        self.music = honse_data.get_absolute_path(os.path.join(music_folder, random.choice(files_in_music_folder)))
        self.sound_events = []
        # this is stored in the game bc i want all the statuses to update at the same time
        # i think it will look nice :)
        self.update_status_icons_in_n_frames = honse_data.STATUS_ICON_BLINK_LENGTH
        # field effects should eventually be moved to a system similar to effects for pokemon
        self.default_weather = default_weather
        self.weather = self.default_weather
        self.environment = environment
        self.encounter_type = encounter_type
        self.daytime = daytime
        self.load_map()
        self.play_music()
        for character in self.characters:
            character.spawn_in()
        
    def times_width_ratio(self, value):
        # is it faster to do it this way? idk!!!!
        # does it matter? i also dont know!!!!!!
        return value if self.width_ratio == 1 else int(max(1, value*self.width_ratio))

    def font_setup(self):
        self.message_fonts = {
            "gen4": honse_data.HonseFont(self, "gen4", honse_data.get_absolute_path(os.path.join("fonts", "pokemon-gen-4-fullwidth", "pokemon-gen-4-fullwidth.otf")))
        }
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

    def play_sound(self, sound, repeat=0):
        if self.pygame_mode:
            honse_data.SOUNDS[sound][1].play(repeat)
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
                    .from_file(honse_data.SOUNDS[name][0])
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
            # the number of pixels that will be cut off by the edges of the screen
            offscreen = False
            if x - radius < 0 or x + radius > self.SCREEN_WIDTH * 3 // 4 or y - radius < 0 or y + radius > self.SCREEN_HEIGHT * 3 // 4:
                offscreen = True
            if rgba[3] == 255 and not offscreen:
                self.current_frame_draw.ellipse(
                    (x - radius, y - radius, x + radius, y + radius), fill=rgba
                )
                return size
            # Doing alpha-composite magic here
            # - lina
            min_x = int(x - radius)
            min_y = int(y - radius)
            max_x = int(x + radius)
            max_y = int(y + radius)
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

    def draw_text(self, text, x, y):
        x = self.times_width_ratio(x)
        y = self.times_width_ratio(y)
        text.draw(x, y)
        return text.get_size()

    def check_game_end(self):
        alive = []
        for team in self.teams:
            if not team.eliminated():
                alive.append(team)
        if len(alive) == 1:
            self.display_message(alive[0].get_name()+" wins!", "gen4", 48, (0, 0, 0, 255))
            self.game_end = True
        elif len(alive) == 0:
            self.display_message("Tie!", "gen4", 48, (0, 0, 0, 255))
            self.game_end = True

    def display_message(self, text, font_name, size, rgba):
        text = honse_data.HonseText(self, text, self.message_fonts[font_name], size, rgba)
        if len(text.display_text):
            self.message_log.append([text.display_text, True])
            self.current_frame_messages.append(text)

    def render_all_messages(self):
        # this is where the next text box should be drawn
        y = self.SCREEN_HEIGHT
        if len(self.current_frame_messages):
            reversed_copy = [msg for msg in self.current_frame_messages]
            reversed_copy.reverse()
            self.current_frame_messages = []
            self.all_frame_messages = [reversed_copy] + self.all_frame_messages
        frames_since_most_recent_frame = 0
        for frame_of_messages in self.all_frame_messages:
            for message in frame_of_messages:
                if frames_since_most_recent_frame == 0:
                    a = 224
                else:
                    a = max(64, (160 - 8 * frames_since_most_recent_frame))
                new_background_color = (255, 255, 255, int(a))
                if message.background_color != new_background_color:
                    message.background_color = new_background_color
                    message.gradient_size = 40
                    message.background_image = None
                    message.background_surface = None
                    message.get_background_image()
                x = self.message_x_offset + 50
                y -= self.message_y_offset + message.background_image_size[1]
                if y < 0:
                    return
                message.draw(x, y)
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
        start_timestamp = datetime.datetime.now().timestamp()
        try:
            while self.running:
                self.frame_count += 1
                if not self.game_end:
                    if self.frame_count == honse_data.SUDDEN_DEATH_FRAMES:
                        self.display_message("Sudden death!", "gen4", 48, (127, 0, 0, 255))
                        self.display_message("Pokemon will randomly become the center of attention!", "gen4", 24, (127, 0, 0, 255))
                    elif self.frame_count == honse_data.SUDDEN_DEATH_FRAMES * 2:
                        self.display_message("YOUR TAKING TOO LONG", "gen4", 48, (127, 0, 0, 255))
                    if self.frame_count >= honse_data.SUDDEN_DEATH_FRAMES:
                        hazard_frequency = 300
                        if self.frame_count % hazard_frequency == 0:
                            radius = 500
                            alive_characters = [character for character in self.characters if not character.is_fainted()]
                            if len(alive_characters):
                                character = random.choice(alive_characters)
                                options = honse_pokemon.CenterOfAttentionOptions(lifetime=180, radius=radius)
                                honse_pokemon.CenterOfAttentionEffect(options, self, None, None, character)
                    # it should take ~300 frames (5 seconds) to kill a full health mon
                    if self.frame_count > honse_data.SUDDEN_DEATH_FRAMES * 2 and self.frame_count % 3 == 0:
                        for character in self.characters:
                            if not character.is_fainted():
                                damage = character.max_hp / 100
                                character.do_damage(None, damage, silent=True)
                if len(self.message_log) and self.message_log[-1][0].startswith("##### FRAME "):
                    self.message_log[-1][0] = f"##### FRAME {self.frame_count} #####"
                else:
                    self.message_log.append([f"##### FRAME {self.frame_count} #####", False])
                # poll for events
                if honse_data.PYGAME_ENABLED:
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
                for team in self.teams:
                    team.update()

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
                # fainted characters and captured characters should appear below other characters. Draw them first
                for character in sorted(
                    self.characters, key=lambda x: 0 if x.is_fainted() or x.in_pokeball else 1
                ):
                    character.draw()

                # draw particles that display on top
                self.particle_spawner.emit(True)
                for spawner in self.temporary_particle_spawners:
                    spawner.emit(True)

                if not self.game_end:
                    self.check_game_end()

                # update ui
                for character in self.characters:
                    character.tried_to_attack_this_frame = False
                    if change_status_icon_this_frame:
                        character.ui_element.next_status_icon()
                    character.ui_element.display()
                
                self.render_all_messages()
                if self.running and self.frame_count % self.draw_every_nth_frame == 0:
                    self.show_display()

                if self.pygame_mode:
                    self.clock.tick(self.FRAMES_PER_SECOND)

                if self.game_end:
                    self.game_end_timer -= 1
                    if self.game_end_timer < 0:
                        self.running = False
                        for team in self.teams:
                            team.in_battle = False
                            for character in team.characters:
                                character.game_end()
        except KeyboardInterrupt:
            self.running = False
        finally:
            # i commented out some of these print statements for now
            # i think we're at the point where most of the basic functionality is consistently working as expected
            # so i don't want to outright delete these print logs as we may need them later
            # we should be safe not to have all of them on screen each run
            # especially now that ive added a way to run the game dozens of times for testing reasons
            end_timestamp = datetime.datetime.now().timestamp()
            time_elapsed = end_timestamp - start_timestamp
            fps = self.frame_count / time_elapsed
            self.game_complete_text = f"Game complete in {time_elapsed:.2f} seconds ({self.frame_count} frames). FPS: {fps:.2f}"
            print(self.game_complete_text)
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
                self.success = True
                
def get_test_stats():
    stat_names = ["HP", "ATK", "DEF", "SPA", "SPD", "SPE"]
    stats = {
        "ivs": {stat: random.randint(0, 31) for stat in stat_names},
        "evs": {stat: 0 for stat in stat_names},
        "nature": random.choice(list(honse_data.NATURES.keys()))
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
    
TEST_SPECIES = [
    honse_pokemon.Species(0, "Saurbot", "bob.png",
                          {"HP": 77, "ATK": 5, "DEF": 107, "SPA": 5, "SPD": 104, "SPE": 20},
                          [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Steel"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Saur", "saur.png",
                          {"HP": 114, "ATK": 44, "DEF": 104, "SPA": 95, "SPD": 138, "SPE": 55},
                          [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Poison"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Stoutland", "stoutland.png",
                          {"HP": 85, "ATK": 120, "DEF": 95, "SPA": 45, "SPD": 95, "SPE": 80},
                          [honse_pokemon.pokemon_types["Normal"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Vesuvius", "vesuvius.png",
                          {"HP": 78, "ATK": 97, "DEF": 81, "SPA": 150, "SPD": 87, "SPE": 122},
                          [honse_pokemon.pokemon_types["Fire"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Apollo", "apollo.png",
                          {"HP": 88, "ATK": 119, "DEF": 103, "SPA": 117, "SPD": 101, "SPE": 94},
                          [honse_pokemon.pokemon_types["Grass"], honse_pokemon.pokemon_types["Ghost"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Dragonite", "dragonite.png",
                          {"HP": 91, "ATK": 134, "DEF": 95, "SPA": 100, "SPD": 100, "SPE": 80},
                          [honse_pokemon.pokemon_types["Dragon"], honse_pokemon.pokemon_types["Flying"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Alakazam", "alakazam.png",
                          {"HP": 55, "ATK": 50, "DEF": 45, "SPA": 135, "SPD": 95, "SPE": 120},
                          [honse_pokemon.pokemon_types["Psychic"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Warwolf", "warwolf.png",
                          {"HP": 106, "ATK": 116, "DEF": 69, "SPA": 46, "SPD": 87, "SPE": 96},
                          [honse_pokemon.pokemon_types["Ice"], honse_pokemon.pokemon_types["Dark"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Sudowoodo", "sudowoodo.png",
                          {"HP": 80, "ATK": 115, "DEF": 125, "SPA": 30, "SPD": 65, "SPE": 55},
                          [honse_pokemon.pokemon_types["Rock"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Croconaw", "croconaw.png",
                          {"HP": 75, "ATK": 90, "DEF": 85, "SPA": 59, "SPD": 68, "SPE": 68},
                          [honse_pokemon.pokemon_types["Water"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Drowzee", "drowzee.png",
                          {"HP": 67, "ATK": 79, "DEF": 61, "SPA": 64, "SPD": 94, "SPE": 42},
                          [honse_pokemon.pokemon_types["Psychic"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Luxio", "luxio.png",
                          {"HP": 70, "ATK": 105, "DEF": 60, "SPA": 85, "SPD": 60, "SPE": 70},
                          [honse_pokemon.pokemon_types["Electric"], honse_pokemon.pokemon_types["Dark"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Riolu", "riolu.png",
                          {"HP": 50, "ATK": 75, "DEF": 45, "SPA": 45, "SPD": 45, "SPE": 70},
                          [honse_pokemon.pokemon_types["Fighting"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Manaphy", "Manaphy.png",
                          {"HP": 100, "ATK": 100, "DEF": 100, "SPA": 100, "SPD": 100, "SPE": 100},
                          [honse_pokemon.pokemon_types["Water"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Steelix", "steelix.png",
                          {"HP": 75, "ATK": 95, "DEF": 200, "SPA": 50, "SPD": 75, "SPE": 25},
                          [honse_pokemon.pokemon_types["Steel"], honse_pokemon.pokemon_types["Ground"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Camerupt", "camerupt.png",
                          {"HP": 100, "ATK": 110, "DEF": 75, "SPA": 125, "SPD": 90, "SPE": 40},
                          [honse_pokemon.pokemon_types["Fire"], honse_pokemon.pokemon_types["Ground"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Electrode", "electrode.png",
                          {"HP": 60, "ATK": 80, "DEF": 70, "SPA": 100, "SPD": 80, "SPE": 150},
                          [honse_pokemon.pokemon_types["Electric"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    honse_pokemon.Species(0, "Shuckle", "shuckle.png",
                          {"HP": 20, "ATK": 10, "DEF": 230, "SPA": 10, "SPD": 230, "SPE": 5},
                          [honse_pokemon.pokemon_types["Bug"], honse_pokemon.pokemon_types["Rock"]],
                          {}, [], [], 10, honse_pokemon.GrowthRates.MEDIUM_FAST, {}, 0, 140, 45),
    ]

def saurbot_test(teams):
    game = HonseGame(
        json_path = "map05.json",
        background = "map05.png",
        background_bw = "map05bw.png",
        music_folder = "wild",
        teams = teams,
        pygame_mode = True,
        video_mode = True,
        environment = honse_pokemon.Environments.INDOORS,
        encounter_type = honse_pokemon.EncounterTypes.WILD_ENCOUNTER,
        default_weather = honse_pokemon.Weather.CLEAR,
        daytime = True)
    game.main_loop()
    return game

def get_random_player_color():
    h = random.random()
    s = random.uniform(0.8, 1)
    v = random.uniform(0.6, 0.8)
    return [round(i * 255) for i in colorsys.hsv_to_rgb(h,s,v)]

def test_game(games_to_play):
    moves_list = list(honse_pokemon.MOVES.values())
    for i in range(games_to_play):
        print(f"Starting game {i+1}/{games_to_play}.")
        number_of_teams_player_teams = 2
        pokemon_per_team = 3
        number_of_wild_pokemon = 3
        level = 100
        teams = []
        for i in range(number_of_teams_player_teams):
            teams.append(honse_pokemon.Team(f"Player {i+1}", get_random_player_color()))
            for j in range(pokemon_per_team):
                species = random.choice(TEST_SPECIES)
                stats = get_test_stats()
                mon = honse_pokemon.Pokemon(
                    species = species,
                    level = level,
                    experience = 0,
                    moves = random.sample(moves_list, 4),
                    #moves = [honse_pokemon.MOVES["Helping Hand"], honse_pokemon.MOVES["Flare Blitz"], honse_pokemon.MOVES["Take Down"]],
                    #moves = [honse_pokemon.MOVES["Explosion"]],
                    nature = stats["nature"],
                    ivs = stats["ivs"],
                    evs = stats["evs"],
                    friendship = 70)
                teams[-1].pokemon.append(mon)
            teams[-1].ball_type = "Ultra Ball"
            teams[-1].balls = 10
            teams[-1].capture_threshold = 0.2
        for i in range(number_of_wild_pokemon):
            teams.append(honse_pokemon.Team(f"Wild Pokemon {i+1}", honse_data.WILD_COLOR))
            species = random.choice(TEST_SPECIES)
            stats = get_test_stats()
            mon = honse_pokemon.Pokemon(
                species = species,
                level = level,
                experience = 0,
                moves = random.sample(moves_list, 4),
                #moves = [honse_pokemon.MOVES["Helping Hand"], honse_pokemon.MOVES["Flare Blitz"], honse_pokemon.MOVES["Take Down"]],
                nature = stats["nature"],
                ivs = stats["ivs"],
                evs = {"HP": 0, "ATK": 0, "DEF": 0, "SPA": 0, "SPD": 0, "SPE": 0},
                friendship = 70)
            teams[-1].pokemon.append(mon)
            teams[-1].wild = True
        game = HonseGame(
            json_path = "map05.json",
            background = "map05.png",
            background_bw = "map05bw.png",
            music_folder = "wild",
            teams = teams,
            pygame_mode = True,
            video_mode = True,
            environment = honse_pokemon.Environments.INDOORS,
            encounter_type = honse_pokemon.EncounterTypes.WILD_ENCOUNTER,
            default_weather = honse_pokemon.Weather.CLEAR,
            daytime = True)
        game.main_loop()
    print(honse_data.BUG_FINDER.get_found_bugs())

def create_sounds():
    DIR = honse_data.get_absolute_path("sfx_wave")
    DIR = "sfx_wave"
    files = os.listdir(DIR)
    for file in files:
        no_file_extension = file.removesuffix(".mp3").removesuffix(".wav")
        file_path = os.path.join(DIR, file)
        if honse_data.PYGAME_ENABLED:
            pygame_sound = pygame.mixer.Sound(file_path)
        else:
            pygame_sound = None
        honse_data.SOUNDS.update({no_file_extension: [file_path, pygame_sound]})
    

# particle images works like this
# {"image": {}, "surface": {}}
# each dict contains key value pairs where the key is the name of the image and the value is the list of sprites that image has
# sometimes there will just be one sprite in the image but for animated particles it might have more
# if pygame is not enabled, the keys will exist for surface's dict but the values will all be empty lists
def add_to_particle_images(key, images):
    if type(images) != list:
        images = [images]
    if key not in honse_data.PARTICLE_IMAGES["image"]:
        honse_data.PARTICLE_IMAGES["image"][key] = []
        honse_data.PARTICLE_IMAGES["surface"][key] = []
    honse_data.PARTICLE_IMAGES["image"][key] += images
    if honse_data.PYGAME_ENABLED:
        for image in images:
            honse_data.PARTICLE_IMAGES["surface"][key].append(honse_data.image_to_surface(image))
 

def load_image_particles():
    path = os.path.join("vfx", "particles")
    path = honse_data.get_absolute_path(path)
    def get_image(filename):
        return Image.open(os.path.join(path, filename))
    # punch
    punch = get_image("punch.png")
    add_to_particle_images("punch", punch)
    for opacity in [80, 60, 40, 20]:
        transparent_punch = honse_data.alpha_change(punch.copy(), opacity)
        add_to_particle_images("punch", transparent_punch)
    # razor leaf
    razor_leaf = get_image("razor leaf.png")
    razor_leaf = honse_data.alpha_change(razor_leaf, 75)
    razor_leaf = honse_data.from_sprite_sheet(razor_leaf, 40)
    add_to_particle_images("razor leaf", razor_leaf)
    # thunderbolt
    thunderbolt = get_image("thunderbolt.png")
    thunderbolt = honse_data.from_sprite_sheet(thunderbolt, 60)
    add_to_particle_images("thunderbolt", thunderbolt)
    # ice
    ice = get_image("ice.png")
    new_size = (int(ice.size[0]*1.5), int(ice.size[1]*1.5))
    ice = ice.resize(new_size)
    ice = honse_data.alpha_change(ice, 40)
    ice = honse_data.from_sprite_sheet(ice, 120)
    add_to_particle_images("ice", ice)
    # protect
    barrier = get_image("barrier.png")
    protect = honse_data.hue_shift(barrier.copy(), 115)
    protect = honse_data.alpha_change(protect, 60)
    protect = honse_data.from_sprite_sheet(protect, 48)
    add_to_particle_images("protect", protect)

def load_status_icons():
    path = os.path.join("vfx", "status icons")
    path = honse_data.get_absolute_path(path)
    files = os.listdir(path)
    for file in files:
        no_file_extension = file.removesuffix(".png")
        file_path = os.path.join(path, file)
        image = Image.open(file_path)
        honse_data.STATUS_IMAGES["image"][no_file_extension] = image
        if honse_data.PYGAME_ENABLED:
            honse_data.STATUS_IMAGES["surface"][no_file_extension] = honse_data.image_to_surface(image)
        else:
            honse_data.STATUS_IMAGES["surface"][no_file_extension] = None

def setup_honse_game():
    if honse_data.PYGAME_ENABLED:
        pygame.display.set_mode()
    create_sounds()
    load_status_icons()
    load_image_particles()
    honse_pokemon.MOVES = honse_pokemon.create_moves()
    print(f"Number of moves: {len(honse_pokemon.MOVES)}")

if __name__ == "__main__":
    
    honse_data.PYGAME_ENABLED = False
    pygame.init()
    pygame.mixer.init()
    
    setup_honse_game()
    cProfile.run("test_game(1)", sort="cumtime", filename="res")
    p = pstats.Stats("res")
    p.strip_dirs()
    p.sort_stats("cumulative").print_stats(40)
    if honse_data.PYGAME_ENABLED:
        pygame.quit()


