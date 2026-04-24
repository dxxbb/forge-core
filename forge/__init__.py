"""forge-core: a review-gated context compiler."""

__version__ = "0.1.0"

from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.compiler.loader import load_sections, load_config
from forge.compiler.renderer import render

__all__ = ["Section", "Config", "load_sections", "load_config", "render", "__version__"]
