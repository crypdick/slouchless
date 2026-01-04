import os


class Settings:
    # Camera Settings
    CAMERA_DEVICE_ID = int(os.getenv("SLOUCHLESS_CAMERA_ID", 0))
    CAMERA_RESIZE_TO = (640, 480)  # (width, height)

    # VLM / Detector Settings
    # Use a quantized model to save VRAM.
    MODEL_NAME = os.getenv("SLOUCHLESS_MODEL", "ybelkada/llava-1.5-7b-hf-awq")

    # GPU Memory Utilization (0.0 to 1.0).
    # With AWQ, we need much less memory.
    # Bump to 0.8 to fit KV cache.
    GPU_MEMORY_UTILIZATION = float(os.getenv("SLOUCHLESS_GPU_UTIL", "0.8"))

    # Quantization: Set to "awq_marlin" for faster inference with compatible models (like ybelkada/llava-1.5-7b-hf-awq).
    QUANTIZATION = os.getenv("SLOUCHLESS_QUANTIZATION", "awq_marlin")

    # Inference Optimization
    MAX_NUM_SEQS = 1
    ENFORCE_EAGER = True

    MAX_TOKENS = 10
    TEMPERATURE = 0.0

    # Prompt
    PROMPT = "USER: <image>\nIs the person in this image slouching? Answer strictly with 'Yes' or 'No'.\nASSISTANT:"

    # Application Settings
    CHECK_INTERVAL = 30  # seconds

    # UI
    POPUP_THUMBNAIL_SIZE = (600, 600)


settings = Settings()
