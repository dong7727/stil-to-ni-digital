"""STIL to NI-Digital conversion tools."""

from .converter import (
    ConversionError,
    ConversionResult,
    PinInfo,
    ScanChain,
    StilInspection,
    convert_file,
    inspect_file,
)

__all__ = [
    "ConversionError",
    "ConversionResult",
    "PinInfo",
    "ScanChain",
    "StilInspection",
    "convert_file",
    "inspect_file",
]
__version__ = "0.4.1"
