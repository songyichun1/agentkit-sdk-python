from __future__ import annotations

from pathlib import Path

import agentkit.extensions


PLUGIN_EXTENSIONS = (
    Path(__file__).resolve().parents[1] / "src" / "agentkit" / "extensions"
)
agentkit.extensions.__path__.append(str(PLUGIN_EXTENSIONS))
