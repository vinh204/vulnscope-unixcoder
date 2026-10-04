"""Reusable UniXcoder inference and token-occlusion explanations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import torch
from transformers import RobertaConfig, RobertaForSequenceClassification, RobertaTokenizer

from model import Model


@dataclass
class Prediction:
    label: int
    vulnerable_probability: float
    safe_probability: float
    elapsed_ms: float
    token_count: int
    truncated: bool

    def to_dict(self):
        return asdict(self)


class UniXcoderPredictor:
    def __init__(self, checkpoint: str, model_name: str = "microsoft/unixcoder-base",
                 block_size: int = 512, device: str | None = None):
        checkpoint_path = Path(checkpoint)
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy checkpoint: {checkpoint_path}")
        self.block_size = block_size
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.tokenizer = RobertaTokenizer.from_pretrained(model_name)
        config = RobertaConfig.from_pretrained(model_name, num_labels=2)
        encoder = RobertaForSequenceClassification.from_pretrained(model_name, config=config)
        self.model = Model(encoder, config, SimpleNamespace()).to(self.device)
        state = torch.load(checkpoint_path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)
        self.model.eval()

    def encode(self, code: str):
        normalized = " ".join(code.split())
        raw_tokens = self.tokenizer.tokenize(normalized)
        limit = self.block_size - 4
        code_tokens = raw_tokens[:limit]
        tokens = [self.tokenizer.cls_token, "<encoder_only>", self.tokenizer.sep_token,
                  *code_tokens, self.tokenizer.sep_token]
        ids = self.tokenizer.convert_tokens_to_ids(tokens)
        mask = [1] * len(ids)
        padding = self.block_size - len(ids)
        ids += [self.tokenizer.pad_token_id] * padding
        mask += [0] * padding
        return (tokens, torch.tensor([ids], device=self.device),
                torch.tensor([mask], device=self.device), len(raw_tokens) > limit)

    @torch.inference_mode()
    def predict(self, code: str) -> Prediction:
        if not code.strip():
            raise ValueError("Mã nguồn không được để trống")
        started = perf_counter()
        tokens, input_ids, attention_mask, truncated = self.encode(code)
        probabilities = self.model(input_ids=input_ids, attention_mask=attention_mask)[0]
        return Prediction(int(torch.argmax(probabilities).item()), float(probabilities[1].item()),
                          float(probabilities[0].item()), (perf_counter() - started) * 1000,
                          max(0, len(tokens) - 4), truncated)

    @torch.inference_mode()
    def predict_batch(self, codes: list[str]) -> list[Prediction]:
        """Predict a batch efficiently for offline evaluation."""
        if not codes:
            return []
        started = perf_counter()
        encoded = [self.encode(code) for code in codes]
        input_ids = torch.cat([item[1] for item in encoded], dim=0)
        attention_masks = torch.cat([item[2] for item in encoded], dim=0)
        probabilities = self.model(input_ids=input_ids, attention_mask=attention_masks)
        elapsed_per_item = (perf_counter() - started) * 1000 / len(codes)
        results = []
        for position, (tokens, _, _, truncated) in enumerate(encoded):
            item = probabilities[position]
            results.append(Prediction(
                int(torch.argmax(item).item()), float(item[1].item()), float(item[0].item()),
                elapsed_per_item, max(0, len(tokens) - 4), truncated,
            ))
        return results

    @torch.inference_mode()
    def explain(self, code: str, max_tokens: int = 80):
        """Measure vulnerable-probability change after masking each token."""
        tokens, input_ids, attention_mask, _ = self.encode(code)
        base = float(self.model(input_ids=input_ids, attention_mask=attention_mask)[0, 1].item())
        explanations = []
        first = 3
        for position in range(first, min(len(tokens) - 1, first + max_tokens)):
            masked = input_ids.clone()
            masked[0, position] = self.tokenizer.mask_token_id
            changed = float(self.model(input_ids=masked, attention_mask=attention_mask)[0, 1].item())
            explanations.append({"token": self.tokenizer.convert_tokens_to_string([tokens[position]]),
                                 "position": position - first, "attribution": base - changed})
        return sorted(explanations, key=lambda item: abs(item["attribution"]), reverse=True)
