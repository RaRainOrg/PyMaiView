import tempfile
import unittest
import zipfile
from pathlib import Path

from pymaiview import PyMaiView, RenderError


class ArchiveTest(unittest.TestCase):
    def _archive(self, root: Path, files: dict[str, bytes | str]) -> Path:
        archive = root / "project.zip"
        with zipfile.ZipFile(archive, "w") as target:
            for name, contents in files.items():
                target.writestr(name, contents)
        return archive

    def test_extracts_project_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self._archive(
                Path(directory),
                {
                    "maidata.txt": "&title=test\n&inote_5=(120){4}1,",
                    "track.mp3": b"audio",
                    "bg.jpg": b"image",
                },
            )
            with PyMaiView.from_zip(archive) as view:
                extracted_root = view._project.root
                self.assertTrue(Path(view.maidata).is_file())
                self.assertTrue(Path(view.music).is_file())
                self.assertTrue(Path(view.pv).is_file())
            self.assertFalse(extracted_root.exists())

    def test_rejects_ambiguous_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self._archive(
                Path(directory),
                {"a/maidata.txt": "one", "b/maidata.txt": "two"},
            )
            with self.assertRaisesRegex(RenderError, "多个 maidata"):
                PyMaiView.from_zip(archive)

    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self._archive(Path(directory), {"../maidata.txt": "outside"})
            with self.assertRaisesRegex(RenderError, "不安全路径"):
                PyMaiView.from_zip(archive)


class InputTest(unittest.TestCase):
    def test_long_single_line_maidata_is_text(self):
        raw = "1," * 300
        self.assertEqual(PyMaiView._maidata_text(raw), raw)

    def test_rejects_invalid_render_dimensions_before_browser_start(self):
        view = PyMaiView(maidata="1,")
        with self.assertRaisesRegex(RenderError, "正整数"):
            view.render(width=0)


if __name__ == "__main__":
    unittest.main()
