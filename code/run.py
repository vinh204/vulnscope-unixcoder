# coding=utf-8
# Copyright 2018 The Google AI Language Team Authors and The HuggingFace Inc. team.
# Copyright (c) 2018, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Fine-tuning the library models for language modeling on a text file (GPT, GPT-2, BERT, RoBERTa).
GPT and GPT-2 are fine-tuned using a causal language modeling (CLM) loss while BERT and RoBERTa are fine-tuned
using a masked language modeling (MLM) loss.
"""

from __future__ import absolute_import, division, print_function

import argparse
import logging
import os
import random
import json
import re
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, average_precision_score
import torch
import numpy as np
import tempfile
from pathlib import Path

from torch.utils.data import DataLoader, Dataset, SequentialSampler, RandomSampler

from model import Model
from data_utils import load_records, validate_code_records
from torch.optim import AdamW
from transformers import (get_linear_schedule_with_warmup,
                          RobertaConfig, RobertaForSequenceClassification, RobertaTokenizer)

logger = logging.getLogger(__name__)


class InputFeatures(object):
    """A single training/test features for a example."""

    def __init__(self,
                 input_tokens,
                 input_ids,
                 index,
                 label,

                 ):
        self.input_tokens = input_tokens
        self.input_ids = input_ids
        self.index = index
        self.label = label


def convert_examples_to_features(js, tokenizer, args):
    """convert examples to token ids"""
    code = js[args.code_key]
    if args.tokenize_ast_token:
        code = ' '.join(js['ast_tokens'])
    code = ' '.join(code.split())
    code_tokens = tokenizer.tokenize(code)[:args.block_size - 4]
    source_tokens = [tokenizer.cls_token, "<encoder_only>", tokenizer.sep_token] + code_tokens + [
        tokenizer.sep_token]
    source_ids = tokenizer.convert_tokens_to_ids(source_tokens)
    padding_length = args.block_size - len(source_ids)
    source_ids += [tokenizer.pad_token_id] * padding_length
    return InputFeatures(source_tokens, source_ids, js.get(args.index_key, 0), int(js[args.label_key]))


class TextDataset(Dataset):
    def __init__(self, tokenizer, args, file_path=None):
        m = re.search(r"(train|valid|test)", file_path)
        if m is None:
            partition = None
        else:
            partition = m.group(1)

        self.examples = []
        count = 0
        records = validate_code_records(load_records(file_path), file_path)
        for js in records:
            count += 1
            if args.head is not None and count >= args.head:
                self.examples.append(convert_examples_to_features(js, tokenizer, args))
                break
            self.examples.append(convert_examples_to_features(js, tokenizer, args))

        if partition == 'train':
            for idx, example in enumerate(self.examples[:3]):
                logger.info("*** Example ***")
                logger.info("idx: {}".format(idx))
                logger.info("label: {}".format(example.label))
                logger.info("input_tokens: {}".format([x.replace('\u0120', '_') for x in example.input_tokens]))
                logger.info("input_ids: {}".format(' '.join(map(str, example.input_ids))))

        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, i):
        return (
            torch.tensor(self.examples[i].input_ids),
            torch.tensor(self.examples[i].label),
        )


def set_seed(seed=42):
    random.seed(seed)
    # Python reads PYTHONHASHSEED only when the interpreter starts. Setting it
    # here would be too late, so require the caller to provide it in the shell.
    if os.environ.get('PYTHONHASHSEED') != str(seed):
        logger.warning(
            "PYTHONHASHSEED is not %s before interpreter startup; set it in the shell "
            "to control Python hash randomization.",
            seed,
        )
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True


def _rng_state():
    state = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
    }
    if torch.cuda.is_available():
        state["cuda"] = torch.cuda.get_rng_state_all()
    return state


def _restore_rng_state(state):
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"])
    if torch.cuda.is_available() and "cuda" in state:
        torch.cuda.set_rng_state_all(state["cuda"])


def _atomic_torch_save(value, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        torch.save(value, temp_path)
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)


def save_last_checkpoint(args, model, optimizer, scheduler, epoch, global_step, best_perf):
    checkpoint_dir = Path(args.output_dir) / "checkpoint-last"
    state = {
        "model": (model.module if hasattr(model, "module") else model).state_dict(),
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict(),
        "epoch": epoch,
        "global_step": global_step,
        "best_perf": best_perf,
        "rng_state": _rng_state(),
        "training_args": {
            "model_name_or_path": args.model_name_or_path,
            "train_data_file": str(Path(args.train_data_file).resolve()),
            "eval_data_file": str(Path(args.eval_data_file).resolve()),
            "block_size": args.block_size,
            "train_batch_size": args.train_batch_size,
            "gradient_accumulation_steps": args.gradient_accumulation_steps,
            "learning_rate": args.learning_rate,
            "weight_decay": args.weight_decay,
            "adam_epsilon": args.adam_epsilon,
            "max_grad_norm": args.max_grad_norm,
            "num_train_epochs": args.num_train_epochs,
            "seed": args.seed,
            "validation_metric": args.validation_metric,
            "head": args.head,
            "tokenize_ast_token": args.tokenize_ast_token,
            "freeze_encoder_and_embeddings": args.freeze_encoder_and_embeddings,
        },
    }
    _atomic_torch_save(state, checkpoint_dir / "training_state.pt")


def train(args, train_dataset, model, tokenizer):
    """ Train the model """
    train_sampler = RandomSampler(train_dataset)
    train_dataloader = DataLoader(train_dataset, sampler=train_sampler,
                                  batch_size=args.train_batch_size, num_workers=0, pin_memory=args.device.type == "cuda")

    # The scheduler counts optimizer updates, not mini-batches. Account for
    # gradient accumulation when computing the total and warmup steps.
    updates_per_epoch = (len(train_dataloader) + args.gradient_accumulation_steps - 1) // args.gradient_accumulation_steps
    args.max_steps = args.num_train_epochs * updates_per_epoch

    # Prepare optimizer and schedule (linear warmup and decay)
    no_decay = ['bias', 'LayerNorm.weight']
    optimizer_grouped_parameters = [
        {'params': [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)],
         'weight_decay': args.weight_decay},
        {'params': [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)], 'weight_decay': 0.0}
    ]
    optimizer = AdamW(optimizer_grouped_parameters, lr=args.learning_rate, eps=args.adam_epsilon)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=int(args.max_steps * 0.1),
                                                num_training_steps=args.max_steps)

    # Train!
    logger.info("***** Running training *****")
    logger.info("  Num examples = %d", len(train_dataset))
    logger.info("  Num Epochs = %d", args.num_train_epochs)
    logger.info("  Batch size per device = %d", args.train_batch_size // max(1, args.n_gpu))
    logger.info("  Total train batch size = %d", args.train_batch_size)
    logger.info("  Gradient accumulation steps = %d", args.gradient_accumulation_steps)
    logger.info("  Effective train batch size = %d", args.train_batch_size * args.gradient_accumulation_steps)
    logger.info("  Total optimization steps = %d", args.max_steps)

    losses, best_perf, global_step, start_epoch = [], float("-inf"), 0, 0
    if args.resume_from_checkpoint:
        resume_path = Path(args.resume_from_checkpoint)
        state_path = resume_path / "training_state.pt" if resume_path.is_dir() else resume_path
        if not state_path.is_file():
            raise FileNotFoundError(f"Resume state not found: {state_path}")
        state = torch.load(state_path, map_location="cpu", weights_only=False)
        expected = state["training_args"]
        current = {
            "model_name_or_path": args.model_name_or_path,
            "train_data_file": str(Path(args.train_data_file).resolve()),
            "eval_data_file": str(Path(args.eval_data_file).resolve()),
            "block_size": args.block_size,
            "train_batch_size": args.train_batch_size,
            "gradient_accumulation_steps": args.gradient_accumulation_steps,
            "learning_rate": args.learning_rate,
            "weight_decay": args.weight_decay,
            "adam_epsilon": args.adam_epsilon,
            "max_grad_norm": args.max_grad_norm,
            "num_train_epochs": args.num_train_epochs,
            "seed": args.seed,
            "validation_metric": args.validation_metric,
            "head": args.head,
            "tokenize_ast_token": args.tokenize_ast_token,
            "freeze_encoder_and_embeddings": args.freeze_encoder_and_embeddings,
        }
        mismatches = [key for key, value in expected.items() if current.get(key) != value]
        if mismatches:
            raise ValueError("Resume settings differ from checkpoint: " + ", ".join(mismatches))
        model_to_load = model.module if hasattr(model, "module") else model
        model_to_load.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        start_epoch = int(state["epoch"])
        global_step = int(state["global_step"])
        best_perf = float(state["best_perf"])
        _restore_rng_state(state["rng_state"])
        logger.info("Resuming at epoch %d, optimizer step %d", start_epoch + 1, global_step)

    model.zero_grad()
    for idx in range(start_epoch, args.num_train_epochs):
        model.train()
        for step, batch in enumerate(train_dataloader):
            inputs = batch[0].to(args.device)
            labels = batch[1].to(args.device)
            model.train()
            loss, prob = model(input_ids=inputs, labels=labels)

            if args.n_gpu > 1:
                loss = loss.mean()  # mean() to average on multi-gpu parallel training
            raw_loss = loss.item()
            accumulation_window_start = (step // args.gradient_accumulation_steps) * args.gradient_accumulation_steps
            accumulation_window_size = min(
                args.gradient_accumulation_steps,
                len(train_dataloader) - accumulation_window_start,
            )
            loss = loss / accumulation_window_size

            loss.backward()

            losses.append(raw_loss)

            if (step + 1) % 100 == 0:
                logger.info("epoch {} step {} loss {}".format(idx, step + 1, round(np.mean(losses[-100:]), 4)))

            if ((step + 1) % args.gradient_accumulation_steps == 0
                    or (step + 1) == len(train_dataloader)):
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
                optimizer.step()
                optimizer.zero_grad()
                scheduler.step()
                global_step += 1

        results = evaluate(args, model, tokenizer, args.eval_data_file)
        for key, value in results.items():
            logger.info("  %s = %s", key, round(value, 4))

        if results[f'eval_{args.validation_metric}'] > best_perf:
            best_perf = results[f'eval_{args.validation_metric}']
            logger.info("  " + "*" * 20)
            logger.info(f"  Best {args.validation_metric}:%s", round(best_perf, 4))
            logger.info("  " + "*" * 20)

            checkpoint_prefix = f'checkpoint-best-{args.validation_metric}'
            output_dir = os.path.join(args.output_dir, '{}'.format(checkpoint_prefix))
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            output_dir = os.path.join(output_dir, '{}'.format('model.bin'))
            model_to_save = model.module if hasattr(model, 'module') else model
            _atomic_torch_save(model_to_save.state_dict(), output_dir)
            logger.info("Saving model checkpoint to %s", output_dir)

        save_last_checkpoint(args, model, optimizer, scheduler, idx + 1, global_step, best_perf)
        logger.info("Saved resumable checkpoint after epoch %d", idx + 1)


def evaluate(args, model, tokenizer, data_file):
    """ Evaluate the model """
    eval_dataset = TextDataset(tokenizer, args, data_file)
    eval_sampler = SequentialSampler(eval_dataset)
    eval_dataloader = DataLoader(eval_dataset, sampler=eval_sampler, batch_size=args.eval_batch_size, num_workers=0)

    eval_output_dir = args.output_dir
    if not os.path.exists(eval_output_dir):
        os.makedirs(eval_output_dir)

    # Eval!
    logger.info("***** Running evaluation *****")
    logger.info("  Num examples = %d", len(eval_dataset))
    logger.info("  Batch size = %d", args.eval_batch_size)
    logger.info("  Gradient accumulation steps = %d", args.gradient_accumulation_steps)
    logger.info("  Effective batch size = %d", args.eval_batch_size * args.gradient_accumulation_steps)
    eval_loss = 0.0
    nb_eval_steps = 0
    model.eval()
    labels = []
    probs = []
    for batch in eval_dataloader:
        inputs = batch[0].to(args.device)
        label = batch[1].to(args.device)
        with torch.no_grad():
            loss, prob = model(input_ids=inputs, labels=label)
            eval_loss += loss.mean().item()
            labels.append(label.cpu().numpy())
            probs.append(prob.cpu().numpy())
        nb_eval_steps += 1
    labels = np.concatenate(labels, 0)
    probs = np.concatenate(probs, 0)
    preds = np.argmax(probs, axis=1)
    eval_loss = eval_loss / nb_eval_steps

    result = {
        "eval_acc": accuracy_score(labels, preds),
        "eval_precision": precision_score(labels, preds, zero_division=0),
        "eval_recall": recall_score(labels, preds, zero_division=0),
        "eval_f1": f1_score(labels, preds, zero_division=0),
        "eval_roc_auc": roc_auc_score(labels, probs[:, 1]) if len(np.unique(labels)) == 2 else 0.0,
        "eval_pr_auc": average_precision_score(labels, probs[:, 1]) if len(np.unique(labels)) == 2 else 0.0,
    }

    return result


def main():
    parser = argparse.ArgumentParser()

    ## Required parameters
    parser.add_argument("--output_dir", default=None, type=str, required=True,
                        help="The output directory where the model predictions and checkpoints will be written.")
    ## Other parameters
    parser.add_argument("--train_data_file", default=None, type=str,
                        help="The input training data file (a jsonl file).")
    parser.add_argument("--eval_data_file", default=None, type=str,
                        help="An optional input evaluation data file to evaluate the perplexity on (a jsonl file).")
    parser.add_argument("--model_name_or_path", default="microsoft/unixcoder-base", type=str,
                        help="The model checkpoint for weights initialization.")

    parser.add_argument("--block_size", default=512, type=int,
                        help="Optional input sequence length after tokenization.")
    parser.add_argument("--do_train", action='store_true',
                        help="Whether to run training.")
    parser.add_argument("--do_eval", action='store_true',
                        help="Whether to run eval on the dev set.")
    parser.add_argument("--resume_from_checkpoint", type=str, default=None,
                        help="Resume training from a checkpoint-last directory; checkpoints are saved after each epoch.")
    parser.add_argument("--train_batch_size", default=8, type=int,
                        help="Batch size per GPU/CPU for training.")
    parser.add_argument("--eval_batch_size", default=16, type=int,
                        help="Batch size per GPU/CPU for evaluation.")
    parser.add_argument("--learning_rate", default=2e-5, type=float,
                        help="The initial learning rate for Adam.")
    parser.add_argument('--gradient_accumulation_steps', type=int, default=4,
                        help="Number of updates steps to accumulate before performing a backward/update pass.")
    parser.add_argument("--weight_decay", default=0.0, type=float,
                        help="Weight deay if we apply some.")
    parser.add_argument("--adam_epsilon", default=1e-8, type=float,
                        help="Epsilon for Adam optimizer.")
    parser.add_argument("--max_grad_norm", default=1.0, type=float,
                        help="Max gradient norm.")
    parser.add_argument("--num_train_epochs", default=10, type=int,
                        help="Total number of training epochs to perform.")
    parser.add_argument('--seed', type=int, default=123456,
                        help="random seed for initialization")
    parser.add_argument('--validation_metric', type=str, default='f1',
                        help="metric to use to for model selection based on the validation set")
    parser.add_argument('--code_key', type=str, default="func",
                        help="dataset key for code")
    parser.add_argument('--label_key', type=str, default="target",
                        help="dataset key for labels")
    parser.add_argument('--index_key', type=str, default="idx",
                        help="dataset key for index")
    parser.add_argument('--head', type=int,
                        help="number of dataset examples to cut off")
    parser.add_argument('--freeze_encoder_and_embeddings', action='store_true',
                        help="whether to freeze the model's encoder and embeddings layers")
    parser.add_argument('--tokenize_ast_token', type=int, default=0)

    # print arguments
    args = parser.parse_args()
    if not (args.do_train or args.do_eval):
        parser.error("Select at least one operation: --do_train and/or --do_eval")
    if args.resume_from_checkpoint and not args.do_train:
        parser.error("--resume_from_checkpoint requires --do_train")
    if args.do_train and (not args.train_data_file or not args.eval_data_file):
        parser.error("--do_train requires --train_data_file and --eval_data_file")
    if args.do_eval and not args.eval_data_file:
        parser.error("--do_eval requires --eval_data_file")
    if args.block_size < 5 or args.block_size > 512:
        parser.error("--block_size must be between 5 and 512 for microsoft/unixcoder-base")
    if args.train_batch_size < 1 or args.eval_batch_size < 1 or args.gradient_accumulation_steps < 1:
        parser.error("Batch sizes and --gradient_accumulation_steps must be positive")
    if args.num_train_epochs < 1 or args.learning_rate <= 0 or args.max_grad_norm <= 0:
        parser.error("Epochs, learning rate and max gradient norm must be positive")
    if args.head is not None and args.head < 1:
        parser.error("--head must be positive when supplied")
    if args.validation_metric not in {"f1", "acc", "precision", "recall", "roc_auc", "pr_auc"}:
        parser.error("Unsupported --validation_metric")
    # set log
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(name)s -   %(message)s',
                        datefmt='%m/%d/%Y %H:%M:%S', level=logging.INFO)
    # set device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    args.n_gpu = torch.cuda.device_count()
    args.device = device
    logger.info("device: %s, n_gpu: %s", device, args.n_gpu)

    # Set seed
    set_seed(args.seed)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    training_config = {
        "model_name_or_path": args.model_name_or_path,
        "train_data_file": str(Path(args.train_data_file).resolve()) if args.train_data_file else None,
        "eval_data_file": str(Path(args.eval_data_file).resolve()) if args.eval_data_file else None,
        "block_size": args.block_size,
        "train_batch_size": args.train_batch_size,
        "eval_batch_size": args.eval_batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "adam_epsilon": args.adam_epsilon,
        "max_grad_norm": args.max_grad_norm,
        "num_train_epochs": args.num_train_epochs,
        "seed": args.seed,
        "validation_metric": args.validation_metric,
        "device": str(args.device),
        "gpu_count": args.n_gpu,
        "resume_from_checkpoint": args.resume_from_checkpoint,
    }
    (Path(args.output_dir) / "training_config.json").write_text(
        json.dumps(training_config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # build model
    tokenizer = RobertaTokenizer.from_pretrained(args.model_name_or_path)
    config = RobertaConfig.from_pretrained(args.model_name_or_path)
    config.num_labels = 2
    model = RobertaForSequenceClassification.from_pretrained(args.model_name_or_path, config=config)

    model = Model(model, config, args)
    if args.freeze_encoder_and_embeddings:
        logger.info("Freezing encoder and embeddings parameters")
        model.freeze_encoder_and_embeddings()
    logger.info("Training/evaluation parameters %s", args)

    model.to(args.device)
    if args.n_gpu > 1:
        model = torch.nn.DataParallel(model)

        # Training
    if args.do_train:
        train_dataset = TextDataset(tokenizer, args, args.train_data_file)
        train(args, train_dataset, model, tokenizer)

    # Evaluation
    if args.do_eval:
        output_dir = os.path.join(args.output_dir, f'checkpoint-best-{args.validation_metric}/model.bin')
        model_to_load = model.module if hasattr(model, 'module') else model
        model_to_load.load_state_dict(torch.load(output_dir, map_location=args.device, weights_only=True))
        result = evaluate(args, model, tokenizer, args.eval_data_file)
        logger.info("***** Eval results *****")
        for key in sorted(result.keys()):
            logger.info("  %s = %s", key, str(round(result[key] * 100 if "map" in key else result[key], 4)))

if __name__ == "__main__":
    main()
