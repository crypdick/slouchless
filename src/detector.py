from vllm import LLM, SamplingParams
from PIL import Image
from src.settings import settings


class SlouchDetector:
    def __init__(self):
        self.model_name = settings.MODEL_NAME

        print(f"Initializing vLLM with model: {self.model_name}")
        print(f"GPU Utilization Limit: {settings.GPU_MEMORY_UTILIZATION}")
        print(f"Quantization: {settings.QUANTIZATION}")
        print(f"Enforce Eager Mode: {settings.ENFORCE_EAGER}")

        # Initialize vLLM
        self.llm = LLM(
            model=self.model_name,
            trust_remote_code=True,
            gpu_memory_utilization=settings.GPU_MEMORY_UTILIZATION,
            quantization=settings.QUANTIZATION,
            enforce_eager=settings.ENFORCE_EAGER,
            max_num_seqs=settings.MAX_NUM_SEQS,
            max_model_len=2048,
        )
        self.sampling_params = SamplingParams(
            temperature=settings.TEMPERATURE, max_tokens=settings.MAX_TOKENS
        )

    def is_slouching(self, image: Image.Image) -> bool:
        # Prompt format for LLaVA
        prompt = settings.PROMPT

        inputs = [{"prompt": prompt, "multi_modal_data": {"image": image}}]

        # vLLM doesn't expose `use_fast` directly in `generate`,
        # it is usually handled during tokenizer/processor load.
        # But we can try to pass it if we were loading manually.
        # For vLLM, `trust_remote_code=True` handles most custom code needs.

        outputs = self.llm.generate(
            inputs, sampling_params=self.sampling_params, use_tqdm=False
        )
        generated_text = outputs[0].outputs[0].text.strip().lower()
        print(f"VLM Output: {generated_text}")

        # Check for positive response
        # Clean up punctuation
        cleaned_text = generated_text.strip(".").strip()
        return cleaned_text == "yes"
