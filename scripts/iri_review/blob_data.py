"""Push / pull the review's data to / from the team's dev blob (container `projects`).

Layout under pa-aa-bfa-drought/:
  raw/iri_maproom/        Maproom export (fetch_maproom.py)
  raw/iri_partner/        IRI's candidate table as shared with us (not public)
  processed/iri_review/   outputs of backtest / skill / compare / checks / overall, AOI weights, SEAS5 + ERA5 pulls
  processed/obs_review/   outputs of scripts/obs_review/

Usage:
  BFA_DATA_DIR=<folder> uv run --no-project --with ocha-stratus python scripts/iri_review/blob_data.py push
  uv run --no-project --with ocha-stratus python scripts/iri_review/blob_data.py pull   # prints the temp folder
"""

import sys
import tempfile
from pathlib import Path

import ocha_stratus as stratus

PREFIX = "pa-aa-bfa-drought"
MAP = {  # local sub-folder of BFA_DATA_DIR -> blob folder
    "iri_maproom": "raw/iri_maproom",
    "iri_partner": "raw/iri_partner",
    "iri_review": "processed/iri_review",
    "db": "processed/iri_review/db",
    "cod": "processed/iri_review/cod",
    "obs_review": "processed/obs_review",
}


def push(src: Path) -> None:
    cc = stratus.get_container_client("projects", "dev", write=True)
    n = 0
    for local, remote in MAP.items():
        for f in sorted((src / local).glob("*")):
            if f.is_file() and f.suffix in {".csv", ".json", ".parquet", ".xlsx", ".png", ".txt", ".py"}:
                with f.open("rb") as fh:
                    cc.upload_blob(f"{PREFIX}/{remote}/{f.name}", fh, overwrite=True)
                n += 1
    print(f"pushed {n} files")


def pull() -> None:
    cc = stratus.get_container_client("projects", "dev")
    dst = Path(tempfile.mkdtemp(prefix="bfa_iri_review_"))
    for local, remote in MAP.items():
        for b in cc.list_blobs(name_starts_with=f"{PREFIX}/{remote}/"):
            rel = b.name[len(f"{PREFIX}/{remote}/"):]
            if "/" in rel:
                continue
            p = dst / local / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(cc.download_blob(b.name).readall())
    print(dst)


if __name__ == "__main__":
    if sys.argv[1] == "push":
        import os

        push(Path(os.environ["BFA_DATA_DIR"]))
    else:
        pull()
