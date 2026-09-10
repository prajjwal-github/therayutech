"""
Loads protocols_seed.yaml into the catalogue tables.

Idempotent and safe to re-run: everything upserts on `code`, so editing a target
in the YAML and running this again updates the catalogue without disturbing a
single patient record. Protocol rows for a condition are replaced wholesale,
which is what you want when an exercise is removed from a protocol.

    python -m records.seed                 # default database
    python -m records.seed --db path.db    # somewhere else
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Dict

from .db import Database, get_db

_SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "protocols_seed.yaml")


def load_seed_file(path: str = _SEED_PATH) -> Dict[str, Any]:
    # Imported here rather than at module scope on purpose. records/__init__.py
    # re-exports seed(), so a top-level `import yaml` meant a machine without
    # PyYAML could not import the records package AT ALL - losing recording and
    # reporting, neither of which touch YAML. Only this function needs it.
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "PyYAML is required to load the protocol seed file. "
            "Install it with:  python -m pip install pyyaml"
        ) from exc

    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def seed(db: Database, path: str = _SEED_PATH, verbose: bool = True) -> Dict[str, int]:
    data = load_seed_file(path)
    counts = {"exercises": 0, "conditions": 0, "protocol_rows": 0}

    # -- exercises ------------------------------------------------------------
    for ex in data.get("exercises", []):
        db.execute(
            """
            INSERT INTO exercises
                (code, name, body_mode, primary_joint, mirror_joint,
                 movement_type, goal, instructions)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(code) DO UPDATE SET
                name          = excluded.name,
                body_mode     = excluded.body_mode,
                primary_joint = excluded.primary_joint,
                mirror_joint  = excluded.mirror_joint,
                movement_type = excluded.movement_type,
                goal          = excluded.goal,
                instructions  = excluded.instructions
            """,
            (
                ex["code"], ex["name"], ex["body_mode"], ex["primary_joint"],
                ex.get("mirror_joint"), ex.get("movement_type", "REP"),
                ex.get("goal", "INCREASE"),
                (ex.get("instructions") or "").strip(),
            ),
        )
        counts["exercises"] += 1

    ex_ids = {r["code"]: r["id"] for r in db.query("SELECT id, code FROM exercises")}

    # -- conditions and their protocols --------------------------------------
    for cond in data.get("conditions", []):
        db.execute(
            """
            INSERT INTO conditions (code, name, body_region, description)
            VALUES (?,?,?,?)
            ON CONFLICT(code) DO UPDATE SET
                name        = excluded.name,
                body_region = excluded.body_region,
                description = excluded.description
            """,
            (cond["code"], cond["name"], cond["body_region"],
             (cond.get("description") or "").strip()),
        )
        cond_id = db.query_one("SELECT id FROM conditions WHERE code = ?",
                               (cond["code"],))["id"]
        counts["conditions"] += 1

        # Replace the protocol wholesale so removing an exercise from the YAML
        # actually removes it. Patient records reference exercises directly, not
        # protocol rows, so nothing historical is harmed by this.
        db.execute("DELETE FROM protocols WHERE condition_id = ?", (cond_id,))

        for seq, row in enumerate(cond.get("protocol", []), start=1):
            code = row["exercise"]
            if code not in ex_ids:
                raise ValueError(
                    f"condition {cond['code']} prescribes unknown exercise {code!r}"
                )
            db.execute(
                """
                INSERT INTO protocols
                    (condition_id, exercise_id, sequence, target_rom_deg,
                     target_reps, target_hold_sec, band_min_deg, band_max_deg)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (cond_id, ex_ids[code], seq, row.get("target_rom_deg"),
                 row.get("target_reps"), row.get("target_hold_sec"),
                 row.get("band_min_deg"), row.get("band_max_deg")),
            )
            counts["protocol_rows"] += 1

    if verbose:
        print(f"seeded  exercises={counts['exercises']}  "
              f"conditions={counts['conditions']}  "
              f"protocol_rows={counts['protocol_rows']}")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed the Therayu catalogue.")
    ap.add_argument("--db", default=None, help="path to the SQLite file")
    ap.add_argument("--file", default=_SEED_PATH, help="path to the seed YAML")
    args = ap.parse_args()

    db = get_db(args.db)
    seed(db, args.file)
    print(f"database: {db.path}")


if __name__ == "__main__":
    main()
