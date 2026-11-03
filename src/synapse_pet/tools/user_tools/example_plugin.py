"""Copy this file to the local user_tools folder and adapt it."""
from synapse_pet.tools.manifest import ToolManifest

def run(params: dict[str, object]) -> dict[str, object]:
    return {"message": "Example plugin is ready"}

MANIFEST = ToolManifest("exemplo", "Exemplo mínimo de plugin.", "low", ("example",), run=run)
