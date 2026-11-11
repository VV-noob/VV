"""归并排序实现（分治法，稳定，非原地）。

功能要点：
- MS-01 分解：递归二分，中点取 floor。
- MS-02 合并：线性合并两个有序子序列。
- MS-03 稳定性：相等元素优先取左侧。
- MS-04 边界处理：空 / 单元素 / 重复 / 负数与极值 / 非 2 的幂长度。
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

__all__ = ["merge_sort", "merge", "is_sorted"]


def _default_key(x: Any) -> Any:
    return x


def merge(
    left: Sequence[Any],
    right: Sequence[Any],
    key: Callable[[Any], Any] = _default_key,
    reverse: bool = False,
) -> List[Any]:
    """合并两个已排序序列，返回新的有序列表。

    相等元素（key 相等）时优先取左侧元素，以保证排序稳定性。
    """
    result: List[Any] = []
    i = 0
    j = 0
    n_left = len(left)
    n_right = len(right)

    while i < n_left and j < n_right:
        left_key = key(left[i])
        right_key = key(right[j])
        # 稳定性关键：相等时取左侧（<=），降序时取右侧保持稳定（>=）
        if (left_key <= right_key) if not reverse else (left_key >= right_key):
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1

    if i < n_left:
        result.extend(left[i:])
    if j < n_right:
        result.extend(right[j:])

    return result


def merge_sort(
    seq: Sequence[Any],
    key: Optional[Callable[[Any], Any]] = None,
    reverse: bool = False,
) -> List[Any]:
    """对序列进行归并排序，返回升序（或降序）新列表。

    参数：
        seq: 待排序序列，不会被修改。
        key: 可选比较键函数，默认按自然顺序比较。
        reverse: 为 True 时按降序排序（仍保持稳定性）。

    返回：
        与输入等长的新列表，是输入元素的一个排列。
    """
    if seq is None:
        raise TypeError("seq 不能为 None")

    key_func = _default_key if key is None else key
    items = list(seq)  # 拷贝，保证不修改调用方传入的原序列

    if len(items) <= 1:
        return items

    mid = len(items) // 2  # 中点取 floor，非 2 的幂长度也正确二分
    left = merge_sort(items[:mid], key=key_func, reverse=reverse)
    right = merge_sort(items[mid:], key=key_func, reverse=reverse)
    return merge(left, right, key=key_func, reverse=reverse)


def is_sorted(
    seq: Sequence[Any],
    key: Optional[Callable[[Any], Any]] = None,
    reverse: bool = False,
) -> bool:
    """辅助函数：判断序列是否按要求有序。"""
    key_func = _default_key if key is None else key
    items = list(seq)
    for a, b in zip(items, items[1:]):
        ka, kb = key_func(a), key_func(b)
        if not reverse and ka > kb:
            return False
        if reverse and ka < kb:
            return False
    return True
