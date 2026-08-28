"""Safe, deterministic project archive extraction."""

from __future__ import annotations

import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Iterable, Optional, Union

from .errors import RenderError


PathLike = Union[str, os.PathLike]
MAX_FILES = 4096
MAX_UNCOMPRESSED_BYTES = 4 * 1024**3
MUSIC_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
VIDEO_SUFFIXES = {".avi", ".mkv", ".mov", ".mp4", ".ogv", ".webm"}
IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


@dataclass
class ExtractedProject:
    """Resources extracted from one project archive."""

    root: Path
    maidata: Path
    music: Optional[Path]
    pv: Optional[Path]
    _temporary_directory: TemporaryDirectory

    def close(self) -> None:
        self._temporary_directory.cleanup()


def _validate_members(members: Iterable[zipfile.ZipInfo]) -> list[zipfile.ZipInfo]:
    files = [member for member in members if not member.is_dir()]
    if len(files) > MAX_FILES:
        raise RenderError(f"压缩包文件过多（最多 {MAX_FILES} 个）")
    if sum(member.file_size for member in files) > MAX_UNCOMPRESSED_BYTES:
        raise RenderError("压缩包解压后超过 4 GiB")

    for member in files:
        path = PurePosixPath(member.filename)
        mode = member.external_attr >> 16
        if path.is_absolute() or ".." in path.parts:
            raise RenderError(f"压缩包包含不安全路径：{member.filename}")
        if member.flag_bits & 1:
            raise RenderError(f"不支持加密文件：{member.filename}")
        if stat.S_ISLNK(mode):
            raise RenderError(f"压缩包包含符号链接：{member.filename}")
    return files


def _select(
    files: Iterable[Path],
    label: str,
    stems: set[str],
    suffixes: set[str],
    *,
    required: bool = False,
) -> Optional[Path]:
    candidates = sorted(
        (path for path in files if path.stem.lower() in stems and path.suffix.lower() in suffixes),
        key=lambda path: (len(path.parts), path.as_posix().lower()),
    )
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise RenderError(f"压缩包包含多个 {label}：{names}")
    if candidates:
        return candidates[0]
    if required:
        raise RenderError(f"压缩包缺少 {label}")
    return None


def extract_project(archive: PathLike) -> ExtractedProject:
    """Extract and resolve one Web mai Chart X project archive."""

    archive_path = Path(archive).expanduser().resolve()
    if not archive_path.is_file():
        raise RenderError(f"找不到输入压缩包：{archive_path}")

    temporary_directory = TemporaryDirectory(prefix="pymaiview-")
    root = Path(temporary_directory.name)
    try:
        with zipfile.ZipFile(archive_path) as source:
            members = _validate_members(source.infolist())
            for member in members:
                source.extract(member, root)
        files = [path for path in root.rglob("*") if path.is_file()]
        maidata = _select(files, "maidata.txt", {"maidata"}, {".txt"}, required=True)
        music = _select(files, "音乐文件", {"music", "track"}, MUSIC_SUFFIXES)
        pv = _select(files, "背景文件", {"background", "bg", "pv"}, IMAGE_SUFFIXES | VIDEO_SUFFIXES)
        assert maidata is not None
        return ExtractedProject(root, maidata, music, pv, temporary_directory)
    except RenderError:
        temporary_directory.cleanup()
        raise
    except zipfile.BadZipFile as exc:
        temporary_directory.cleanup()
        raise RenderError(f"不是有效的 zip 压缩包：{archive_path}") from exc
    except Exception as exc:
        temporary_directory.cleanup()
        raise RenderError(f"无法读取压缩包：{archive_path}（{exc}）") from exc
