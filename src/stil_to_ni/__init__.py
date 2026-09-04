"""STIL to NI-Digital conversion tools."""

from .converter import ConversionError, ConversionResult, convert_file

__all__ = ["ConversionError", "ConversionResult", "convert_file"]
__version__ = "0.1.0"
