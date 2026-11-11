"""冒泡排序实现。

仅支持元素之间可比较（支持 ``<`` 运算符）的一维序列；
元素不可比较时，Python 原生比较异常（TypeError）会向上抛出。
"""

from __future__ import annotations

from typing import Any, List, Sequence


def bubble_sort(sequence: Sequence[Any], descending: bool = False) -> List[Any]:
    """对一维序列进行冒泡排序，返回新列表，不修改输入序列。

    参数:
        sequence: 一维可比较元素序列（list / tuple 等）。
        descending: 为 True 时降序排序，默认 False 升序。

    返回:
        排序后的新列表。

    异常:
        TypeError: 当元素之间不可比较时（由 Python 原生比较抛出）。
    """
    result = list(sequence)
    n = len(result)
    if n < 2:
        return result

    def should_swap(left: Any, right: Any) -> bool:
        if descending:
            return left < right
        return left > right

    for i in range(n - 1):
        swapped = False
        # 每轮结束后末尾 i 个元素已就位
        for j in range(n - 1 - i):
            if should_swap(result[j], result[j + 1]):
                result[j], result[j + 1] = result[j + 1], result[j]
                swapped = True
        if not swapped:
            # 提前终止：本轮无交换，序列已有序
            break

    return result


def bubble_sort_inplace(sequence: List[Any], descending: bool = False) -> List[Any]:
    """就地冒泡排序，返回同一个列表对象。"""
    n = len(sequence)
    if n < 2:
        return sequence

    def should_swap(left: Any, right: Any) -> bool:
        if descending:
            return left < right
        return left > right

    for i in range(n - 1):
        swapped = False
        for j in range(n - 1 - i):
            if should_swap(sequence[j], sequence[j + 1]):
                sequence[j], sequence[j + 1] = sequence[j + 1], sequence[j]
                swapped = True
        if not swapped:
            break
    return sequence


if __name__ == "__main__":
    sample = [5, 1, 4, 2, 8]
    print("ascending:", bubble_sort(sample))
    print("descending:", bubble_sort(sample, descending=True))
    print("original unchanged:", sample)
