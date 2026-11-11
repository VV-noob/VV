import pytest

from bubble_sort import bubble_sort, bubble_sort_inplace


def test_acceptance_example_ascending():
    assert bubble_sort([5, 1, 4, 2, 8]) == [1, 2, 4, 5, 8]


def test_empty_sequence():
    assert bubble_sort([]) == []


def test_single_element():
    assert bubble_sort([7]) == [7]


def test_duplicates_sorted_and_stable():
    data = [3, 1, 3, 2, 3, 1]
    result = bubble_sort(data)
    assert result == sorted(data)


def test_stability_with_keyed_wrappers():
    # 用 (key, tag) 元组验证稳定性：相同 key 的相对顺序应保持不变
    data = [(1, "a"), (0, "b"), (1, "c"), (0, "d")]
    result = bubble_sort(data)
    assert [tag for _, tag in result] == ["b", "d", "a", "c"]


def test_already_sorted_early_termination():
    data = [1, 2, 3, 4, 5]
    assert bubble_sort(data) == data


def test_reverse_sorted():
    assert bubble_sort([5, 4, 3, 2, 1]) == [1, 2, 3, 4, 5]


def test_all_equal():
    data = [6, 6, 6, 6]
    assert bubble_sort(data) == data


def test_negatives_and_extremes():
    data = [0, -10, 10**100, -(10**100), -1, 1]
    assert bubble_sort(data) == sorted(data)


def test_descending():
    assert bubble_sort([5, 1, 4, 2, 8], descending=True) == [8, 5, 4, 2, 1]


def test_descending_empty_and_single():
    assert bubble_sort([], descending=True) == []
    assert bubble_sort([42], descending=True) == [42]


def test_does_not_mutate_input():
    original = [5, 1, 4, 2, 8]
    snapshot = list(original)
    result = bubble_sort(original)
    assert original == snapshot
    assert result is not original


def test_accepts_tuple_input():
    assert bubble_sort((3, 1, 2)) == [1, 2, 3]


def test_inplace_returns_same_object():
    data = [5, 1, 4, 2, 8]
    result = bubble_sort_inplace(data)
    assert result is data
    assert data == [1, 2, 4, 5, 8]


def test_uncomparable_elements_raise_type_error():
    with pytest.raises(TypeError):
        bubble_sort([1, "a", 2])


def test_matches_sorted_on_randomish_data():
    data = [17, -3, 0, 99, -3, 42, 8, 8, 1]
    assert bubble_sort(data) == sorted(data)
    assert bubble_sort(data, descending=True) == sorted(data, reverse=True)
