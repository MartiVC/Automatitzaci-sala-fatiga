"""Validacio i pipeline de tractament de lectures."""

from .pipeline import PipelineResult, ProcessingPipeline
from .validation import ValidationConfig, ReadingValidator

__all__ = ["PipelineResult", "ProcessingPipeline", "ReadingValidator", "ValidationConfig"]
