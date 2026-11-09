"""冒泡排序实现。

提供:
    bubble_sort(data)     -> 返回新的已排序列表，不修改入参
    bubble_sort_inplace(data) -> 原地排序并返回同一个列表
"""

from typing import Iterable, List, TypeVar

T = TypeVar("T")


def bubble_sort(data: Iterable) -> List:
    """返回 data 的升序排序副本（冒泡排序）。

    入参不会被修改。元素之间必须可比较 (支持 < 运算)。
    """
    result = list(data)
    _bubble_sort_inplace(result)
    return result


def bubble_sort_inplace(data: List) -> List:
    """对列表就地升序冒泡排序，返回同一个列表对象。"""
    _bubble_sort_inplace(data)
    return data


def _bubble_sort_inplace(items: List) -> None:
    n = len(items)
    # 每轮把最大的元素“冒”到末尾；若某轮无交换说明已有序，可提前退出。
    for i in range(n - 1):
        swapped = False
        for j in range(n - 1 - i):
            if items[j + 1] < items[j]:
                items[j], items[j + 1] = items[j + 1], items[j]
                swapped = True
        if not swapped:
            break


if __name__ == "__main__":
    demo = [5, 1, 4, 2, 8, 0, 2]
    print("原始:", demo)
    print("排序:", bubble_sort(demo))
    print("原始未被修改:", demo)
