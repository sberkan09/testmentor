import hashlib

import numpy as np
import pytest

from core.hashing import canonical, input_hash, plain_hash
from core.nodes import ClusterContent


def test_input_hash_output_is_pinned():
    """The judge cache and recorded runs are keyed by this exact digest; it must never change."""
    h = input_hash(inputs=["a", {"b": 1}], prompt_version="p1", model="m", params={"t": 0})
    assert h == "26dbe30c0804275652bb1b8eeac03330f5d005966c8caa14a938e8a4538a9c55"


def test_plain_hash_matches_canonical_for_plain_data():
    obj = {"b": [1, 2.5, "ş"], "a": None, "c": True}
    assert plain_hash(obj) == hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def test_plain_hash_ignores_key_order():
    assert plain_hash({"a": 1, "b": 2}) == plain_hash({"b": 2, "a": 1})


@pytest.mark.parametrize("bad", [{"R1", "R2"}, np.array([1.0, 2.0]), object()])
def test_plain_hash_rejects_non_plain_values(bad):
    with pytest.raises(TypeError):
        plain_hash({"x": bad})


def test_cluster_members_are_canonical():
    assert ClusterContent(members=("R2", "R1", "R2")).members == ("R1", "R2")
