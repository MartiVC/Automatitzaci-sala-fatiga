"""Configuració de l'aplicació: models tipats i carregador de ``config.yaml``."""

from .loader import ConfigError, load_config
from .models import Config

__all__ = ["Config", "ConfigError", "load_config"]
