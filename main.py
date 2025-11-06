import os
import random
import time
from collections import deque
from enum import Enum
from pathlib import Path
from typing import Optional, Annotated

import pygame
from pgzero.ptext import getsurf as pgz_text
from pydantic import Field, BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict, CliApp
from watchfiles import watch, Change


# Configuration
ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".gif"]

class FillType(Enum):
    BLACK = "BLACK"
    WHITE = "WHITE"
    TOP_PIXEL = "TOP_PIXEL"
    SIDE_PIXEL = "SIDE_PIXEL"
    CLOSEST_BW = "CLOSEST_BW"

class SlideshowMode(Enum):
    SEQUENTIAL = "SEQUENTIAL"
    RANDOM = "RANDOM"

class Validators:
    @staticmethod
    def validate_image_directory(v):
        if not os.path.isdir(v):
            raise ValueError("Image directory does not exist")
        return v

    @staticmethod
    def to_upper(v):
        if isinstance(v, str):
            return v.upper()
        return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', env_prefix="PYFRAME_")
    image_directory: Annotated[str, BeforeValidator(Validators.validate_image_directory)] = Field("/path/to/Pictures")
    fill_type: Annotated[FillType, BeforeValidator(Validators.to_upper)] = Field(FillType.CLOSEST_BW)
    slideshow_mode: Annotated[SlideshowMode, BeforeValidator(Validators.to_upper)] = Field(SlideshowMode.RANDOM)
    transition_duration: Annotated[float, BeforeValidator(float)] = Field(2)
    slideshow_delay: Annotated[float, BeforeValidator(float)] = Field(10)


class PhotoFrame:
    def __init__(self, settings: Optional[Settings] = None):
        # Initialize pygame
        pygame.init()
        pygame.mouse.set_visible(False)  # Hide the mouse cursor

        # Get display info and set up the screen
        display_info = pygame.display.Info()
        self.screen_width = display_info.current_w
        self.screen_height = display_info.current_h
        print(f"Display resolution: {self.screen_width}x{self.screen_height}")

        # Set the display fullscreen
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("Photo Frame")

        self.font = pygame.font.Font(None, 36)

        # Initialize variables
        self.settings = settings

        self.running = True
        self.images = []
        self.current_image_index = 0
        self.next_image_index = 0
        self.current_image: Optional[pygame.Surface] = None
        self.next_image_surface: Optional[pygame.Surface] = None
        self.last_change_time = time.time()
        self.transition_start_time = 0
        self.is_transitioning = False
        self.paused = False
        self.history = deque(maxlen=100)
        self.file_timeout = 0
        self.file_watcher = watch(self.settings.image_directory, yield_on_timeout=True, rust_timeout=10)
        # Load images from the directory
        self.load_images()

        # Load initial image
        if self.images:
            self.current_image = self.load_current_image()

    def load_images(self):
        """Find all image files in the specified directory"""
        try:
            image_dir = Path(self.settings.image_directory)
            if not image_dir.exists():
                print(f"Error: Directory {self.settings.image_directory} not found.")
                return

            # Get all files with allowed extensions
            self.images = [
                str(f)
                for f in image_dir.rglob("*")
                if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
            ]
            print(f"Found {len(self.images)} images in {self.settings.image_directory}:")
            if self.settings.slideshow_mode == SlideshowMode.RANDOM:
                random.shuffle(self.images)
            if len(self.images) == 0:
                print("No images found! Please check the directory and file types.")
        except Exception as e:
            print(f"Error loading images: {e}")

    def load_current_image(self, idx: Optional[int] = None) -> pygame.Surface:
        """Load and scale the current image"""
        if not self.images:
            raise ValueError("No images found")

        try:
            image_path = self.images[idx or self.current_image_index]

            print(f"Loading image: {image_path}")

            # Load the image and get its dimensions
            img = pygame.image.load(image_path)
            img_width, img_height = img.get_size()

            # Calculate aspect ratio
            img_aspect = img_width / img_height
            screen_aspect = self.screen_width / self.screen_height

            # Scale the image to fit the screen while maintaining the aspect ratio
            if img_aspect > screen_aspect:  # Image is wider
                new_width = self.screen_width
                new_height = int(new_width / img_aspect)
            else:  # Image is taller
                new_height = self.screen_height
                new_width = int(new_height * img_aspect)

            # Scale image
            scaled_img = pygame.transform.smoothscale(img, (new_width, new_height))

            # Calculate position to center the image
            pos_x = (self.screen_width - new_width) // 2
            pos_y = (self.screen_height - new_height) // 2

            # Create the surface for the full screen with a black background
            full_surface = pygame.Surface((self.screen_width, self.screen_height))

            if self.settings.fill_type == FillType.BLACK:
                full_surface.fill((0, 0, 0))
            elif self.settings.fill_type == FillType.WHITE:
                full_surface.fill((255, 255, 255))
            elif self.settings.fill_type == FillType.TOP_PIXEL:
                full_surface.fill(scaled_img.get_at((0, 0)))
            elif self.settings.fill_type == FillType.SIDE_PIXEL:
                for i in range(scaled_img.get_height()):
                    low_line = scaled_img.get_at((0, i))
                    full_surface.fill(low_line, (0, i, self.screen_width//2, 1))
                    high_line = scaled_img.get_at((scaled_img.get_width() - 1, i))
                    full_surface.fill(
                        high_line,
                        (self.screen_width // 2, i, self.screen_width // 2, 1),
                    )
            elif self.settings.fill_type == FillType.CLOSEST_BW:
                pixel = scaled_img.get_at((0, 0))
                avg = pixel[0] + pixel[1] + pixel[2] / 3
                if avg < 128:
                    full_surface.fill((0, 0, 0))
                else:
                    full_surface.fill((255, 255, 255))

            # Blit the scaled image onto the center of the black surface
            full_surface.blit(scaled_img, (pos_x, pos_y))

            return full_surface
        except IndexError:
            print(f"Image index {idx or self.current_image_index} out of range. Resetting to 0.")
            self.current_image_index = 0
            return self.load_current_image()

        except Exception as e:
            print(f"Error loading image index {idx or self.current_image_index}: {self.images[idx or self.current_image_index]}: {e}")
            # Create a blank image with an error message
            error_image = pygame.Surface((self.screen_width, self.screen_height))
            error_image.fill((0, 0, 0))
            text = self.font.render(
                f"Error loading image: {os.path.basename(self.images[idx or self.current_image_index])}",
                True,
                (255, 0, 0),
            )
            error_image.blit(
                text,
                (
                    self.screen_width // 2 - text.get_width() // 2,
                    self.screen_height // 2 - text.get_height() // 2,
                ),
            )
            return error_image

    def start_transition_to(self, index):
        """Start transition to a new image"""
        if index == self.current_image_index or not self.images:
            return

        # Save the current image for transition
        self.next_image_index = index

        # Load the next image
        self.next_image_surface = self.load_current_image(self.next_image_index)

        # Start transition
        self.transition_start_time = time.time()
        self.is_transitioning = True

    def update_transition(self):
        """Update the transition effect"""
        if not self.is_transitioning:
            return

        # Calculate transition progress (0.0 to 1.0)
        elapsed = time.time() - self.transition_start_time
        progress = min(elapsed / self.settings.transition_duration, 1.0)

        if progress >= 1.0:
            # Transition complete
            self.current_image_index = self.next_image_index
            self.current_image = self.next_image_surface
            self.next_image_surface = None
            self.is_transitioning = False
            return

        # Create a blended image for the transition
        temp_surface = self.current_image.copy()
        temp_surface.set_alpha(int(255 * (1 - progress)))

        # Draw the next image and overlay the fading current image
        self.screen.blit(self.next_image_surface, (0, 0))
        self.screen.blit(temp_surface, (0, 0))

    def next_image(self):
        """Switch to the next image"""
        self.history.append(self.images[self.current_image_index])
        if not self.images:
            return
        if self.settings.slideshow_mode == SlideshowMode.RANDOM:
            next_index = self.current_image_index + 1
            if next_index >= len(self.images):
                random.shuffle(self.images)
                next_index = 0
        else:
            next_index = (self.current_image_index + 1) % len(self.images)
        self.start_transition_to(next_index)
        self.last_change_time = time.time()

    def previous_image(self):
        """Switch to the previous image"""
        if not self.images:
            return
        if len(self.history) > 0:
            self.start_transition_to(self.images.index(self.history.pop()))
        self.last_change_time = time.time()

    def random_image(self):
        """Switch to a random image"""
        if len(self.images) <= 1:
            return
        next_index = random.randint(0, len(self.images) - 1)
        while next_index == self.current_image_index:
            next_index = random.randint(0, len(self.images) - 1)
        self.start_transition_to(next_index)
        self.last_change_time = time.time()

    def toggle_pause(self):
        """Toggle slideshow pause state"""
        self.paused = not self.paused
        if self.paused:
            print("Slideshow paused")
        else:
            print("Slideshow resumed")
            self.last_change_time = time.time()  # Reset timer when unpaused

    def handle_events(self):
        """Handle user input events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                # Keyboard controls
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_RIGHT or event.key == pygame.K_DOWN:
                    self.next_image()
                elif event.key == pygame.K_LEFT or event.key == pygame.K_UP:
                    self.previous_image()
                elif event.key == pygame.K_SPACE:
                    self.toggle_pause()
                elif event.key == pygame.K_r:
                    self.random_image()
                elif event.key == pygame.K_f:
                    # Toggle fullscreen
                    pygame.display.toggle_fullscreen()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Mouse controls
                print(f"Mouse: {event.pos}")
                if event.button == 1:  # Left click
                    x = event.pos[0]
                    if x < self.screen_width // 3:
                        self.previous_image()
                    elif x > (self.screen_width * 2) // 3:
                        self.next_image()
                    else:
                        self.toggle_pause()
        self.file_timeout -= 1
        if self.file_timeout < 0:
            self.file_timeout = 300
            while changes:=next(self.file_watcher):
                for action, file_path  in changes:
                    match action:
                        case Change.added:
                            tmp_path = Path(file_path)
                            if tmp_path.is_file():
                                if tmp_path.suffix in ALLOWED_EXTENSIONS:
                                    self.images.append(file_path)
                                    print(f"Image added: {tmp_path}")
                        case Change.deleted:
                            self.images.remove(file_path)
                            print(f"Image removed: {file_path}")
                        case _:
                            pass

    def update(self):
        """Update the display based on time and transitions"""
        current_time = time.time()

        # Check if it's time to change images automatically (if not paused)
        if (
            not self.paused
            and not self.is_transitioning
            and current_time - self.last_change_time > self.settings.slideshow_delay
        ):
            self.next_image()


        # Update transition if in progress
        if self.is_transitioning:
            self.update_transition()
        else:
            # Just draw the current image
            self.screen.blit(self.current_image, (0, 0))
            if self.paused:
                text = self.font.render(
                    f"=",
                    True,
                    (255, 0, 0),
                )
                text = pygame.transform.rotate(text, 90)
                self.screen.blit(text, (10, 10))
                text = pgz_text(f"{self.images[self.current_image_index].replace(self.settings.image_directory, '')}", owidth=1, ocolor="black", color="white", fontsize=36)
                self.screen.blit(text, (self.screen_width//2 - text.get_width()//2 , self.screen_height - text.get_height() - 10))
        pygame.display.flip()

    def run(self):
        """Main program loop"""
        # First draw
        if self.current_image:
            self.screen.blit(self.current_image, (0, 0))
            pygame.display.flip()

        print("Photo Frame started. Controls:")
        print("  - Left/Right arrows or mouse clicks: Previous/Next image")
        print("  - Space or middle click: Pause/Resume slideshow")
        print("  - R: Random image")
        print("  - ESC: Quit")

        # Main loop
        clock = pygame.time.Clock()
        # try:
        while self.running:
            self.handle_events()
            self.update()
            clock.tick(30)  # Limit to 30 FPS to save resources
        # except Exception as e:
        #     print(f"Error in main loop: {e}")
        # finally:
        #     pygame.quit()
        #     print("Photo Frame stopped")


if __name__ == "__main__":
    # Check if we're in an X environment
    if not os.environ.get('DISPLAY'):
        print("No X display found. Trying to set DISPLAY=:0")
        os.environ['DISPLAY'] = ':0'

    # Create and run the photo frame
    try:
        config = CliApp.run(Settings)
    except Exception as err:
        print(f"Error loading settings: {err}")
        exit(1)
    print(config.model_dump())
    photo_frame = PhotoFrame(config)
    photo_frame.run()