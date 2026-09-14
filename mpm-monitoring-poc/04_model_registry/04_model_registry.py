"""
Step 04 -- Model Registry / Version History

SDK mechanics demonstrated -- two calls, in this specific order, on a fresh
`comet_ml.start()` experiment, once per version:

  1. `experiment.log_model(model_name, file_path)` -- uploads the artifact
     (here, `data/model.joblib`, written by Step 00) and attaches it to THIS
     experiment. A model must be logged to an experiment before it can be
     registered -- `register_model` promotes an already-logged model, it
     doesn't take a raw file path itself.
  2. `experiment.register_model(model_name, version=..., registry_name=...,
     comment=..., tags=..., sync=True)` -- takes the model just logged in
     step 1 and publishes it as a specific version under the Model Registry
     (a workspace-level catalog, separate from any single experiment).
       - `version` -- an explicit semver string you control (not
         auto-incremented) -- this is what makes it possible to reuse the
         exact same string as MPM's per-event `model_version` tag.
       - `registry_name` -- set to `config.MPM_MODEL_NAME`. Per Comet's own
         guidance, an MPM model and a Model Registry model are linked simply
         by using the same name
         (https://www.comet.com/docs/v2/guides/model-production-monitoring/send-mpm-data/#integration-with-experiment-management)
         -- MPM would also auto-create a bare registry entry the first time
         an event lands, but this step goes further and attaches real
         version history with descriptive comments to that same model.
       - `tags` -- a list of free-form labels (e.g. `["production"]`,
         `["archived"]`) shown on the registry's version list; purely
         organizational, not enforced by anything. NOTE: an older `stages`
         parameter exists on this call but is silently ignored by the
         installed SDK version (a `COMET_WARNING` at runtime confirms this)
         -- `tags` is the current mechanism, use that instead.
       - `sync=True` -- makes the call block until registration finishes
         rather than returning immediately; harmless and worth keeping, but
         NOT what actually fixes the issue below.

--- Why register_model() can silently no-op, and how this script recovers ---
Because Step 01 runs before this step, by the time this script calls
`register_model(version="1.0.0", ...)`, MPM has *already* auto-created a
bare registry version "1.0.0" itself the moment the first event tagged
`model_version="1.0.0"` landed (this is documented, intentional Comet
behavior: "each model in MPM has a corresponding model in the Model
Registry"). `register_model()` then collides with that already-existing
version -- the backend logs `COMET_ERROR: Failed to register model.
Registry Model Versions must be unique to promote experiment model.` but
does NOT raise a Python exception, so the script has no way to detect
failure except by checking afterward. The practical effect: the version
exists, but with `comment: None` and no tags, exactly as if the call had
fully succeeded from the caller's point of view.

This was confirmed empirically (adding `sync=True` alone did not fix it --
the comment stayed null on a second attempt). The fix implemented below:
after each `register_model()` call, re-fetch the version's actual details
and check whether the comment attached. If it didn't (the auto-created-bare
case), fall back to `API.update_registry_model_version(comment=...)` +
`Model.add_tag(version, tag)` to patch metadata onto the already-existing
version instead of trying to recreate it. Both of those calls were verified
by hand to work reliably against this same conflict.

Two versions are registered:
  - `1.0.0` -- the model as originally deployed, before the upstream
    ERP/WMS migration broke `warehouse_inventory_level` (day config.BREAK_DAY).
  - `1.1.0` -- registered to represent the retrain/redeploy that went out on
    day `config.RETRAIN_DAY`, once the drift alert (Step 03) flagged the
    frozen feature. Every MPM prediction event from that day forward is
    tagged `model_version=1.1.0` (Step 01) -- the same version string used
    here -- so filtering the MPM dashboard to one version or the other and
    reading the Model Registry's version history are describing the exact
    same cutover.

Both versions log the SAME `model.joblib` artifact -- this demo does not
literally retrain a numerically-different model (that's orthogonal to what
this criterion tests); what matters is that two real, timestamped registry
versions exist, with comments that let you correlate the retrain against the
incident timeline. See README.md for the fuller reasoning.

Requires `COMET_API_KEY`/`COMET_WORKSPACE` (or `--dry-run` to validate the
plan locally with no network calls).

Docs: https://www.comet.com/docs/v2/guides/model-registry/using-model-registry/

Usage:
    python 04_model_registry/04_model_registry.py --dry-run
    python 04_model_registry/04_model_registry.py
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

import config

load_dotenv()

VERSION_PLAN = [
    {
        "version": config.MPM_MODEL_VERSION_BEFORE,
        "comment": (
            f"Initial model deployed before the upstream ERP/WMS migration. Predictions tagged "
            f"model_version={config.MPM_MODEL_VERSION_BEFORE} in MPM cover days 0-"
            f"{config.RETRAIN_DAY - 1} of the simulated window, including the break on day "
            f"{config.BREAK_DAY}."
        ),
        "tags": ["archived"],
    },
    {
        "version": config.MPM_MODEL_VERSION_AFTER,
        "comment": (
            f"Retrained/redeployed on day {config.RETRAIN_DAY} after MPM's drift alert flagged "
            f"warehouse_inventory_level frozen at {config.FROZEN_INVENTORY_VALUE} (see Step 01/03). "
            f"Predictions tagged model_version={config.MPM_MODEL_VERSION_AFTER} in MPM cover days "
            f"{config.RETRAIN_DAY}-{config.N_DAYS - 1} and show drift recovering back toward baseline."
        ),
        "tags": ["production"],
    },
]


def run_dry_run() -> None:
    print("[dry-run] nothing was registered with Comet\n")
    print(f"Registry model name: {config.MPM_MODEL_NAME}  (same name as the MPM model)")
    for entry in VERSION_PLAN:
        print(f"\n  version {entry['version']}  (tag: {entry['tags'][0]})")
        print(f"    comment: {entry['comment']}")
    print(
        "\nNext: fill in COMET_API_KEY/COMET_WORKSPACE/COMET_PROJECT_NAME in .env, then re-run "
        "without --dry-run to actually register these two versions."
    )


def run_live() -> None:
    import comet_ml

    if not config.MODEL_PATH.exists():
        raise SystemExit("Missing data/model.joblib -- run 00_generate_data/00_generate_data.py first.")

    workspace = os.getenv("COMET_WORKSPACE")
    api = comet_ml.API()

    for entry in VERSION_PLAN:
        # A fresh experiment per version -- log_model() attaches the artifact
        # to this experiment, then register_model() promotes it into the
        # registry. Both calls are made on the SAME experiment object; the
        # experiment itself is just a vehicle for the upload here, not
        # something this demo otherwise uses (no metrics/params logged).
        experiment = comet_ml.start(project_name=config.COMET_PROJECT_NAME)
        experiment.log_model(config.MPM_MODEL_NAME, str(config.MODEL_PATH))
        experiment.register_model(
            config.MPM_MODEL_NAME,
            version=entry["version"],
            registry_name=config.MPM_MODEL_NAME,
            comment=entry["comment"],
            tags=entry["tags"],
            sync=True,
        )
        experiment.end()

        # register_model() can silently no-op if Step 01 already caused MPM
        # to auto-create a bare version for this string first -- see module
        # docstring. Verify the comment actually attached; if not, patch it
        # onto the existing version instead of assuming success.
        details = api.get_registry_model_details(workspace, config.MPM_MODEL_NAME)
        existing = next((v for v in details["versions"] if v["version"] == entry["version"]), None)
        if not existing or not existing.get("comment"):
            print(
                f"  register_model()'s metadata didn't attach for v{entry['version']} "
                f"(likely collided with a bare version MPM auto-created from Step 01's "
                f"events) -- patching comment/tags onto the existing version instead."
            )
            api.update_registry_model_version(workspace, config.MPM_MODEL_NAME, entry["version"], comment=entry["comment"])
            model = api.get_model(workspace=workspace, model_name=config.MPM_MODEL_NAME)
            for tag in entry["tags"]:
                model.add_tag(entry["version"], tag)

        print(f"Registered {config.MPM_MODEL_NAME} v{entry['version']} (tag: {entry['tags'][0]}).")

    versions = api.get_registry_model_versions(workspace=workspace, registry_name=config.MPM_MODEL_NAME)
    print(f"\n{config.MPM_MODEL_NAME} version history now shows: {versions}")
    print(
        "\nOpen the Model Registry page in Comet to see both versions with their comments -- "
        "compare their order/comments against the MPM dashboard's drift timeline from Steps "
        "01-03 (same day numbers, same incident)."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the registration plan, send nothing to Comet.")
    args = parser.parse_args()

    no_creds = not (os.getenv("COMET_API_KEY") and os.getenv("COMET_WORKSPACE"))
    if args.dry_run or no_creds:
        if no_creds and not args.dry_run:
            print("No COMET_API_KEY/COMET_WORKSPACE set -- falling back to --dry-run.")
        run_dry_run()
    else:
        run_live()
        print("\nSee 04_model_registry.md for the UI checklist.")


if __name__ == "__main__":
    main()
