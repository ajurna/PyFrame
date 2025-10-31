# pyframe

A simple fullscreen photo-frame / slideshow application built with Pygame. It scans a directory recursively for images and displays them with smooth cross‑fade transitions, optional random/sequential modes, and on‑screen filename overlay when paused. Configuration is driven by environment variables (or a local .env file) or command line  via Pydantic Settings.


## Overview
- Fullscreen slideshow using Pygame
- Supports common image formats: .jpg, .jpeg, .png, .bmp, .gif
- Two slideshow modes: sequential or random
- Smooth cross‑fade transitions with configurable duration and delay
- Keyboard and mouse controls
- Configuration via environment variables with `PYFRAME_` prefix (reads from `.env` if present)
- Configuration via command line arguments


## Requirements
- Python 3.13+
- OS: Linux or Windows
  - Linux/X11: the app attempts to set `DISPLAY=:0` if no display variable is found (see main guard)
- Dependencies (managed via `pyproject.toml`):
  - pygame
  - pgzero (used for text rendering via `pgzero.ptext`)
  - pydantic-settings
- Optional/likely system packages for SDL (Pygame), depending on your OS (e.g., SDL2, image codecs). Refer to Pygame installation docs if you hit runtime import/display issues.

## Project Structure
```
pyframe/
├─ main.py             # Application entry point; settings, enums, PhotoFrame class, main loop
├─ pyproject.toml      # Project metadata and dependencies
├─ uv.lock             # Lock file for the `uv` package manager
└─ README.md           # This file
```


## Installation

### Using uv (recommended if you already use uv)
- Install uv if needed: https://docs.astral.sh/uv/ 
- From project root:
```
git clone https://github.com/ajurna/PyFrame.git
cd PyFrame
uv sync
```

## Running
From the project root:

- With uv:
```
uv run python main.py 
```

- With plain Python (after installing dependencies):
```
python main.py
```

The app starts in fullscreen, hides the mouse cursor, and prints basic controls to stdout.


## Running as a systemd service (like PicFrame)
You can run pyframe automatically on boot using systemd. 

Notes:
- On Linux/X11, if `DISPLAY` isn’t set, the app attempts to use `:0`. You can also set it explicitly in the unit file with `Environment=DISPLAY=:0`.


File: `/etc/systemd/system/pyframe.service`
```
[Unit]
Description=PyFrame on Pi
After=multi-user.target

[Service]
Type=idle

User=root
ExecStart=xinit /opt/PyFrame/.venv/bin/python /opt/PyFrame/main.py
Environment=PYFRAME_IMAGE_DIRECTORY=/path/to/images
WorkingDirectory=/opt/PyFrame
#Restart=always

[Install]
WantedBy=multi-user.target
```
Enable and start:
```
systemctl daemon-reload
systemctl enable --now pyframe.service
```

## Command-line arguments
This app uses Pydantic Settings' CLI integration via `CliApp.run(Settings)`. All settings can be provided as command-line options using kebab-case names derived from the fields in `Settings`.

- `--image-directory PATH` (required if not set via env or `.env`)
- `--fill-type {BLACK,WHITE,TOP_PIXEL,SIDE_PIXEL,CLOSEST_BW}`
- `--slideshow-mode {SEQUENTIAL,RANDOM}`
- `--transition-duration FLOAT` (seconds)
- `--slideshow-delay FLOAT` (seconds)

Precedence: command-line options > environment variables > values in `.env` > built-in defaults.

Show help:
```
uv run main.py --help
```

Examples:
```
# Using uv
uv run python main.py \
  --image-directory C:\\Users\\you\\Pictures \
  --fill-type CLOSEST_BW \
  --slideshow-mode RANDOM \
  --transition-duration 2 \
  --slideshow-delay 10

# Plain Python
python main.py \
  --image-directory /home/you/Pictures \
  --slideshow-mode SEQUENTIAL \
  --transition-duration 1.5 \
  --slideshow-delay 8
```

Notes:
- Enum values are effectively case-insensitive; they are upper-cased by a validator.
- If any value is invalid (e.g., directory missing, bad enum), the app prints a validation error and exits.


## Controls
- ESC: Quit
- Right/Down arrows: Next image
- Left/Up arrows: Previous image
- Space: Pause/Resume slideshow
- R: Jump to a random image
- F: Toggle fullscreen (Pygame feature)
- Mouse left click:
  - Left third of screen: Previous image
  - Right third of screen: Next image
  - Middle third: Pause/Resume

When paused, an overlay with the current image filename (relative to the configured directory) is shown at the bottom.


## Configuration
Configuration is done via environment variables with prefix `PYFRAME_`. A `.env` file in the project root is automatically loaded if present.

- `PYFRAME_IMAGE_DIRECTORY` (string, required): Directory to scan for images (recursively). Must exist.
- `PYFRAME_FILL_TYPE` (enum): How to fill background borders when aspect ratios differ. Accepted values (case‑insensitive):
  - `BLACK`
  - `WHITE`
  - `TOP_PIXEL`
  - `SIDE_PIXEL`
  - `CLOSEST_BW` (default)
- `PYFRAME_SLIDESHOW_MODE` (enum): `SEQUENTIAL` or `RANDOM` (default `RANDOM`).
- `PYFRAME_TRANSITION_DURATION` (float): Cross‑fade transition duration in seconds (default `2`).
- `PYFRAME_SLIDESHOW_DELAY` (float): Seconds to show each image before auto‑advancing (default `10`).

Example `.env`:
```
# .env
PYFRAME_IMAGE_DIRECTORY=C:\\Users\\you\\Pictures     # Windows example
# PYFRAME_IMAGE_DIRECTORY=/home/you/Pictures            # Linux/macOS example
PYFRAME_FILL_TYPE=CLOSEST_BW
PYFRAME_SLIDESHOW_MODE=RANDOM
PYFRAME_TRANSITION_DURATION=2
PYFRAME_SLIDESHOW_DELAY=10
```

Notes:
- Values are validated at startup. `image_directory` must exist. Enum values are case‑insensitive in practice because they are upper‑cased by a validator.
- If `DISPLAY` is not set on Linux, the program tries `DISPLAY=:0`.


## License
MIT License.


## Troubleshooting
- "Image directory does not exist": Ensure `PYFRAME_IMAGE_DIRECTORY` points to a valid directory.
- No images found: Supported extensions are `.jpg`, `.jpeg`, `.png`, `.bmp`, `.gif`. Verify files exist and extensions are correct (case‑insensitive).
- Pygame window/display issues:
  - On Linux, ensure an X server is available and `DISPLAY` is set (or accessible as `:0`).
  - On macOS, give Python permission to access the display in System Settings if prompted.
  - On Windows, run from a normal desktop session.


## Notes for Development
- Entry point: `main.py` (guarded by `if __name__ == "__main__":`)
- Settings are defined in `Settings` (Pydantic BaseSettings) in `main.py` and loaded via `CliApp.run(Settings)`. They can be passed to `PhotoFrame(Settings)`.
- The main loop runs at ~30 FPS and performs image transitions based on time and settings.
