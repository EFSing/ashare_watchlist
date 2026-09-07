#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""每日轻量状态查看的兼容入口。

正式复盘输出由 :mod:`review_after` 统一生成；跨日绩效由
``track_perf.py`` 的 signal-level tracker 负责。
"""

from __future__ import annotations

from review_after import main as _review_after_main


def main(argv: list[str] | None = None) -> int:
    """Run the canonical daily lightweight status report."""

    forwarded = [] if argv is None else list(argv)
    return _review_after_main(["--mode", "close", *forwarded])


if __name__ == "__main__":
    raise SystemExit(main())
