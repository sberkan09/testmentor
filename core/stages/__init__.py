"""Stage declarations. Importing this package registers every built-in stage."""

from core.stages import (  # noqa: F401
    cluster_label,
    clustering,
    embedding,
    matrix,
    method,
    retrieval,
    test_set,
)
from core.stages.base import StageSpec, all_specs, get, register

__all__ = ["StageSpec", "all_specs", "get", "register"]
