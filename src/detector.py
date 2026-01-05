import base64
import io
from typing import Literal, TypedDict, Protocol

from PIL import Image
from src.settings import settings
from src.settings import format_settings_for_log
from src.debug_images import DebugFrameWriter
from src.logging_setup import log


def _parse_response(text: str) -> dict | None:
    """
    Parse model response into structured format.

    Returns:
      - {"type": "yes", "explanation": <str>} if response starts with Yes
      - {"type": "no", "explanation": <str>} if response starts with No
      - {"type": "error", "explanation": <str>} if response starts with Error:
      - None if unparseable
    """
    cleaned = text.strip()
    if not cleaned:
        return None

    lowered = cleaned.lower()
    if lowered.startswith("error:"):
        msg = cleaned.split(":", 1)[1].strip()
        return {"type": "error", "explanation": msg or "unknown error"}

    # Accept trailing explanation, but first token must be Yes/No.
    first = lowered.split()[0].strip().strip(".,!?:;\"'()[]{}")
    if first == "yes":
        # Extract explanation after "Yes" - look for comma or just take rest
        rest = cleaned[3:].strip()  # Skip "Yes"
        if rest.startswith(","):
            rest = rest[1:].strip()
        elif rest.startswith("-"):
            rest = rest[1:].strip()
        return {"type": "yes", "explanation": rest}
    if first == "no":
        rest = cleaned[2:].strip()  # Skip "No"
        if rest.startswith(","):
            rest = rest[1:].strip()
        elif rest.startswith("-"):
            rest = rest[1:].strip()
        return {"type": "no", "explanation": rest}
    return None


class AnalysisResult(TypedDict):
    kind: Literal["good", "bad", "error"]
    slouching: bool | None
    message: str
    raw_output: str


def _analysis_result_from_parsed(
    parsed: dict | None, raw_output: str
) -> AnalysisResult:
    if parsed is None:
        return {
            "kind": "error",
            "slouching": None,
            "message": "Unparseable model output",
            "raw_output": raw_output,
        }

    if parsed.get("type") == "error":
        return {
            "kind": "error",
            "slouching": None,
            "message": str(parsed.get("explanation") or "unknown error"),
            "raw_output": raw_output,
        }

    if parsed.get("type") == "yes":
        explanation = str(parsed.get("explanation") or "").strip()
        return {
            "kind": "bad",
            "slouching": True,
            "message": explanation if explanation else "fix your posture!",
            "raw_output": raw_output,
        }

    if parsed.get("type") == "no":
        return {
            "kind": "good",
            "slouching": False,
            "message": "good posture!",
            "raw_output": raw_output,
        }

    return {
        "kind": "error",
        "slouching": None,
        "message": "Unparseable model output",
        "raw_output": raw_output,
    }


class DetectorBackend(Protocol):
    """Protocol for slouch detection backends."""

    def analyze(
        self,
        image: Image.Image,
        *,
        frame_id: str | None = None,
        frame_path: str | None = None,
        debug_writer: DebugFrameWriter | None = None,
    ) -> AnalysisResult: ...


class VLLMDetector:
    def __init__(self):
        from vllm import LLM, SamplingParams

        self.model_name = settings.model_name

        log.info(f"Initializing vLLM with model: {self.model_name}")
        log.debug(f"Detector settings:\n{format_settings_for_log(settings)}")

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
            log.debug("vLLM LLM object created successfully.")
        except Exception as e:
            log.exception(f"CRITICAL ERROR during vLLM init: {e}")
            raise

        self.sampling_params = SamplingParams(
            temperature=settings.temperature, max_tokens=settings.max_tokens
        )

    def analyze(
        self,
        image: Image.Image,
        *,
        frame_id: str | None = None,
        frame_path: str | None = None,
        debug_writer: DebugFrameWriter | None = None,
    ) -> AnalysisResult:
        """
        Structured inference result for UI feedback.
        """
        # Format prompt for vLLM with USER/ASSISTANT markers
        formatted_prompt = f"USER: <image>\n{settings.prompt}\nASSISTANT:"
        inputs = [{"prompt": formatted_prompt, "multi_modal_data": {"image": image}}]

        outputs = self.llm.generate(
            inputs, sampling_params=self.sampling_params, use_tqdm=False
        )
        if not outputs or not getattr(outputs[0], "outputs", None):
            raise RuntimeError(f"vLLM returned no outputs for frame_id={frame_id}")
        if not outputs[0].outputs or not getattr(outputs[0].outputs[0], "text", None):
            raise RuntimeError(f"vLLM returned empty text for frame_id={frame_id}")

        generated_text = outputs[0].outputs[0].text.strip()
        log.debug(f"VLM Output: {generated_text.strip()}")

        parsed = _parse_response(generated_text)
        if debug_writer is not None:
            debug_writer.log(
                {
                    "event": "vlm_inference",
                    "frame_id": frame_id,
                    "frame_path": frame_path,
                    "model": self.model_name,
                    "prompt": formatted_prompt,
                    "raw_output": generated_text,
                    "parsed": parsed,
                }
            )
        return _analysis_result_from_parsed(parsed, generated_text)


class OpenAIDetector:
    def __init__(self):
        from openai import OpenAI

        self.model_name = settings.openai_model
        api_key = settings.openai_api_key.get_secret_value()

        if not api_key:
            raise ValueError(
                "OpenAI API key not found. Please set OPENAI_API_KEY in your .env file."
            )

        log.info(f"Initializing OpenAI detector with model: {self.model_name}")
        log.debug(f"Detector settings:\n{format_settings_for_log(settings)}")

        self.client = OpenAI(api_key=api_key)

    @staticmethod
    def _encode_image(image: Image.Image) -> str:
        """Encode PIL Image to base64 string."""
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def analyze(
        self,
        image: Image.Image,
        *,
        frame_id: str | None = None,
        frame_path: str | None = None,
        debug_writer: DebugFrameWriter | None = None,
    ) -> AnalysisResult:
        """
        Structured inference result for UI feedback using OpenAI Vision API.
        """
        prompt = settings.prompt
        base64_image = self._encode_image(image)

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=settings.max_tokens,
                temperature=settings.temperature,
            )

            generated_text = response.choices[0].message.content.strip()
            log.debug(f"OpenAI Output: {generated_text.strip()}")

        except Exception as e:
            log.exception(f"Error calling OpenAI API: {e}")
            return {
                "kind": "error",
                "slouching": None,
                "message": f"API error: {str(e)}",
                "raw_output": "",
            }

        parsed = _parse_response(generated_text)
        if debug_writer is not None:
            debug_writer.log(
                {
                    "event": "openai_inference",
                    "frame_id": frame_id,
                    "frame_path": frame_path,
                    "model": self.model_name,
                    "prompt": prompt,
                    "raw_output": generated_text,
                    "parsed": parsed,
                }
            )
        return _analysis_result_from_parsed(parsed, generated_text)


class SlouchDetector:
    """
    Main detector interface that delegates to the configured backend.
    """

    def __init__(self):
        if settings.detector_type == "openai":
            self.backend: DetectorBackend = OpenAIDetector()
        elif settings.detector_type == "vllm":
            self.backend = VLLMDetector()
        else:
            raise ValueError(f"Unknown detector type: {settings.detector_type}")

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
        return result["slouching"] is True

    def analyze(
        self,
        image: Image.Image,
        *,
        frame_id: str | None = None,
        frame_path: str | None = None,
        debug_writer: DebugFrameWriter | None = None,
    ) -> AnalysisResult:
        """
        Structured inference result for UI feedback.
        """
        return self.backend.analyze(
            image,
            frame_id=frame_id,
            frame_path=frame_path,
            debug_writer=debug_writer,
        )
