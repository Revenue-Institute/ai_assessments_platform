"""Zod -> JSON Schema -> Pydantic codegen pipeline (spec §5).

The single point that closes the three-source-of-truth drift problem
documented in the architecture audit (2026-05-26). One canonical
authoring layer (Zod in `packages/schemas/`) emits JSON Schema, which
generates Pydantic v2 models committed to the tree under
`apps/api/src/ri_assessments_api/generated/`. CI runs this script and
diffs the resulting tree against HEAD; any drift between hand-edited
Zod and the committed Pydantic mirror fails the build.

Pipeline:
  1. `bun run` packages/schemas/scripts/emit-json-schema.ts. Dumps one
     draft-07 JSON Schema per Zod export into a temp directory.
  2. `datamodel-codegen` over those JSON Schemas. Emits Pydantic v2
     models under `apps/api/src/ri_assessments_api/generated/`.
  3. Writes a deterministic `__init__.py` so the generated package
     imports cleanly without import-order surprises.

The hand-authored Pydantic models in `models/` continue to own
service-layer concerns (EmailStr fields, cross-field validators, alias
generators). They should `from ..generated import ...` whenever the
authoritative shape lives in Zod, instead of redefining it. See
`models/interactive.py` for the canonical example.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMAS_PKG = REPO_ROOT / "packages" / "schemas"
OUT_DIR_DEFAULT = (
    REPO_ROOT / "apps" / "api" / "src" / "ri_assessments_api" / "generated"
)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"$ {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, check=True, cwd=cwd)


def _write_init(out: Path) -> None:
    """Idempotent __init__.py. datamodel-codegen creates per-schema
    modules but doesn't emit a package __init__, so we write one with
    a stable header that doubles as a "do not edit" sentinel."""

    init_path = out / "__init__.py"
    header = (
        '"""Generated Pydantic v2 models from packages/schemas (Zod).\n'
        '\n'
        'Do NOT edit by hand. Regenerate with:\n'
        '    bash apps/api/scripts/gen_schemas.sh\n'
        '\n'
        'The CI `schemas-codegen` job diffs this tree against HEAD; any\n'
        'drift between Zod and these models fails the build.\n'
        '"""\n'
    )
    init_path.write_text(header)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_DIR_DEFAULT,
        help="Directory to write Pydantic models into (overwritten).",
    )
    args = parser.parse_args()

    if not shutil.which("bun"):
        print(
            "error: bun is required for the Zod -> JSON Schema step.",
            file=sys.stderr,
        )
        return 2

    if not shutil.which("datamodel-codegen"):
        print(
            "error: datamodel-code-generator is missing. "
            "Run `uv sync --group dev` in apps/api first.",
            file=sys.stderr,
        )
        return 2

    out: Path = args.out
    if out.exists():
        # Wipe the previous generation so removed Zod exports do not
        # leave orphan modules behind. The committed tree is the only
        # source of truth for what's "in" the generated package.
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ri-schemas-") as tmp:
        tmp_path = Path(tmp)
        _run(
            [
                "bun",
                str(SCHEMAS_PKG / "scripts" / "emit-json-schema.ts"),
                str(tmp_path),
            ],
            cwd=SCHEMAS_PKG,
        )

        # datamodel-code-generator writes one Python module per input
        # file when --input is a directory.
        _run(
            [
                "datamodel-codegen",
                "--input",
                str(tmp_path),
                "--input-file-type",
                "jsonschema",
                "--output",
                str(out),
                "--output-model-type",
                "pydantic_v2.BaseModel",
                "--target-python-version",
                "3.12",
                "--use-standard-collections",
                "--use-union-operator",
                "--field-constraints",
                "--snake-case-field",
                "--use-double-quotes",
                "--use-default",
                "--disable-timestamp",
            ]
        )

    _write_init(out)
    print(f"gen_schemas.py: wrote Pydantic models to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
