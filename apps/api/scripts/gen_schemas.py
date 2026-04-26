"""Zod -> JSON Schema -> Pydantic codegen pipeline (spec §5).

Steps:
  1. Run packages/schemas/scripts/emit-json-schema.ts via Bun. It walks
     every Zod export in @repo/schemas and dumps draft-07 JSON Schemas
     into a temp directory.
  2. Run datamodel-code-generator over those JSON Schemas, emitting
     Pydantic v2 models into apps/api/src/ri_assessments_api/generated/.

Why generate? Spec §5 makes Zod the single source of truth so the API and
the UI cannot disagree about request/response shapes. The generated tree
is gitignored; CI regenerates on every PR and fails if the diff is
non-empty.

Idempotent: rerunning produces a deterministic tree. Safe to wire as a
pre-commit hook or a CI step.
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

        out: Path = args.out
        out.mkdir(parents=True, exist_ok=True)
        # datamodel-code-generator writes one Python module per input file
        # when --input is a directory.
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
            ]
        )

        init_path = out / "__init__.py"
        if not init_path.exists():
            init_path.write_text(
                '"""Generated Pydantic v2 models. Do not edit by hand;'
                ' run `bash apps/api/scripts/gen_schemas.sh` to regenerate."""\n'
            )

    print(f"gen_schemas.py: wrote Pydantic models to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
