"""Optional Qwen3-8B inference backend for the independent TaskSpec protocol.

Not automatically imported, downloaded, or executed. This adapter requires
CUDA-capable hardware, transformers, accelerate and optionally bitsandbytes.
The project's recorded model identity is pinned for reproducibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

QWEN_NAME = 'Qwen/Qwen3-8B'
QWEN_REVISION = 'b968826d9c46dd6066d109eabc6255188de91218'

@dataclass
class QwenTaskSpecModel:
    tokenizer: Any
    model: Any
    max_new_tokens: int = 3072

    @classmethod
    def load(cls, *, four_bit: bool = True, local_files_only: bool = True, max_new_tokens: int = 3072):
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
            if four_bit:
                from transformers import BitsAndBytesConfig
        except ImportError as err:
            raise RuntimeError('Qwen backend requires torch, transformers, accelerate and optional bitsandbytes') from err
        kwargs: dict[str, Any] = {
            'revision': QWEN_REVISION,
            'local_files_only': local_files_only,
            'device_map': 'auto',
            'trust_remote_code': False,
        }
        if four_bit:
            kwargs['quantization_config'] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type='nf4',
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
        tokenizer=AutoTokenizer.from_pretrained(QWEN_NAME, revision=QWEN_REVISION,
            local_files_only=local_files_only, trust_remote_code=False)
        model=AutoModelForCausalLM.from_pretrained(QWEN_NAME, **kwargs)
        model.eval()
        return cls(tokenizer=tokenizer, model=model, max_new_tokens=max_new_tokens)

    def generate(self, prompt: str, source: dict[str, Any]) -> str:
        # No frozen labels, previous predictions, safety or gold are added here.
        messages=[
            {'role':'system','content':'Produce only valid JSON matching the requested TaskSpec. No Markdown.'},
            {'role':'user','content':prompt},
        ]
        try:
            import torch
        except ImportError as err:
            raise RuntimeError('torch is required for model generation') from err
        tokens=self.tokenizer.apply_chat_template(messages, tokenize=True,
            return_tensors='pt', add_generation_prompt=True, enable_thinking=False)
        device=next(self.model.parameters()).device
        tokens=tokens.to(device)
        with torch.inference_mode():
            output=self.model.generate(tokens, max_new_tokens=self.max_new_tokens,
                do_sample=False, pad_token_id=self.tokenizer.eos_token_id)
        return self.tokenizer.decode(output[0][tokens.shape[-1]:],skip_special_tokens=True).strip()
