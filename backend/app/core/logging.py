"""Journalisation.

Règle de sécurité (principe « Privacy by design » du cahier des charges) :
les credentials des connexions sources ne doivent JAMAIS être loggés. On
fournit un filtre qui masque les motifs sensibles en défense en profondeur.
"""
from __future__ import annotations

import logging
import re

_SENSITIVE_PATTERNS = [
    re.compile(r"(password\s*[=:]\s*)([^\s&;'\"]+)", re.IGNORECASE),
    re.compile(r"(pwd\s*[=:]\s*)([^\s&;'\"]+)", re.IGNORECASE),
    re.compile(r"(://[^:/@\s]+:)([^@/\s]+)(@)"),  # user:password@host
    re.compile(r"(secret[_-]?key\s*[=:]\s*)([^\s&;'\"]+)", re.IGNORECASE),
]


class RedactingFilter(logging.Filter):
    """Masque les secrets présents dans les messages de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - formatage défensif
            return True
        redacted = msg
        for pat in _SENSITIVE_PATTERNS:
            redacted = pat.sub(lambda m: m.group(1) + "***" + (m.group(3) if m.lastindex and m.lastindex >= 3 else ""), redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s")
    )
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
