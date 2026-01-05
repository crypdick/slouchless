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
| `SLOUCHLESS_POPUP_BACKEND` | `ffplay`, `notify`, or `auto` (default: `ffplay`). |
| `SLOUCHLESS_POPUP_MODE` | `feedback` or `live` (default: `feedback`). `feedback` shows a live preview **with model feedback overlay** until you close the window. |
| `SLOUCHLESS_POPUP_FEEDBACK_INTERVAL_MS` | For `SLOUCHLESS_POPUP_MODE=feedback`: inference cadence while the popup is open (default: `500`). |
| `SLOUCHLESS_POPUP_PREVIEW_FPS` | For `SLOUCHLESS_POPUP_MODE=feedback`: preview FPS pushed to the ffplay window (default: `15`). |
| `SLOUCHLESS_LOG_LEVEL` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`). |

## Popup live feedback (✅/🚨/⚠️)

Enable the feedback popup mode (live feed + LLM feedback overlay):

```bash
export SLOUCHLESS_POPUP_BACKEND=ffplay
export SLOUCHLESS_POPUP_MODE=feedback
export SLOUCHLESS_POPUP_FEEDBACK_INTERVAL_MS=500
```

Notes:
- `feedback` uses an ffplay window and streams an overlay-rendered video feed from Python.
- If you're running headless, use `SLOUCHLESS_POPUP_BACKEND=notify`.

