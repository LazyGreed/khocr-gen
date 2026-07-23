"""khocr-gen - Synthetic OCR training data generator for mixed Khmer/English text."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("khocr-gen")
except PackageNotFoundError:
    __version__ = "0.0.0"
