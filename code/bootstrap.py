"""Prepare model artifacts, then start the production Streamlit server."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def ensure_checkpoint() -> Path:
    checkpoint = Path(os.getenv("CHECKPOINT_PATH", "/app/models/model.bin"))
    if checkpoint.is_file():
        return checkpoint

    repo_id = os.getenv("CHECKPOINT_REPO_ID")
    if not repo_id:
        raise RuntimeError(
            f"Checkpoint not found at {checkpoint}. Set CHECKPOINT_REPO_ID "
            "or mount a checkpoint at CHECKPOINT_PATH."
        )

    from huggingface_hub import hf_hub_download

    filename = os.getenv("CHECKPOINT_FILENAME", "model.bin")
    revision = os.getenv("CHECKPOINT_REVISION", "main")
    downloaded = Path(
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
            token=os.getenv("HF_TOKEN"),
        )
    )
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    try:
        checkpoint.symlink_to(downloaded)
    except OSError:
        import shutil

        shutil.copy2(downloaded, checkpoint)
    return checkpoint


def main() -> None:
    checkpoint = ensure_checkpoint()
    print(f"Using checkpoint: {checkpoint}", flush=True)
    subprocess.run(
        [
            "streamlit",
            "run",
            "code/app.py",
            "--server.address=0.0.0.0",
            "--server.port=7860",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
