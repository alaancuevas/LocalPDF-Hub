"""Characterisation of the Word COM converter, which only runs on Windows.

The COM calls were carried over from 3.x unchanged. These tests pin what
they do with fake COM objects so a refactor cannot silently change it.
"""

import types
from pathlib import Path

import pytest

from localpdf_hub.errors import AppError
from localpdf_hub.platform import word_com


class FakeComError(Exception):
    def __init__(self, hresult: int | None = None, text: str = "") -> None:
        super().__init__(text)
        self.hresult = hresult


class FakeDoc:
    def __init__(self, fail_with: Exception | None) -> None:
        self.fail_with = fail_with
        self.closed = False

    def SaveAs(self, path: str, FileFormat: int) -> None:  # noqa: N802, N803 -- COM names
        if self.fail_with:
            raise self.fail_with
        assert FileFormat == 17
        Path(path).write_bytes(b"%PDF-1.4")

    def Close(self, _save: int) -> None:  # noqa: N802 -- COM name
        self.closed = True


class FakeWord:
    def __init__(self, fail_with: Exception | None = None) -> None:
        self.opened: list[tuple[str, dict]] = []
        self.quit_called = False
        self.docs: list[FakeDoc] = []
        self.fail_with = fail_with
        self.Documents = types.SimpleNamespace(Open=self._open)

    def _open(self, path: str, **options: object) -> FakeDoc:
        self.opened.append((path, options))
        doc = FakeDoc(self.fail_with)
        self.docs.append(doc)
        return doc

    def Quit(self) -> None:  # noqa: N802 -- COM name
        self.quit_called = True


class FakeLibreOffice:
    def __init__(self) -> None:
        self.converted: list[str] = []

    def convert_one(self, document: Path, out_dir: Path) -> Path:
        self.converted.append(document.name)
        pdf = out_dir / f"{document.stem}.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        return pdf


@pytest.fixture
def com(monkeypatch):
    calls = {"init": 0, "uninit": 0}
    pythoncom = types.SimpleNamespace(
        CoInitialize=lambda: calls.__setitem__("init", calls["init"] + 1),
        CoUninitialize=lambda: calls.__setitem__("uninit", calls["uninit"] + 1),
    )
    monkeypatch.setattr(word_com, "pythoncom", pythoncom, raising=False)
    monkeypatch.setattr(
        word_com, "pywintypes", types.SimpleNamespace(com_error=FakeComError), raising=False
    )
    return calls


def _use_word(monkeypatch, word: FakeWord | None) -> None:
    monkeypatch.setattr(word_com, "_start_word", lambda: word)


def _docx(tmp_path: Path, name: str = "report.docx") -> Path:
    path = tmp_path / name
    path.write_bytes(b"PK")
    return path


def test_word_converts_and_always_quits(tmp_path, monkeypatch, com):
    word = FakeWord()
    _use_word(monkeypatch, word)
    pdfs = word_com.WordComConverter(fallback=None).convert([_docx(tmp_path)], tmp_path)
    assert [pdf.name for pdf in pdfs] == ["report.pdf"]
    _, options = word.opened[0]
    assert options == {
        "ConfirmConversions": False,
        "ReadOnly": True,
        "AddToRecentFiles": False,
        "OpenAndRepair": True,
    }
    assert word.docs[0].closed and word.quit_called
    assert com == {"init": 1, "uninit": 1}


def test_word_2007_falls_back_to_libreoffice(tmp_path, monkeypatch, com):
    word = FakeWord(fail_with=FakeComError(hresult=-2147352567))
    _use_word(monkeypatch, word)
    fallback = FakeLibreOffice()
    pdfs = word_com.WordComConverter(fallback=fallback).convert([_docx(tmp_path)], tmp_path)
    assert fallback.converted == ["report.docx"]
    assert pdfs[0].exists()
    assert word.docs[0].closed


def test_word_2007_without_libreoffice(tmp_path, monkeypatch, com):
    _use_word(monkeypatch, FakeWord(fail_with=FakeComError(text="Office12")))
    with pytest.raises(AppError) as info:
        word_com.WordComConverter(fallback=None).convert([_docx(tmp_path)], tmp_path)
    assert info.value.code == "ERR_CONVERTER_MISSING"
    assert com["uninit"] == 1


def test_other_com_errors_stop_the_batch(tmp_path, monkeypatch, com):
    word = FakeWord(fail_with=FakeComError(hresult=-1, text="file is corrupt"))
    _use_word(monkeypatch, word)
    with pytest.raises(AppError) as info:
        word_com.WordComConverter(fallback=FakeLibreOffice()).convert([_docx(tmp_path)], tmp_path)
    assert info.value.code == "ERR_INTERNAL"
    assert word.quit_called


def test_without_word_every_document_goes_to_libreoffice(tmp_path, monkeypatch, com):
    _use_word(monkeypatch, None)
    fallback = FakeLibreOffice()
    documents = [_docx(tmp_path, "a.docx"), _docx(tmp_path, "b.docx")]
    word_com.WordComConverter(fallback=fallback).convert(documents, tmp_path)
    assert fallback.converted == ["a.docx", "b.docx"]
