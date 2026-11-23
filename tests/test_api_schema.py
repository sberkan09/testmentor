"""The committed API schema (api/schema.json) matches worker/contracts.py."""

from api.export_schema import OUT, render


def test_schema_file_is_current():
    assert OUT.read_text(encoding="utf-8") == render(), "run: uv run python -m api.export_schema"
