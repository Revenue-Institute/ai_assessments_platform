"""Zod → JSON Schema → Pydantic codegen (spec §5).

TODO: full pipeline. Steps:
  1. Run a Bun script in packages/schemas that uses zod-to-json-schema to
     emit JSON Schema files per Zod export to a temp directory.
  2. Run datamodel-code-generator over those JSON Schemas, writing Pydantic
     v2 models into apps/api/src/ri_assessments_api/generated/schemas/.
  3. Wire as a pre-commit hook so the generated tree never drifts.

Until that lands, hand-write Pydantic models in
apps/api/src/ri_assessments_api/models/ (not yet created)."""

import sys


def main() -> int:
    print(
        "gen_schemas.py: codegen pipeline not yet implemented. "
        "See apps/api/scripts/gen_schemas.py docstring.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
