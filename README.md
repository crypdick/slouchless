# Slouchless

A Python-based background application that uses a webcam and local vision-language model (VLM) .to detect slouching, controllable via a system tray icon.


## Requirements
- Webcam
- NVIDIA GPU with sufficient VRAM for your chosen VLM
- `uv` package manager.

## Installation

1. Clone the repository.
2. Install dependencies:
   ```bash
   uv sync
   ```

## Usage

Run the application:
```bash
uv run --active main.py
```

## Configuration

Configuration is managed via `pydantic-settings` (`src/settings.py`). You can set environment variables (prefixed with `SLOUCHLESS_`) and/or create a `.env` file in the project root.

| Variable | Description |
|----------|-------------|
| `SLOUCHLESS_CAMERA_DEVICE_ID` | Webcam device index (OpenCV). If unset, Slouchless auto-detects **only if exactly one** camera is found. |
| `SLOUCHLESS_CAMERA_NAME` | Webcam name substring (Linux `/sys/class/video4linux/.../name`) |
| `SLOUCHLESS_CAMERA_RESIZE_TO` | Resize, e.g. `640x480` (or JSON like `[640, 480]`) |
| `SLOUCHLESS_MODEL_NAME` | HuggingFace model ID |
| `SLOUCHLESS_GPU_MEMORY_UTILIZATION` | GPU memory utilization (0.0-1.0) |
| `SLOUCHLESS_QUANTIZATION` | Quantization method |
| `SLOUCHLESS_CHECK_INTERVAL_SECONDS` | Seconds between checks |
| `SLOUCHLESS_POPUP_BACKEND` | `notify` or `tk` |

