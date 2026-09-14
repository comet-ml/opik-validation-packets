"""
Step 02 — Dataset Creation and Versioning

Seeds the Opik dataset for the docs_rag persona:

    docs_rag — query, expected_output, relevant_doc_ids  (retrieval grounding)

The dataset is then mutated twice (an update + an insert) to prove version
history works — every mutation creates a new immutable dataset version, and
each experiment (Step 04+) is pinned to the version active when it ran.

Docs: https://www.comet.com/docs/opik/v1/evaluation/manage_datasets/

Usage:
    python 02_datasets/02_datasets.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import opik

load_dotenv()
os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")  # SDK only reads OPIK_API_KEY

DATASETS_DIR = Path(__file__).parent.parent / "data" / "datasets"
client = opik.Opik()


def pause(msg: str) -> None:
    """input() prompt between UI-checkpoint steps. NONINTERACTIVE=1 skips blocking on stdin."""
    if os.environ.get("NONINTERACTIVE") == "1":
        print(msg)
        return
    input(msg)


# =============================================================================
# docs_rag — grounding checked against relevant_doc_ids
# =============================================================================

# --- Create: seed the dataset (version 1) -----------------------------------
with open(DATASETS_DIR / "docs_rag_seed.json") as f:
    seed_items = json.load(f)

dataset = client.get_or_create_dataset(
    name="genai-gateway-docs-rag-qa",
    description="Golden Q&A set for the AcmeChat 'docs_rag' persona.",
)
dataset.insert(seed_items)
pause(f">>> UI: Datasets > genai-gateway-docs-rag-qa — confirm {len(seed_items)} items. Press Enter to continue.\n")

# --- Mutation 1: update an existing item (ground-truth correction) ----------
first = dict(dataset.get_items()[0])
first["expected_output"] += " Contact HR if your situation isn't covered by this policy."
dataset.update([first])
pause(">>> UI: confirm a new version appears in the version history. Press Enter to continue.\n")

# --- Mutation 2: insert a new item (adding a test case) ---------------------
dataset.insert([{
    "query": "How often are company laptops refreshed?",
    "expected_output": (
        "Company laptops are refreshed every 3 years; an early refresh can be "
        "requested through IT with manager approval."
    ),
    "relevant_doc_ids": ["kb-007"],
}])

print("Done. See 02_datasets.md for the UI checklist.")
