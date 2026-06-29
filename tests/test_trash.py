"""Tests for core/trash.py"""

import tempfile
from pathlib import Path

from core.trash import list_trash, restore_file, trash_file, trash_path


def test_trash_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    f = vault / "test.md"
    f.write_text("hello")

    result = trash_file(f, vault)
    assert result is not None
    assert result.exists()
    assert not f.exists()
    assert ".trash" in result.parts


def test_restore_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    f = vault / "sub" / "test.md"
    f.parent.mkdir(parents=True)
    f.write_text("hello")

    trashed = trash_file(f, vault)
    restored = restore_file(trashed, vault)
    assert restored == f
    assert f.exists()
    assert not trashed.exists()


def test_list_trash(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    f = vault / "a.md"
    f.write_text("x")
    trash_file(f, vault)

    listed = list_trash(vault)
    assert len(listed) == 1
