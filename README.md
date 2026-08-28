# PyMaiView

用 Python 和 Playwright 导出 maimai 谱面确认视频。运行时 Web 代码、皮肤和音效都位于
`src/pymaiview/web`，它们是应用源码，不需要额外构建脚本或 Git submodule。转场直接使用
`Assets/transition.mp4` 的原始动画和 WebGL 五色映射，并与
“转场 → 谱面介绍 → 转场 → 正式播放”共用同一条渲染时间轴。

## 安装

```bash
uv sync
uv run playwright install chromium
```

## Python API

```python
from pymaiview import PyMaiView

with PyMaiView.from_zip("TECHNOPOLIS 1042.5.zip") as view:
    view.playback.update({"speed": 6.5, "touchSpeed": 7, "visualZoom": 200})
    view.render("output.mp4", width=1280, height=720, fps=30)
```

也可以直接传入资源。文件路径推荐使用 `Path`，普通字符串也可以作为 maidata 原文。

```python
from pathlib import Path
from pymaiview import PyMaiView

PyMaiView(
    skin=Path("my-skin"),
    playback={"speed": 7, "touchSpeed": 8, "moviebrightness": -2},
    maidata=Path("maidata.txt"),
    pv=Path("bg.jpg"),
    music=Path("track.mp3"),
    difficulty=5,
).render("output.mp4")
```

## CLI

```bash
uv run pymaiview "TECHNOPOLIS 1042.5.zip" -o output.mp4 --fps 60
```

## 开发

```bash
uv run python -m unittest discover -v
uv build
```

## 版权与致谢

本项目使用或参考了以下开源项目与视觉素材：

- 浏览器谱面渲染器修改自 [Web mai Chart X](https://github.com/Susuy0725/web-mai-chart-x)，谱面介绍卡还原自该项目 `78859fd` 版本的 `drawLoadingIntro`。
- 谱面解析、音符表现和 Judge Text 参考 [MajdataView](https://github.com/LingFeng-bbben/MajdataView)。
- 左右辅助 UI、字体层级、排版及 Judge Text 动画参数参考 [MajdataViewX / TRGUI-yours](https://github.com/re-poem/MajdataViewX/tree/TRGUI-yours)。
- 转场动画素材来源及设计参考：[你真见过这么丝滑的迪拉熊么？｜舞萌DX 转场复刻](https://www.bilibili.com/video/BV1or421s7i5/)。

本项目依照 GPL-3.0 发布，完整条款见 `LICENSE`。上游项目及素材的版权归各自作者所有。
