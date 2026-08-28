"""Command-line adapter; rendering lives in :mod:`pymaiview.core`."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .core import PyMaiView, RenderError


def _default_zip(root: Path) -> Path:
    preferred = root / "TECHNOPOLIS 1042.5.zip"
    if preferred.is_file():
        return preferred
    archives = sorted(root.glob("*.zip"))
    if len(archives) == 1:
        return archives[0]
    if not archives:
        raise RenderError("请指定输入 zip，或在当前目录放入唯一的 *.zip")
    raise RenderError("找到多个 zip，请明确指定输入文件：" + ", ".join(p.name for p in archives))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="pymaiview", description="导出 maimai 谱面确认视频")
    parser.add_argument("input", nargs="?", type=Path, help="Web mai Chart X 工程 zip")
    parser.add_argument("-o", "--output", type=Path, default=Path("output.mp4"))
    parser.add_argument("--skin", type=Path, help="自定义 skin 目录")
    parser.add_argument("--difficulty", type=int, default=5)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--speed", type=float)
    parser.add_argument("--touch-speed", type=float)
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--no-sfx", action="store_true")
    parser.add_argument("--no-intro", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)

    playback = {
        key: value
        for key, value in {
            "speed": args.speed,
            "touchSpeed": args.touch_speed,
        }.items()
        if value is not None
    }
    try:
        with PyMaiView.from_zip(
            args.input or _default_zip(Path.cwd()),
            skin=args.skin,
            difficulty=args.difficulty,
            playback=playback,
        ) as view:
            view.render(
                args.output,
                width=args.width,
                height=args.height,
                fps=args.fps,
                start=args.start,
                end=args.end,
                include_audio=not args.no_audio,
                include_sfx=not args.no_sfx,
                include_intro=not args.no_intro,
                headed=args.headed,
            )
    except RenderError as exc:
        parser.exit(2, f"pymaiview: error: {exc}\n")
    print(f"已输出：{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
