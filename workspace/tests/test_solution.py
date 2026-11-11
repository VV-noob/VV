"""归并排序验收测试。"""

from __future__ import annotations

import random
import time
from collections import Counter

import pytest

from solution import is_sorted, merge, merge_sort


# ---------- 基本验收：各类输入 ----------

def test_empty_sequence():
    assert merge_sort([]) == []


def test_single_element():
    assert merge_sort([42]) == [42]


def test_two_elements_sorted_and_reversed():
    assert merge_sort([1, 2]) == [1, 2]
    assert merge_sort([2, 1]) == [1, 2]


def test_already_sorted():
    data = [1, 2, 3, 4, 5, 6, 7, 8]
    assert merge_sort(data) == data


def test_reverse_sorted():
    data = [9, 7, 5, 3, 1, -1]
    assert merge_sort(data) == [-1, 1, 3, 5, 7, 9]


def test_duplicates_kept():
    data = [3, 1, 3, 2, 1, 3]
    out = merge_sort(data)
    assert out == [1, 1, 2, 3, 3, 3]
    assert Counter(out) == Counter(data)


def test_negative_and_extremes():
    data = [0, -1, 10**18, -(10**18), -5, 5]
    assert merge_sort(data) == [-(10**18), -5, -1, 0, 5, 10**18]


def test_float_and_none_key():
    data = [2.5, -0.5, 1.0, 0.0]
    assert merge_sort(data) == [-0.5, 0.0, 1.0, 2.5]


@pytest.mark.parametrize("n", [0, 1, 2, 3, 5, 7, 8, 13, 16, 17, 31, 33, 100])
def test_non_power_of_two_lengths(n):
    data = [random.randint(-1000, 1000) for _ in range(n)]
    out = merge_sort(data)
    assert out == sorted(data)
    assert len(out) == n


def test_random_large_correctness_and_multiset():
    rnd = random.Random(20240517)
    data = [rnd.randint(-10**6, 10**6) for _ in range(5000)]
    out = merge_sort(data)
    assert out == sorted(data)
    assert Counter(out) == Counter(data)
    assert is_sorted(out)


# ---------- 不修改原输入 ----------

def test_input_not_mutated():
    data = [5, 2, 9, 1, 5]
    snapshot = list(data)
    out = merge_sort(data)
    assert data == snapshot
    assert out is not data


def test_input_not_mutated_tuple():
    data = (4, 2, 8)
    out = merge_sort(data)
    assert data == (4, 2, 8)
    assert out == [2, 4, 8]


# ---------- 稳定性 ----------

def test_stability_preserves_relative_order():
    # 元素为 (key, tag)，按 key 排序，检查同 key 的 tag 顺序不变
    data = [(1, "a"), (0, "b"), (1, "c"), (0, "d"), (1, "e"), (0, "f")]
    out = merge_sort(data, key=lambda x: x[0])
    tags_by_key = {}
    for k, tag in out:
        tags_by_key.setdefault(k, []).append(tag)
    assert tags_by_key[0] == ["b", "d", "f"]
    assert tags_by_key[1] == ["a", "c", "e"]


def test_stability_with_duplicate_ints_using_index_key():
    data = [3, 1, 2, 1, 3, 2, 1]
    indexed = list(enumerate(data))
    out = merge_sort(indexed, key=lambda p: p[1])
    # 相同值应保持原始索引递增
    for value in set(data):
        idxs = [i for i, v in out if v == value]
        assert idxs == sorted(idxs)


def test_merge_prefers_left_on_equal():
    left = [(1, "L1"), (1, "L2")]
    right = [(1, "R1"), (1, "R2")]
    merged = merge(left, right, key=lambda x: x[0])
    assert [t for _, t in merged] == ["L1", "L2", "R1", "R2"]


# ---------- 自定义比较规则 ----------

def test_reverse_order():
    data = [3, 1, 4, 1, 5, 9, 2, 6]
    assert merge_sort(data, reverse=True) == sorted(data, reverse=True)


def test_key_function_abs_value():
    data = [-5, 3, -1, 4, -2]
    out = merge_sort(data, key=abs)
    assert [abs(x) for x in out] == sorted(abs(x) for x in data)


def test_string_sorting():
    data = ["pear", "apple", "fig", "banana"]
    assert merge_sort(data) == ["apple", "banana", "fig", "pear"]


def test_key_by_length_stability():
    data = ["bb", "a", "cc", "d"]
    out = merge_sort(data, key=len)
    assert out == ["a", "d", "bb", "cc"]


# ---------- 边��异常 ----------

def test_none_input_raises():
    with pytest.raises(TypeError):
        merge_sort(None)


def test_empty_and_single_no_exception():
    assert merge_sort([]) == []
    assert merge_sort([0]) == [0]


# ---------- 复杂度 / 性能 ----------

def test_performance_1e5():
    rnd = random.Random(1)
    data = [rnd.randint(-10**9, 10**9) for _ in range(100_000)]
    start = time.perf_counter()
    out = merge_sort(data)
    elapsed = time.perf_counter() - start
    assert out == sorted(data)
    # O(n log n) 预期：10^5 规模应在宽松阈值内完成
    assert elapsed < 10.0
