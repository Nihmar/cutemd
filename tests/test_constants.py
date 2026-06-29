"""Tests for core/constants.py"""

from core.constants import DOC_EXTS, IMG_EXTS, MD_EXTS, PDF_EXTS


def test_md_exts():
    assert ".md" in MD_EXTS
    assert ".markdown" in MD_EXTS


def test_img_exts():
    assert ".png" in IMG_EXTS
    assert ".jpg" in IMG_EXTS
    assert ".svg" in IMG_EXTS


def test_doc_exts():
    assert ".docx" in DOC_EXTS
    assert ".pdf" in PDF_EXTS
