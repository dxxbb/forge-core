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
        """The output filename.

        A config may override it with ``filename:`` — this is what lets two
        configs share one target (e.g. two ``agents-md`` agents) without their
        runtime outputs colliding. Defaults to the adapter's default_filename.
        """
        return config.filename or self.default_filename
