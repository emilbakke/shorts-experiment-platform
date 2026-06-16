from __future__ import annotations

import itertools
from typing import Literal

Condition = Literal["control_recommendation", "treatment_search", "treatment_problematic_content"]
ContentPool = Literal["safe", "problematic"]
PoolMode = Literal["safe", "problematic", "mixed"]

CONDITIONS: tuple[str, ...] = (
    "control_recommendation",
    "treatment_search",
    "treatment_problematic_content",
)
CONTENT_POOLS: tuple[str, ...] = ("safe", "problematic")
POOL_MODES: tuple[str, ...] = ("safe", "problematic", "mixed")

_assignment_cycle = itertools.cycle(CONDITIONS)


def normalize_condition(condition: str | None) -> str:
    if condition in CONDITIONS:
        return condition
    return "control_recommendation"


def assign_condition(requested: str | None = None) -> str:
    if requested in CONDITIONS:
        return requested
    return next(_assignment_cycle)


def normalize_pool_mode(mode: str | None, condition: str | None = None) -> str:
    if mode in POOL_MODES:
        return mode
    normalized = normalize_condition(condition)
    if normalized == "treatment_problematic_content":
        return "mixed"
    return "safe"


def validate_condition(condition: str) -> None:
    if condition not in CONDITIONS:
        raise ValueError("condition must be control_recommendation, treatment_search, or treatment_problematic_content")


def validate_content_pool(content_pool: str) -> None:
    if content_pool not in CONTENT_POOLS:
        raise ValueError("content_pool must be safe or problematic")
