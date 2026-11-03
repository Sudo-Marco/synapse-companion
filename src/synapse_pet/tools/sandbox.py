from __future__ import annotations
from pathlib import Path
import subprocess

class Sandbox:
    """Allowlist checks for built-in filesystem, app, and command tools."""
    def __init__(self, allowed_folders: list[str] | None = None,
                 allowed_commands: list[str] | None = None,
                 allowed_apps: list[str] | None = None,
                 timeout_s: float = 5.0, max_output_chars: int = 4000) -> None:
        self.allowed_folders = [Path(x).expanduser().resolve() for x in (allowed_folders or [])]
        self.allowed_commands = {str(Path(x).expanduser().resolve()).lower() for x in (allowed_commands or [])}
        self.allowed_apps = {str(Path(x).expanduser().resolve()).lower() for x in (allowed_apps or [])}
        self.timeout_s, self.max_output_chars = timeout_s, max_output_chars

    def path_allowed(self, path: str | Path) -> bool:
        resolved = Path(path).expanduser().resolve()
        return any(resolved == root or root in resolved.parents for root in self.allowed_folders)

    def run_command(self, executable: str, args: list[str]) -> dict[str, object]:
        path = Path(executable).expanduser().resolve()
        if str(path).lower() not in self.allowed_commands:
            raise PermissionError("command path is not on the allowlist")
        result = subprocess.run([str(path), *args], capture_output=True, text=True,
                                timeout=self.timeout_s, shell=False, check=False)
        return {"returncode": result.returncode, "stdout": result.stdout[:self.max_output_chars],
                "stderr": result.stderr[:self.max_output_chars]}
