import random

import pytest

from bubble_sort import bubble_sort, bubble_sort_inplace


def test_empty():
    assert bubble_sort([]) == []


def test_single():
    assert bubble_sort([42]) == [42]


def test_basic():
    assert bubble_sort([5, 1, 4, 2, 8]) == [1, 2, 4, 5, 8]


def test_already_sorted():
    assert bubble_sort([1, 2, 3, 4]) == [1, 2, 3, 4]


def test_reverse_sorted():
    assert bubble_sort([4, 3, 2, 1]) == [1, 2, 3, 4]


def test_duplicates():
    assert bubble_sort([3, 1, 3, 1, 2]) == [1, 1, 2, 3, 3]


def test_negatives_and_floats():
    assert bubble_sort([0.5, -1.5, 2, -0.0, 1]) == [-1.5, -0.0, 0.5, 1, 2]


def test_does_not_mutate_input():
    data = [3, 2, 1]
    out = bubble_sort(data)
    assert data == [3, 2, 1]
    assert out is not data


def test_inplace_returns_same_object():
    data = [3, 2, 1]
    out = bubble_sort_inplace(data)
    assert out is data
    assert data == [1, 2, 3]


def test_accepts_iterable():
    assert bubble_sort((3, 1, 2)) == [1, 2, 3]
    assert bubble_sort(range(3, 0, -1)) == [1, 2, 3]


def test_strings():
    assert bubble_sort(["pear", "apple", "fig"]) == ["apple", "fig", "pear"]


@pytest.mark.parametrize("seed", range(5))
def test_matches_sorted_random(seed):
    rng = random.Random(seed)
    data = [rng.randint(-50, 50) for _ in range(50)]
    assert bubble_sort(data) == sorted(data)


def test_uncomparable_raises():
    with pytest.raises(TypeError):
        bubble_sort([1, "a"])
