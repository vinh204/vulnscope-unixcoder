"""Model wrapper used by training, evaluation and the demo."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, SequentialSampler


class Model(nn.Module):
    def __init__(self, encoder, config, args):
        super().__init__()
        self.encoder = encoder
        self.config = config
        self.args = args
        self.loss = nn.CrossEntropyLoss()
        self.query = 0

    def forward(self, inputs_embeds=None, input_ids=None, attention_mask=None, labels=None):
        if attention_mask is None:
            if input_ids is None:
                raise ValueError("attention_mask is required when inputs_embeds is used")
            attention_mask = input_ids.ne(getattr(self.config, "pad_token_id", 1))
        outputs = self.encoder(input_ids=input_ids, inputs_embeds=inputs_embeds, attention_mask=attention_mask)
        logits = outputs.logits if hasattr(outputs, "logits") else outputs[0]
        probabilities = torch.softmax(logits, dim=-1)
        if labels is None:
            return probabilities
        return self.loss(logits, labels), probabilities

    def freeze_encoder_and_embeddings(self):
        """Freeze the RoBERTa backbone and leave the classification head trainable."""
        backbone = getattr(self.encoder, "roberta", None)
        if backbone is None:
            raise AttributeError("The wrapped model does not expose a RoBERTa backbone")
        for parameter in backbone.parameters():
            parameter.requires_grad = False

    def get_results(self, dataset, batch_size):
        """Return probabilities and predictions without assuming CUDA."""
        self.query += len(dataset)
        device = next(self.parameters()).device
        loader = DataLoader(dataset, sampler=SequentialSampler(dataset), batch_size=batch_size, num_workers=0)
        all_probabilities = []
        self.eval()
        for batch in loader:
            inputs = batch[0].to(device)
            with torch.no_grad():
                probabilities = self(input_ids=inputs)
            all_probabilities.append(probabilities.cpu().numpy())
        probabilities = np.concatenate(all_probabilities, axis=0)
        return probabilities.tolist(), probabilities.argmax(axis=1).tolist()
