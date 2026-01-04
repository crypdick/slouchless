import os


class Settings:
    # Camera Settings
    # Prefer selecting by human-friendly name (matches /sys/class/video4linux/video*/name).
    # Example:
    #   export SLOUCHLESS_CAMERA_NAME="Logitech BRIO"
    CAMERA_NAME = os.getenv("SLOUCHLESS_CAMERA_NAME", "").strip()
    # Back-compat fallback only (discouraged): numeric OpenCV device id.
    CAMERA_DEVICE_ID = int(os.getenv("SLOUCHLESS_CAMERA_ID", 0))
    CAMERA_RESIZE_TO = (640, 480)  # (width, height)

    # VLM / Detector Settings
    # Use a quantized model to save VRAM.
    MODEL_NAME = os.getenv("SLOUCHLESS_MODEL", "ybelkada/llava-1.5-7b-hf-awq")

    # GPU Memory Utilization (0.0 to 1.0).
    # With AWQ, we need much less memory.
    # Bump to 0.7 to fit KV cache.
    GPU_MEMORY_UTILIZATION = float(os.getenv("SLOUCHLESS_GPU_UTIL", "0.7"))

    # Quantization: Set to "awq_marlin" for faster inference with compatible models (like ybelkada/llava-1.5-7b-hf-awq).
    QUANTIZATION = os.getenv("SLOUCHLESS_QUANTIZATION", "awq_marlin")

    # Inference Optimization
    MAX_NUM_SEQS = 1
    ENFORCE_EAGER = True

    # Backend
    # Use 'ray' or 'mp' (multiprocessing). Ray is more robust for some setups.
    DISTRIBUTED_EXECUTOR_BACKEND = "ray"
    MAX_TOKENS = 10
    TEMPERATURE = 0.0

    # Prompt
    PROMPT = (
        "USER: <image>\n"
        "Look at the person's posture. If they are slouching (rounded shoulders, "
        "forward head/neck, hunched/curved upper back), answer 'Yes'. If they are "
        "sitting/standing upright with a neutral spine, answer 'No'.\n"
        "If you cannot determine from the image, answer with 'Error: <short reason>'.\n"
        "Your response must start with exactly one of: Yes, No, or Error:.\n"
        "ASSISTANT:"
    )

    # Application Settings
    CHECK_INTERVAL = 30  # seconds

    # Debugging
    # Save recent frames to disk so you can inspect what the VLM actually saw.
    DEBUG_SAVE_FRAMES = os.getenv("SLOUCHLESS_DEBUG_SAVE_FRAMES", "1") == "1"
    DEBUG_CLEAR_FRAMES_ON_START = (
        os.getenv("SLOUCHLESS_DEBUG_CLEAR_ON_START", "1") == "1"
    )
    DEBUG_MAX_FRAMES = int(os.getenv("SLOUCHLESS_DEBUG_MAX_FRAMES", "20"))
    DEBUG_FRAMES_DIR = os.getenv("SLOUCHLESS_DEBUG_FRAMES_DIR", "debug_frames")

    # Camera capture quality/debugging
    # Some webcams buffer frames; grabbing a couple frames helps ensure we get the "latest" image.
    CAMERA_GRAB_FRAMES = int(os.getenv("SLOUCHLESS_CAMERA_GRAB_FRAMES", "2"))

    # UI
    POPUP_THUMBNAIL_SIZE = (600, 600)
    # Popup backend: on Linux, "notify" is much more reliable than Tk + multiprocessing under X11/Wayland.
    POPUP_BACKEND = os.getenv("SLOUCHLESS_POPUP_BACKEND", "notify").strip().lower()


settings = Settings()
