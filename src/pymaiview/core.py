"""Public rendering API."""

from __future__ import annotations

import base64
import json
import math
import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Mapping, Optional, Union

from .archive import ExtractedProject, extract_project
from .errors import RenderError


PathLike = Union[str, os.PathLike]


class PyMaiView:
    """Render a maimai chart project with the bundled browser renderer."""

    def __init__(
        self,
        *,
        skin: Optional[PathLike] = None,
        playback: Optional[Mapping[str, Any]] = None,
        maidata: Optional[Union[str, PathLike]] = None,
        pv: Optional[PathLike] = None,
        music: Optional[PathLike] = None,
        difficulty: int = 5,
    ) -> None:
        self.skin = skin
        self.playback = dict(playback or {})
        self.maidata = maidata
        self.pv = pv
        self.music = music
        self.difficulty = difficulty
        self._project: Optional[ExtractedProject] = None

    @classmethod
    def from_zip(cls, archive: PathLike, **overrides: Any) -> "PyMaiView":
        """Create a renderer from a Web mai Chart X project archive.

        Explicit keyword arguments override resources detected in the archive.
        Use the returned object as a context manager for deterministic cleanup.
        """

        project = extract_project(archive)
        resources = {
            "maidata": project.maidata,
            "music": project.music,
            "pv": project.pv,
        }
        resources.update({key: value for key, value in overrides.items() if value is not None})
        try:
            view = cls(**resources)
        except Exception:
            project.close()
            raise
        view._project = project
        return view

    def close(self) -> None:
        """Release files extracted by :meth:`from_zip`."""

        if self._project is not None:
            self._project.close()
            self._project = None

    def __enter__(self) -> "PyMaiView":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    @staticmethod
    def _maidata_text(value: Optional[Union[str, PathLike]]) -> str:
        if value is None:
            raise RenderError("没有提供 maidata")
        if isinstance(value, os.PathLike):
            return PyMaiView._read_text_file(Path(value), "maidata")

        # Preserve the string-path API without treating every single-line
        # chart as a filename. Some platforms reject long raw text as a path.
        if "\n" not in value and "\r" not in value:
            try:
                path = Path(value).expanduser()
                if path.is_file():
                    return PyMaiView._read_text_file(path, "maidata")
            except OSError:
                pass
        return value

    @staticmethod
    def _read_text_file(path: Path, label: str) -> str:
        path = path.expanduser()
        if not path.is_file():
            raise RenderError(f"找不到 {label}：{path}")
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RenderError(f"无法读取 {label}：{path}（{exc}）") from exc

    @staticmethod
    def _uri(value: Optional[PathLike], *, directory: bool = False) -> Optional[str]:
        if value is None:
            return None
        path = Path(value).expanduser().resolve()
        expected = path.is_dir() if directory else path.is_file()
        if not expected:
            kind = "skin 目录" if directory else "资源文件"
            raise RenderError(f"找不到{kind}：{path}")
        uri = path.as_uri()
        return uri.rstrip("/") + "/" if directory else uri

    @staticmethod
    def _browser_options(playwright: Any, headed: bool) -> Dict[str, Any]:
        args = [
            "--allow-file-access-from-files",
            "--autoplay-policy=no-user-gesture-required",
        ]
        configured = os.environ.get("PYMAIVIEW_CHROME_PATH")
        if configured:
            executable = Path(configured).expanduser()
            if not executable.is_file():
                raise RenderError(f"PYMAIVIEW_CHROME_PATH 无效：{executable}")
            return {"headless": not headed, "executable_path": str(executable), "args": args}

        candidates = [
            Path(playwright.chromium.executable_path),
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
        for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
        for candidate in candidates:
            if candidate.is_file():
                return {
                    "headless": not headed,
                    "executable_path": str(candidate),
                    "args": args,
                }
        return {"headless": not headed, "args": args}

    @staticmethod
    def _validate_render_args(
        width: int,
        height: int,
        fps: int,
        start: float,
        end: Optional[float],
        timeout: float,
    ) -> None:
        def finite_number(value: object) -> bool:
            return (
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(value)
            )

        dimensions = (width, height, fps)
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in dimensions):
            raise RenderError("width、height、fps 必须为正整数")
        if not finite_number(start):
            raise RenderError("start 必须是有限数值")
        if end is not None and (not finite_number(end) or end <= start):
            raise RenderError("end 必须是大于 start 的有限数值")
        if not finite_number(timeout) or timeout <= 0:
            raise RenderError("timeout 必须是正的有限数值")

    def _render_in_browser(
        self,
        partial: Path,
        config: Mapping[str, Any],
        request: Mapping[str, Any],
        page_path: Path,
        timeout: float,
        headed: bool,
    ) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RenderError("缺少 Playwright，请先运行：uv sync") from exc

        browser = None
        context = None
        browser_errors: list[str] = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(**self._browser_options(playwright, headed))
                context = browser.new_context(
                    viewport={"width": request["width"], "height": request["height"]}
                )
                page = context.new_page()
                page.on("pageerror", lambda error: browser_errors.append(f"pageerror: {error}"))
                page.on(
                    "console",
                    lambda message: browser_errors.append(f"console: {message.text}")
                    if message.type == "error"
                    else None,
                )
                with partial.open("wb") as output_file:
                    page.expose_binding(
                        "__pymaiview_chunk",
                        lambda _source, chunk: output_file.write(base64.b64decode(chunk)),
                    )
                    page.expose_binding("__pymaiview_done", lambda _source: True)
                    page.add_init_script(
                        "globalThis.__PYMAIVIEW_CONFIG__ = "
                        + json.dumps(config, ensure_ascii=False)
                        + ";"
                    )
                    page.goto(page_path.as_uri(), wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_function(
                        "() => Boolean(window.pymaiview && window.pymaiview.ready)",
                        timeout=30_000,
                    )
                    page.evaluate("() => window.pymaiview.ready")
                    page.evaluate(
                        """([renderRequest, timeoutMs]) => Promise.race([
                            window.pymaiview.render(renderRequest),
                            new Promise((_, reject) => setTimeout(
                                () => reject(new Error('render timeout')), timeoutMs
                            )),
                        ])""",
                        [request, int(timeout * 1000)],
                    )
        except RenderError:
            raise
        except Exception as exc:
            detail = "; ".join(browser_errors[-3:])
            suffix = f"（{detail}）" if detail else ""
            raise RenderError(f"浏览器渲染失败：{exc}{suffix}") from exc
        finally:
            for resource in (context, browser):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        pass

    def render(
        self,
        output: PathLike = "output.mp4",
        *,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        start: float = 0.0,
        end: Optional[float] = None,
        bgm_volume: Optional[float] = None,
        sfx_volume: Optional[float] = None,
        include_audio: bool = True,
        include_sfx: bool = True,
        include_intro: bool = True,
        include_all_perfect: bool = False,
        timeout: float = 1800,
        headed: bool = False,
    ) -> Path:
        """Render an MP4 and return its absolute path."""

        self._validate_render_args(width, height, fps, start, end, timeout)
        if not isinstance(self.difficulty, int) or isinstance(self.difficulty, bool) or self.difficulty <= 0:
            raise RenderError("difficulty 必须为正整数")

        page_path = Path(__file__).resolve().parent / "web" / "render.html"
        if not page_path.is_file():
            raise RenderError(f"缺少浏览器运行时：{page_path}")

        config = {
            "skin": self._uri(self.skin, directory=True),
            "playback": self.playback,
            "maidata": self._maidata_text(self.maidata),
            "pv": self._uri(self.pv),
            "music": self._uri(self.music),
            "difficulty": self.difficulty,
        }
        request = {
            "width": width,
            "height": height,
            "fps": fps,
            "start": start,
            "end": end,
            "bgmVolume": bgm_volume,
            "sfxVolume": sfx_volume,
            "includeAudio": include_audio,
            "includeSfx": include_sfx,
            "includeIntro": include_intro,
            "includeAllPerfect": include_all_perfect,
        }
        try:
            json.dumps(config)
        except (TypeError, ValueError) as exc:
            raise RenderError(f"playback 包含无法序列化的值：{exc}") from exc

        output_path = Path(output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            prefix=f".{output_path.name}.",
            suffix=".part",
            dir=output_path.parent,
            delete=False,
        ) as temporary:
            partial = Path(temporary.name)

        try:
            self._render_in_browser(partial, config, request, page_path, timeout, headed)
            if partial.stat().st_size < 1024:
                raise RenderError("浏览器没有生成有效的 MP4")
            with partial.open("rb") as rendered:
                header = rendered.read(128)
            if b"ftyp" not in header:
                raise RenderError("浏览器输出不是 MP4")
            partial.replace(output_path)
            return output_path
        finally:
            partial.unlink(missing_ok=True)


MaiView = PyMaiView
