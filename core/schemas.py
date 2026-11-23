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


Limits = tuple[tuple[str, int], ...]
"""(field, maxLength) pairs, sorted; empty: no limit. Paket 3b (KDH-030)."""


def _text(limits: dict[str, int], name: str, min_length: int = 0) -> Any:
    kw: dict[str, Any] = {}
    if min_length:
        kw["min_length"] = min_length
    if name in limits:
        kw["max_length"] = limits[name]
    return (str, Field(**kw)) if kw else (str, ...)


@lru_cache(maxsize=32)
def _step_model(limits: Limits = ()) -> type[BaseModel]:
    """`Step` with the `action` and `expected` limits; without limits `Step` itself."""
    if not limits:
        return Step
    lim = dict(limits)
    return create_model(
        "Step",
        __config__=ConfigDict(extra="forbid"),
        no=(int, Field(ge=1)),
        action=_text(lim, "action", 1),
        expected=_text(lim, "expected", 1),
    )


@lru_cache(maxsize=32)
def _test_case_model(
    types: tuple[str, ...], priorities: tuple[str, ...], limits: Limits = ()
) -> type[BaseModel]:
    """One test case. Every step carries its own expected result. `limits`: `maxLength` of the
    text fields (paket 3b)."""
    test_type = _enum("TestType", types)
    priority = _enum("Priority", priorities)
    lim = dict(limits)
    return create_model(
        "TestCase",
        __config__=ConfigDict(extra="forbid"),
        id=(str, Field(min_length=1)),
        title=_text(lim, "title", 1),
        covers=(list[str], Field(min_length=1)),
        type=(test_type, ...),
        priority=(priority, ...),
        preconditions=_text(lim, "preconditions"),
        test_inputs=_text(lim, "test_inputs"),
        assumptions=_text(lim, "assumptions"),
        steps=(list[_step_model(limits)], Field(min_length=1)),  # type: ignore[valid-type]
    )


@lru_cache(maxsize=32)
def _case_set_model(
    types: tuple[str, ...], priorities: tuple[str, ...], limits: Limits = ()
) -> type[BaseModel]:
    """`{"test_cases": [...]}`: full generation, repair and each part of a split cluster."""
    test_case = _test_case_model(types, priorities, limits)
    # At least one test: generation is only called for clusters that need tests, and an empty
    # list let the model skip a cluster entirely (paket 1, D2 first runs).
    return create_model(
        "TestCaseSet",
        __config__=ConfigDict(extra="forbid"),
        test_cases=(list[test_case], Field(min_length=1)),  # type: ignore[valid-type]
    )


@lru_cache(maxsize=32)
def _incremental_model(
    types: tuple[str, ...], priorities: tuple[str, ...], limits: Limits = ()
) -> type[BaseModel]:
    """`{"add": [...], "update": [...]}`: incremental generation (paket 3). `update` items carry
    the id of an existing case and are its complete new version; both lists may be empty."""
    test_case = _test_case_model(types, priorities, limits)
    return create_model(
        "TestCaseDelta",
        __config__=ConfigDict(extra="forbid"),
        add=(list[test_case], ...),  # type: ignore[valid-type]
        update=(list[test_case], ...),  # type: ignore[valid-type]
    )


# Public factories: `limits` normalised (sorted tuple) before the cache, so that a call without
# limits and one with `()` return the same class.


def step_model(limits: Limits = ()) -> type[BaseModel]:
    return _step_model(tuple(sorted(limits)))


def test_case_model(
    types: tuple[str, ...], priorities: tuple[str, ...], limits: Limits = ()
) -> type[BaseModel]:
    return _test_case_model(tuple(types), tuple(priorities), tuple(sorted(limits)))


def case_set_model(
    types: tuple[str, ...], priorities: tuple[str, ...], limits: Limits = ()
) -> type[BaseModel]:
    return _case_set_model(tuple(types), tuple(priorities), tuple(sorted(limits)))


def incremental_model(
    types: tuple[str, ...], priorities: tuple[str, ...], limits: Limits = ()
) -> type[BaseModel]:
    return _incremental_model(tuple(types), tuple(priorities), tuple(sorted(limits)))


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
