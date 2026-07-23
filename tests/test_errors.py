"""Tests for the error/exception hierarchy."""

from __future__ import annotations

import pytest

from khocr_gen.errors import (
    ErrorContext,
    FontLoadError,
    GenerationError,
    InputValidationError,
    KhocrGenError,
)


class TestErrorContext:
    def test_creation(self):
        ctx = ErrorContext(code="E001", detail="some detail")
        assert ctx.code == "E001"
        assert ctx.detail == "some detail"


class TestKhocrGenError:
    def test_basic_error(self):
        exc = KhocrGenError("something failed", code="TEST")
        assert "something failed" in str(exc)
        assert exc.context is not None
        assert exc.context.code == "TEST"
        assert exc.context.detail == "something failed"

    def test_repr(self):
        exc = KhocrGenError("msg", code="E001")
        r = repr(exc)
        assert "KhocrGenError" in r
        # The context code is stored separately, not in the repr

    def test_default_code(self):
        exc = KhocrGenError("plain error")
        assert exc.context is not None
        assert exc.context.code == "internal_error"
        assert str(exc) == "plain error"


class TestInputValidationError:
    def test_with_message(self):
        exc = InputValidationError("file not found")
        assert exc.context is not None
        assert exc.context.code == "internal_error"
        assert "file not found" in str(exc)

    def test_is_khocr_gen_error(self):
        exc = InputValidationError("bad input")
        assert isinstance(exc, KhocrGenError)

    def test_can_catch_as_base(self):
        with pytest.raises(KhocrGenError):
            raise InputValidationError("test")

    def test_custom_code(self):
        exc = InputValidationError("file not found", code="corpus_not_found")
        assert exc.context.code == "corpus_not_found"


class TestGenerationError:
    def test_basic(self):
        exc = GenerationError("generation failed")
        assert isinstance(exc, KhocrGenError)
        assert "generation failed" in str(exc)


class TestFontLoadError:
    def test_basic(self):
        exc = FontLoadError("font not found")
        assert isinstance(exc, KhocrGenError)
        assert "font not found" in str(exc)
