from vllm import LLM, SamplingParams
from PIL import Image
from src.settings import settings
from src.debug_images import DebugFrameWriter


class SlouchDetector:
    def __init__(self):
        self.model_name = settings.model_name

        print(f"DEBUG: Initializing vLLM with model: {self.model_name}")
        print(f"DEBUG: GPU Utilization Limit: {settings.gpu_memory_utilization}")
        print(f"DEBUG: Quantization: {settings.quantization}")
        print(f"DEBUG: Enforce Eager Mode: {settings.enforce_eager}")
        print(f"DEBUG: Distributed Backend: {settings.distributed_executor_backend}")

        # Initialize vLLM
        try:
            self.llm = LLM(
                model=self.model_name,
                trust_remote_code=True,
                gpu_memory_utilization=settings.gpu_memory_utilization,
                quantization=settings.quantization,
                enforce_eager=settings.enforce_eager,
                max_num_seqs=settings.max_num_seqs,
                max_model_len=2048,
                distributed_executor_backend=settings.distributed_executor_backend,
            )
            print("DEBUG: vLLM LLM object created successfully.")
        except Exception as e:
            print(f"CRITICAL ERROR during vLLM init: {e}")
            raise e

        self.sampling_params = SamplingParams(
            temperature=settings.temperature, max_tokens=settings.max_tokens
        )

    @staticmethod
    def _parse_yes_no_or_error(text: str) -> bool | tuple[str, str] | None:
        """
        Returns:
          - True/False if response starts with Yes/No (extra text allowed)
          - ("error", <message>) if response starts with Error: ...
          - None if unparseable
        """
        cleaned = text.strip()
        if not cleaned:
            return None

        lowered = cleaned.lower()
        if lowered.startswith("error:"):
            msg = cleaned.split(":", 1)[1].strip()
            return ("error", msg or "unknown error")

        # Accept trailing explanation, but first token must be Yes/No.
        first = lowered.split()[0].strip().strip(".,!?:;\"'()[]{}")
        if first == "yes":
            return True
        if first == "no":
            return False
        return None

    def is_slouching(
        self,
        image: Image.Image,
        *,
        frame_id: str | None = None,
        frame_path: str | None = None,
        debug_writer: DebugFrameWriter | None = None,
    ) -> bool:
        result = self.analyze(
            image,
            frame_id=frame_id,
            frame_path=frame_path,
            debug_writer=debug_writer,
        )
        if result["kind"] == "error":
            raise RuntimeError(
                f"{result['message']} (frame_id={frame_id} frame_path={frame_path})"
            )
        return bool(result["slouching"])

    def analyze(
        self,
        image: Image.Image,
        *,
        frame_id: str | None = None,
        frame_path: str | None = None,
        debug_writer: DebugFrameWriter | None = None,
    ) -> dict[str, object]:
        """
        Structured inference result for UI feedback.

        Returns dict with:
          - kind: "good" | "bad" | "error"
          - slouching: bool | None
          - message: str (human-friendly)
          - raw_output: str
        """
        prompt = settings.prompt
        inputs = [{"prompt": prompt, "multi_modal_data": {"image": image}}]

        outputs = self.llm.generate(
            inputs, sampling_params=self.sampling_params, use_tqdm=False
        )
        if not outputs or not getattr(outputs[0], "outputs", None):
            raise RuntimeError(f"vLLM returned no outputs for frame_id={frame_id}")
        if not outputs[0].outputs or not getattr(outputs[0].outputs[0], "text", None):
            raise RuntimeError(f"vLLM returned empty text for frame_id={frame_id}")

        generated_text = outputs[0].outputs[0].text.strip()
        print(f"VLM Output: {generated_text.strip().lower()}")

        parsed = self._parse_yes_no_or_error(generated_text)
        if debug_writer is not None:
            debug_writer.log(
                {
                    "event": "vlm_inference",
                    "frame_id": frame_id,
                    "frame_path": frame_path,
                    "model": self.model_name,
                    "prompt": prompt,
                    "raw_output": generated_text,
                    "parsed": parsed,
                }
            )

        if parsed is None:
            return {
                "kind": "error",
                "slouching": None,
                "message": "⚠️ Unparseable model output",
                "raw_output": generated_text,
            }
        if isinstance(parsed, tuple) and parsed[0] == "error":
            return {
                "kind": "error",
                "slouching": None,
                "message": f"⚠️ Model error: {parsed[1]}",
                "raw_output": generated_text,
            }

        slouching = bool(parsed)
        if slouching:
            return {
                "kind": "bad",
                "slouching": True,
                "message": "bad posture!",
                "raw_output": generated_text,
            }
        return {
            "kind": "good",
            "slouching": False,
            "message": "good posture",
            "raw_output": generated_text,
        }
