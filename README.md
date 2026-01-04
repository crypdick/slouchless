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

You can configure the application by modifying `src/settings.py` or setting environment variables:

| Variable | Description |
|----------|-------------|
| `SLOUCHLESS_CAMERA_ID` | Webcam Device ID |
| `SLOUCHLESS_MODEL` | HuggingFace Model ID |
| `SLOUCHLESS_GPU_UTIL` | GPU Memory Utilization (0.0-1.0) |
| `SLOUCHLESS_QUANTIZATION` | Quantization method|

