import pygame
from os.path import join as pathjoin 
from random import randint, uniform, choice
from math import sin

pygame.init()

# General setup
debug_mode = False
WINDOW_WIDTH, WINDOW_HEIGHT = 600, 600
display_surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
display_rect = display_surface.get_rect()
pygame.display.set_caption("Space Shooters (debug mode)" if debug_mode else "Space Shooters")
running = True
clock = pygame.time.Clock()

# Game setup
def surface_prep(address: str) -> pygame.Surface:
    surface = pygame.image.load(address)
    return pygame.transform.smoothscale_by(surface, 0.5).convert_alpha()

meteors_hit = 0
player_lives = 3
font = pygame.font.Font(pathjoin("images", "Oxanium-Bold.ttf"), 40)

master_volume = 0.1
laser_sound = pygame.mixer.Sound(pathjoin("audio", "laser.wav"))
laser_sound.set_volume(master_volume)
explosion_sound = pygame.mixer.Sound(pathjoin("audio", "explosion.wav"))
explosion_sound.set_volume(master_volume)
damage_sound = pygame.mixer.Sound(pathjoin("audio", "damage.ogg"))
damage_sound.set_volume(master_volume)
game_music = pygame.mixer.Sound(pathjoin("audio", "game_music.wav"))
game_music.set_volume(0.5 * master_volume)
game_music.play(loops=-1) # Repeat forever

# Groups
all_sprites = pygame.sprite.Group()
background_layer = pygame.sprite.Group()
elements_layer = pygame.sprite.Group()
meteor_group = pygame.sprite.Group()
laser_group = pygame.sprite.Group()
player_group = pygame.sprite.Group()
ui_layer = pygame.sprite.Group()

# Sprites
class CooldownBar(pygame.sprite.Sprite):
    def __init__(self, groups, duration_ms):
        super().__init__(groups)
        self.image = pygame.Surface((100, 10), pygame.SRCALPHA) # Enable ALPHA values on the surface for transprency
        self.rect = self.image.get_frect(center=(WINDOW_WIDTH / 2, WINDOW_HEIGHT - 20))
        self.duration = self.time_left = duration_ms

    def update(self, *args, **kwargs):
        self.time_left -= kwargs.get('dt', 0) * 1000
        draw_rect = pygame.FRect(0, 0, 100 * self.time_left / self.duration, 10)
        draw_rect.center = (50, 5) 
        if self.time_left >= 0:
            self.image.fill((0, 0, 0, 0)) # Clear canvas
            pygame.draw.rect(self.image, pygame.Color(230, 140, 133), draw_rect, border_radius=10)
        else:
            self.kill()

class Player(pygame.sprite.Sprite): 
    player_surface = surface_prep(pathjoin("images", "player.png"))
    player_mask = pygame.mask.from_surface(player_surface)

    def __init__(self, groups):
        super().__init__(groups)
        self.image = Player.player_surface
        self.rect = self.image.get_frect(center=(WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2))
        self.direction = pygame.Vector2()
        self.speed = 300

        # shooting
        self.can_shoot = True
        self.shoot_cooldown_ms = 400
        self.last_shot_time = 0

        # mask
        self.mask = Player.player_mask

    def move(self, dt):
        keys = pygame.key.get_pressed()
        self.direction.x = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        self.direction.y = int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP])

        if self.direction: # (0, 0) = Falsey
            self.direction = self.direction.normalize()

        self.rect.center += self.direction * self.speed * dt
        self.rect.clamp_ip(display_rect) # Keeps the player within the display area

    def shoot(self):
        single_action_key = pygame.key.get_just_pressed()
        if single_action_key[pygame.K_SPACE] and self.can_shoot:
            Laser((all_sprites, elements_layer, laser_group), midbottom=self.rect.midtop)
            laser_sound.play()

            self.can_shoot = False
            self.last_shot_time = pygame.time.get_ticks()
            CooldownBar((all_sprites, ui_layer), self.shoot_cooldown_ms)

        if not self.can_shoot: # If can't shoot, check the timer
            current_time = pygame.time.get_ticks()
            if current_time - self.last_shot_time >= self.shoot_cooldown_ms:
                self.can_shoot = True

    def collide(self):
        meteor_collisions = pygame.sprite.spritecollide(
            self, meteor_group, dokill=True, collided=pygame.sprite.collide_mask)
        if meteor_collisions:
            global player_lives
            for meteor in meteor_collisions:
                AnimatedExplosion((all_sprites, elements_layer), meteor.rect.center)
            
            damage_sound.play()
            player_lives -= 1
            print(f"There are {player_lives} lives left for the player")

    def update(self, *args, **kwargs):
        self.move(kwargs.get('dt', 0))
        self.shoot()
        self.collide()

class Star(pygame.sprite.Sprite):
    original_surface = surface_prep(pathjoin("images", "star.png"))
    star_surfaces = {}

    @classmethod
    def pre_render_sizes(cls):
        # Flipping even <-> odd dimensions introduces jitter. Keep dimensions even.
        for scale in [round(0.8 + 0.01 * i, 2) for i in range(41)]:
            o_width, o_height = cls.original_surface.get_size()
            n_width = int(o_width * scale) // 2 * 2
            n_height = int(o_height * scale) // 2 * 2
            cls.star_surfaces[scale] = pygame.transform.smoothscale(cls.original_surface, (n_width, n_height))

    def __init__(self, groups):
        super().__init__(groups)
        self.pos = pygame.Vector2(
            randint(20, WINDOW_WIDTH - 20),
            randint(20, WINDOW_HEIGHT - 20)
        )
        self.image = Star.original_surface
        self.rect = self.image.get_frect(center=self.pos)
        self.scale = 1
        self.ticks = randint(0, 314) / 100 # Offset 0-1 sec

    def update(self, *args, **kwargs):
        dt = kwargs.get('dt', 0)
        self.ticks += dt
        # Period = PI sec => omega = 2 rad/s
        self.scale = round(1 + 0.2 * sin(2 * self.ticks), 2)
        # Setting center to previous rect.center introduces pixel jitter.
        self.image = Star.star_surfaces[self.scale]
        self.rect = self.image.get_frect(center=self.pos)  

class Meteor(pygame.sprite.Sprite):
    original_surface = surface_prep(pathjoin("images", "meteor.png"))
    meteor_surfaces = {}
    meteor_masks = {}

    @classmethod # Static class-level method
    def pre_render_rotations(cls):
        for angle in range(360):
            altered_surface = pygame.transform.rotozoom(cls.original_surface, angle=angle, scale=1)
            cls.meteor_surfaces[angle] = altered_surface
            cls.meteor_masks[angle] = pygame.mask.from_surface(altered_surface)

    def __init__(self, groups, midbottom):
        super().__init__(groups)
        self.image = Meteor.meteor_surfaces[0]
        self.rect = self.image.get_frect(midbottom=midbottom)
        self.direction = pygame.Vector2(uniform(-0.5, 0.5), 1).normalize()
        self.speed = randint(100, 200)
        self.rotation = 0
        self.degs_per_sec = ((self.speed * 2) - 40) * choice([-1, 1]) # 100 - 200 -> 160 - 360
        self.mask = Meteor.meteor_masks[0]
    
    def update(self, *args, **kwargs):
        dt = kwargs.get('dt', 0)
        self.rect.center += self.direction * self.speed * dt 

        # Rotate => Change the trio: Image, Rect, Mask.
        self.rotation += self.degs_per_sec * dt 
        self.rotation %= 360
        self.image = Meteor.meteor_surfaces[int(self.rotation)]
        self.rect = self.image.get_frect(center=self.rect.center)
        self.mask = Meteor.meteor_masks[int(self.rotation)]

        if self.rect.top >= WINDOW_HEIGHT:
            self.kill()

class Laser(pygame.sprite.Sprite):
    laser_surface = surface_prep(pathjoin("images", "laser.png"))
    laser_mask = pygame.mask.from_surface(laser_surface)

    def __init__(self, groups, midbottom):
        super().__init__(groups)
        self.image = Laser.laser_surface
        self.rect = self.image.get_frect(midbottom=midbottom) # Shot at the tip of the ship
        self.speed = 400
        self.mask = Laser.laser_mask

    def update(self, *args, **kwargs):
        global meteors_hit
        dt = kwargs.get('dt', 0)
        self.rect.bottom -= self.speed * dt
        meteor_collisions = pygame.sprite.spritecollide(self, meteor_group, dokill=True, 
                                                        collided=pygame.sprite.collide_mask)
        if meteor_collisions:
            meteors_hit += len(meteor_collisions)
            for meteor in meteor_collisions:
                AnimatedExplosion((all_sprites, elements_layer), center=meteor.rect.center)
            explosion_sound.play()
            self.kill()
        if self.rect.bottom <= 0:
            self.kill()

class AnimatedExplosion(pygame.sprite.Sprite):
    surfaces = []
    number_of_frames = 21

    @classmethod
    def import_surfaces(cls):
        cls.surfaces = [
            pygame.image.load(pathjoin("images", "explosion", f"{i}.png")).convert_alpha() for i in range(cls.number_of_frames)
        ]

    def __init__(self, groups, center):
        super().__init__(groups)
        self.frame_estimate = 0 # 0 -> 20
        self.center = center
        self.image = self.surfaces[0]
        self.rect = self.image.get_frect(center=center)

    def update(self, *args, **kwargs):
        dt = kwargs.get('dt', 0)
        self.frame_estimate += 40 * dt # 20 frames / 40 = 0.5s 
        if self.frame_estimate < self.number_of_frames:
            self.image = self.surfaces[int(self.frame_estimate)]
            self.rect = self.image.get_frect(center=self.center)
        else:
            self.kill()        



# Scene Building
for _ in range(30):
    Star((all_sprites, background_layer))
player = Player((all_sprites, elements_layer, player_group))
Meteor.pre_render_rotations()
Star.pre_render_sizes()
AnimatedExplosion.import_surfaces()

def display_score():
    score_color = pygame.Color(220, 220, 220)
    score = pygame.time.get_ticks() // 100 + meteors_hit * 10
    score_surface = font.render(str(score), antialias=True, color=score_color)
    score_rect = score_surface.get_frect(midbottom=(WINDOW_WIDTH / 2, WINDOW_HEIGHT - 50)) 
    display_surface.blit(score_surface, score_rect)
    score_border_rect = score_rect.copy().move(0, -7).inflate(20, 5)
    pygame.draw.rect(display_surface, score_color, score_border_rect, width=5, border_radius=10)

# Custom Events
meteor_event = pygame.event.custom_type()
pygame.time.set_timer(meteor_event, 500) 
debug_event = pygame.event.custom_type()
if debug_mode:
    pygame.time.set_timer(debug_event, 1000)

while running:
    # Event loop
    dt = clock.tick() / 1000 # delta time in seconds
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == debug_event:
            print(f"Fps: {clock.get_fps()}")
        elif event.type == meteor_event:
            # Variations in altitudes => Variations in time
            Meteor((all_sprites, elements_layer, meteor_group), 
                   midbottom=(randint(20, WINDOW_WIDTH - 20), randint(-100, 0)))

    # Updates
    all_sprites.update(dt=dt)

    # Game draw
    display_surface.fill("#3a2e3f") 
    background_layer.draw(display_surface)
    display_score()
    elements_layer.draw(display_surface)
    ui_layer.draw(display_surface)

    pygame.display.update()

pygame.quit()