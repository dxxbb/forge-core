"""forge: a review-gated context compiler. (PyPI package: context-forge)"""

__version__ = "0.3.1"

from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.compiler.loader import load_sections, load_config
from forge.compiler.renderer import render

__all__ = ["Section", "Config", "load_sections", "load_config", "render", "__version__"]
