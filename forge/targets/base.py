"""Base adapter interface. Implement one subclass per runtime."""

from __future__ import annotations

from abc import ABC, abstractmethod

from forge.compiler.section import Section
from forge.compiler.config import Config


class TargetAdapter(ABC):
    name: str = ""
    default_filename: str = ""

    @abstractmethod
    def render(self, sections: list[Section], config: Config) -> str:
        """Render an ordered list of sections into the target runtime's text format."""

    def filename(self, config: Config) -> str:
        """The output filename. Default: adapter's default_filename."""
        return self.default_filename
