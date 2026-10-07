# 本模块为 GraphRAG 提供阶段进度统计，并将真实计数送入统一监控日志。
# 原生 callback 行为保持兼容，结构化日志可在没有 callback 时独立使用。
# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Progress Logging Utilities."""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


@dataclass
class Progress:
    """A class representing the progress of a task."""

    description: str | None = None
    """Description of the progress"""

    total_items: int | None = None
    """Total number of items"""

    completed_items: int | None = None
    """Number of items completed"""


ProgressHandler = Callable[[Progress], None]
"""A function to handle progress reports."""


class ProgressTicker:
    """A class that emits progress reports incrementally."""

    _callback: ProgressHandler | None
    _description: str
    _num_total: int
    _num_complete: int

    def __init__(
        self, callback: ProgressHandler | None, num_total: int, description: str = ""
    ):
        self._callback = callback
        self._description = description
        self._num_total = num_total
        self._num_complete = 0

    def __call__(self, num_ticks: int = 1) -> None:
        """Emit progress and report its real count to the unified monitor."""
        # 以中文说明：每次推进时同步发出可机器解析的结构化进度记录。
        self._num_complete += num_ticks
        progress = Progress(
            total_items=self._num_total,
            completed_items=self._num_complete,
            description=self._description,
        )
        logging.getLogger("dataweaver.progress").info(
            "baseline progress",
            extra={
                "progress_event": {
                    "schema_version": 1,
                    "stage": _monitor_stage(self._description),
                    "native_stage": self._description or "workflow",
                    "status": "running",
                    "current": self._num_complete,
                    "total": self._num_total,
                    "unit": "items",
                    "message": self._description or "workflow progress",
                }
            },
        )
        if self._callback is not None:
            if progress.description:
                logger.info("%s%s/%s", progress.description, progress.completed_items, progress.total_items)
            self._callback(progress)

    def done(self) -> None:
        """标记进度阶段完成并发出最终结构化计数。"""
        logging.getLogger("dataweaver.progress").info(
            "baseline progress",
            extra={
                "progress_event": {
                    "schema_version": 1,
                    "stage": _monitor_stage(self._description),
                    "native_stage": self._description or "workflow",
                    "status": "completed",
                    "current": self._num_total,
                    "total": self._num_total,
                    "unit": "items",
                    "message": self._description or "workflow completed",
                }
            },
        )
        if self._callback is not None:
            self._callback(
                Progress(
                    total_items=self._num_total,
                    completed_items=self._num_total,
                    description=self._description,
                )
            )


def _monitor_stage(description: str) -> str:
    """根据 GraphRAG 阶段名称映射公共 monitor 阶段。"""
    normalized = description.lower()
    if "embed" in normalized:
        return "embedding"
    if "chunk" in normalized or "text unit" in normalized:
        return "chunking"
    if any(token in normalized for token in ("write", "persist", "index")):
        return "index_write"
    if any(token in normalized for token in ("extract", "graph", "entity", "relation", "community")):
        return "graph_extract"
    return "workflow"


def progress_ticker(
    callback: ProgressHandler | None, num_total: int, description: str = ""
) -> ProgressTicker:
    """Create a progress ticker."""
    return ProgressTicker(callback, num_total, description=description)


def progress_iterable(
    iterable: Iterable[T],
    progress: ProgressHandler | None,
    num_total: int | None = None,
    description: str = "",
) -> Iterable[T]:
    """Wrap an iterable with a progress handler. Every time an item is yielded, the progress handler will be called with the current progress."""
    if num_total is None:
        num_total = len(list(iterable))

    tick = ProgressTicker(progress, num_total, description=description)

    for item in iterable:
        tick(1)
        yield item
