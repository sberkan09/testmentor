"""Output schemas of the model stages. JSON schemas sent to the engine derive from these models.

Label lists (verification methods, test types, priorities) come from the project configuration,
so the models are built by factories instead of being fixed at import time.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model


class Requirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    language: str = ""


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    no: int = Field(ge=1)
    action: str = Field(min_length=1)
    expected: str = Field(min_length=1)


def _enum(name: str, values: tuple[str, ...]) -> type[Enum]:
    return Enum(name, {f"v{i}": v for i, v in enumerate(values)}, type=str)  # type: ignore[return-value]


@lru_cache(maxsize=32)
def test_case_model(types: tuple[str, ...], priorities: tuple[str, ...]) -> type[BaseModel]:
    """One test case. Every step carries its own expected result."""
    test_type = _enum("TestType", types)
    priority = _enum("Priority", priorities)
    return create_model(
        "TestCase",
        __config__=ConfigDict(extra="forbid"),
        id=(str, Field(min_length=1)),
        title=(str, Field(min_length=1)),
        covers=(list[str], Field(min_length=1)),
        type=(test_type, ...),
        priority=(priority, ...),
        preconditions=(str, ...),
        test_inputs=(str, ...),
        assumptions=(str, ...),
        steps=(list[Step], Field(min_length=1)),
    )


@lru_cache(maxsize=32)
def case_set_model(types: tuple[str, ...], priorities: tuple[str, ...]) -> type[BaseModel]:
    """`{"test_cases": [...]}`: full generation, repair and each part of a split cluster."""
    test_case = test_case_model(types, priorities)
    # At least one test: generation is only called for clusters that need tests, and an empty
    # list let the model skip a cluster entirely (paket 1, D2 first runs).
    return create_model(
        "TestCaseSet",
        __config__=ConfigDict(extra="forbid"),
        test_cases=(list[test_case], Field(min_length=1)),  # type: ignore[valid-type]
    )


@lru_cache(maxsize=32)
def incremental_model(types: tuple[str, ...], priorities: tuple[str, ...]) -> type[BaseModel]:
    """`{"add": [...], "update": [...]}`: incremental generation (paket 3). `update` items carry
    the id of an existing case and are its complete new version; both lists may be empty."""
    test_case = test_case_model(types, priorities)
    return create_model(
        "TestCaseDelta",
        __config__=ConfigDict(extra="forbid"),
        add=(list[test_case], ...),  # type: ignore[valid-type]
        update=(list[test_case], ...),  # type: ignore[valid-type]
    )


class MergeDecision(BaseModel):
    """`{"drop": [...]}`: ids of duplicate cases to remove when two sets are merged."""

    model_config = ConfigDict(extra="forbid")

    drop: list[str]


class ClusterLabel(BaseModel):
    """Cluster name (3–6 words) and a one-sentence rationale."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    rationale: str


@lru_cache(maxsize=32)
def method_batch_model(methods: tuple[str, ...]) -> type[BaseModel]:
    """`{"decisions": [{"requirement_id", "methods", "rationale"}]}`."""
    method = _enum("Method", methods)
    decision = create_model(
        "MethodDecision",
        __config__=ConfigDict(extra="forbid"),
        requirement_id=(str, Field(min_length=1)),
        methods=(list[method], Field(min_length=1)),  # type: ignore[valid-type]
        rationale=(str, ...),
    )
    return create_model(
        "MethodBatch",
        __config__=ConfigDict(extra="forbid"),
        decisions=(list[decision], ...),  # type: ignore[valid-type]
    )


def plain(obj: Any) -> Any:
    """Pydantic output (with enums) to plain JSON data."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return obj
