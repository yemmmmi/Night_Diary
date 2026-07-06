"""Fine-tuned model inference adapter for chat intent classification.

``FinetunedIntentLLM`` implements the ``LLMClient`` Protocol (same structural
interface as ``app.shared.llm.LLMClient``) so it can be directly injected into
``ChatIntentClassifier(llm=FinetunedIntentLLM(...))`` — replacing the HTTP
LLM client with a locally fine-tuned LoRA model, zero API cost.

The returned ``Message`` objects are structurally compatible with
``tests/eval/_http_llm.Message`` (same ``content`` / ``response_metadata`` /
``tool_calls`` fields) so ``message_text()`` and ``extract_token_usage()``
work transparently.

Device strategy::

    GPU available  → FP16, device_map="auto" (fast)
    GPU unavailable → FP32 on CPU (slow but functional)

Example::

    from training.finetune_intent.inference import FinetunedIntentLLM
    from app.domain.agents.chat_intent_classifier import ChatIntentClassifier

    llm = FinetunedIntentLLM(model_path="training/finetune_intent/outputs/final")
    classifier = ChatIntentClassifier(llm=llm, model="qwen2.5-1.5b-lora")

    # Async (production path)
    result = await classifier.classify("今天工作压力好大，感觉撑不住了")

    # Sync (eval path)
    result = classifier.classify_sync("今天工作压力好大，感觉撑不住了")
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Message (structurally compatible with tests/eval/_http_llm.Message) ──


@dataclass
class Message:
    """Minimal LLM response wrapper.

    Structurally compatible with ``tests/eval/_http_llm.Message`` so that
    :func:`app.shared.llm.message_text` (reads ``.content``) and
    :func:`app.domain.agents.state.extract_token_usage` (reads
    ``.response_metadata.token_usage``) work without modification.
    """

    content: str
    response_metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def usage_block(prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
    """Build a standard usage block for ``response_metadata``.

    Mirrors ``tests/eval/_http_llm.usage_block``.
    """
    return {
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_cache_miss_tokens": prompt_tokens,
        }
    }


# ── Fallback JSON (used when generation fails) ──────────────────────

_FALLBACK_JSON = json.dumps(
    {
        "intent_category": "casual_chat",
        "confidence": 0.5,
        "need_retrieval": False,
        "need_tools": [],
        "need_entity_query": False,
    },
    ensure_ascii=False,
)


class FinetunedIntentLLM:
    """Local fine-tuned LoRA model as an ``LLMClient``.

    Loads the base model + LoRA adapter weights, then generates JSON intent
    classifications in response to the ``_CHAT_INTENT_PROMPT`` prompt.

    Args:
        model_path: Path to the saved LoRA adapter directory (contains
            ``adapter_model.safetensors`` + ``adapter_config.json``).  The base
            model name is read from the adapter config.
        base_model: Override the base model name (e.g.
            ``"Qwen/Qwen2.5-1.5B"``).  If not provided, reads from the adapter
            config or defaults to ``"Qwen/Qwen2.5-1.5B"``.
        max_new_tokens: Maximum tokens to generate (default 128).
        device: ``"auto"``, ``"cuda"``, or ``"cpu"``.  Defaults to ``"auto"``
            (uses CUDA if available, falls back to CPU).

    Note:
        Model loading (``torch``, ``transformers``, ``peft``) is deferred to
        ``__init__`` so the module can be imported without those deps installed
        (useful for ``--help`` and static analysis).
    """

    #: Default base model if adapter config doesn't specify one.
    _DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-1.5B"

    def __init__(
        self,
        model_path: str,
        *,
        base_model: str | None = None,
        max_new_tokens: int = 128,
        device: str = "auto",
    ) -> None:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._max_new_tokens = max_new_tokens
        self._model_path = model_path

        # ── Resolve device ──
        if device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = device
        self._is_cpu = self._device == "cpu"

        # ── Resolve base model name ──
        if base_model is None:
            base_model = self._read_base_model_from_config(model_path)
        self._base_model = base_model

        logger.info(
            "Loading fine-tuned model: base=%s, adapter=%s, device=%s, dtype=%s",
            self._base_model,
            model_path,
            self._device,
            "fp32" if self._is_cpu else "fp16",
        )

        # ── Load tokenizer ──
        self._tokenizer = AutoTokenizer.from_pretrained(
            self._base_model, trust_remote_code=True
        )
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        # ── Load base model ──
        dtype = torch.float32 if self._is_cpu else torch.float16
        if self._is_cpu:
            self._model = AutoModelForCausalLM.from_pretrained(
                self._base_model,
                trust_remote_code=True,
                torch_dtype=dtype,
            )
        else:
            self._model = AutoModelForCausalLM.from_pretrained(
                self._base_model,
                trust_remote_code=True,
                torch_dtype=dtype,
                device_map="auto",
            )

        # ── Load LoRA adapter ──
        self._model = PeftModel.from_pretrained(self._model, model_path)
        self._model.eval()

        logger.info("Model loaded successfully (device=%s)", self._device)

    # ── Public API (LLMClient Protocol) ─────────────────────────────

    def invoke(self, prompt: str) -> Message:
        """Synchronously generate a response for *prompt*.

        Satisfies the ``LLMClient`` Protocol's ``invoke`` method.

        If generation fails, returns a safe fallback JSON (casual_chat with
        confidence 0.5) so the caller's error-handling (rule-layer fallback
        in ``ChatIntentClassifier``) still receives a parseable response.
        """
        try:
            text, prompt_tokens, completion_tokens = self._generate(prompt)
        except Exception as exc:
            logger.error("Generation failed, returning fallback: %s", exc)
            return Message(
                content=_FALLBACK_JSON,
                response_metadata=usage_block(0, 0),
            )
        return Message(
            content=text.strip(),
            response_metadata=usage_block(prompt_tokens, completion_tokens),
        )

    async def ainvoke(self, prompt: str) -> Message:
        """Asynchronously generate a response for *prompt*.

        Satisfies the ``LLMClient`` Protocol's ``ainvoke`` method.  Generation
        is CPU/GPU-bound so we run it in a thread executor to avoid blocking
        the event loop in async code paths (e.g. ``ChatIntentClassifier.
        classify``).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.invoke, prompt)

    # ── Internal ────────────────────────────────────────────────────

    @staticmethod
    def _read_base_model_from_config(model_path: str) -> str:
        """Read the base model name from the LoRA adapter config."""
        config_path = Path(model_path) / "adapter_config.json"
        if config_path.is_file():
            try:
                with config_path.open("r", encoding="utf-8") as f:
                    adapter_cfg = json.load(f)
                base = adapter_cfg.get("base_model_name_or_path", "")
                if base:
                    return base
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read adapter config: %s", exc)

        logger.warning(
            "Could not determine base model from adapter config; "
            "defaulting to %s",
            FinetunedIntentLLM._DEFAULT_BASE_MODEL,
        )
        return FinetunedIntentLLM._DEFAULT_BASE_MODEL

    def _generate(self, prompt: str) -> tuple[str, int, int]:
        """Generate text from *prompt*.

        Returns:
            Tuple of (generated_text, prompt_token_count, completion_token_count).
        """
        import torch

        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )
        # Move inputs to the model's device
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        prompt_token_count = inputs["input_ids"].shape[1]

        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=self._max_new_tokens,
                do_sample=False,
                pad_token_id=self._tokenizer.pad_token_id,
                eos_token_id=self._tokenizer.eos_token_id,
            )

        # Extract only the generated tokens (after the prompt)
        generated_ids = output_ids[0][prompt_token_count:]
        text = self._tokenizer.decode(generated_ids, skip_special_tokens=True)
        completion_token_count = len(generated_ids)

        return text, prompt_token_count, completion_token_count


# ── CLI entry point ─────────────────────────────────────────────────

def _main() -> None:
    """Quick smoke test: load model and classify a sample message."""
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python -m training.finetune_intent.inference <model_path>")
        print("Example:")
        print("  python -m training.finetune_intent.inference "
              "training/finetune_intent/outputs/final")
        sys.exit(1)

    model_path = sys.argv[1]
    llm = FinetunedIntentLLM(model_path=model_path)

    # Use the same prompt format as ChatIntentClassifier
    from training.finetune_intent.prepare_data import format_prompt

    test_messages = [
        "今天工作压力好大，感觉撑不住了",
        "你好呀，最近怎么样",
        "不想活了，真的太累了",
    ]

    for msg in test_messages:
        prompt = format_prompt(msg)
        response = llm.invoke(prompt)
        print(f"\nInput : {msg}")
        print(f"Output: {response.content}")
        usage = response.response_metadata.get("token_usage", {})
        print(f"Tokens: prompt={usage.get('prompt_tokens', 0)}, "
              f"completion={usage.get('completion_tokens', 0)}")


if __name__ == "__main__":
    _main()
