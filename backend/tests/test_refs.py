from __future__ import annotations

import pytest

from app.agent.refs import resolve_refs
from app.tools.errors import RefResolutionError


def test_resolve_nested_references():
    observations = {
        "s1": {"density_kg_m3": 997.0, "nested": {"x": 2}, "items": [10, 20]}
    }
    args = {
        "density": "${s1.density_kg_m3}",
        "nested": "${s1.nested.x}",
        "items": ["${s1.items.1}"],
    }
    assert resolve_refs(args, observations) == {
        "density": 997.0,
        "nested": 2,
        "items": [20],
    }


def test_plain_strings_are_untouched():
    assert resolve_refs("${not_a_ref", {}) == "${not_a_ref"
    assert resolve_refs("hello", {}) == "hello"


def test_missing_step_raises():
    with pytest.raises(RefResolutionError):
        resolve_refs({"x": "${s9.value}"}, {"s1": {"value": 1}})


def test_missing_field_raises():
    with pytest.raises(RefResolutionError):
        resolve_refs({"x": "${s1.missing}"}, {"s1": {"value": 1}})
