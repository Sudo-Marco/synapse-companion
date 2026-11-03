from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
import os
import sqlite3
import subprocess
import webbrowser
from typing import Any
from ..manifest import ToolManifest, ToolParameter
from ..sandbox import Sandbox

def status_system(_params: dict[str, Any]) -> dict[str, Any]:
    import psutil
    battery = psutil.sensors_battery()
    return {"cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent,
            "battery_percent": battery.percent if battery else None}

def reminder(params: dict[str, Any]) -> dict[str, Any]:
    minutes = max(1, min(1440, int(params.get("minutes", 25))))
    return {"due_at": (datetime.now() + timedelta(minutes=minutes)).isoformat(),
            "label": str(params.get("label", "Lembrete"))[:120]}

def suggest_pause(_params: dict[str, Any]) -> dict[str, Any]:
    return {"suggestion": "Que tal fazer uma pausa curta e alongar?"}

def pomodoro(params: dict[str, Any]) -> dict[str, Any]:
    work = max(5, min(90, int(params.get("work_minutes", 25))))
    rest = max(1, min(30, int(params.get("rest_minutes", 5))))
    return {"work_minutes": work, "rest_minutes": rest, "started_at": datetime.now().isoformat()}

def open_folder(params: dict[str, Any], sandbox: Sandbox) -> dict[str, Any]:
    path = Path(str(params.get("path", ""))).expanduser().resolve()
    if not sandbox.path_allowed(path):
        raise PermissionError("folder is outside configured allowed folders")
    os.startfile(str(path))
    return {"opened": str(path)}

def open_app(params: dict[str, Any], sandbox: Sandbox) -> dict[str, Any]:
    app = str(params.get("app", ""))
    path = Path(app).expanduser().resolve()
    if str(path).lower() not in sandbox.allowed_apps:
        raise PermissionError("application path is not on the allowlist")
    subprocess.Popen([str(path)], shell=False)
    return {"started": path.name}

def open_url(params: dict[str, Any], *, explicit_user_action: bool = False) -> dict[str, Any]:
    if not explicit_user_action:
        raise PermissionError("abrir_url requires an explicit user action")
    url = str(params.get("url", ""))
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("only http/https URLs are accepted")
    webbrowser.open(url)
    return {"opened": True}

def notes_tools(db_path: Path) -> tuple[ToolManifest, ToolManifest]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    def add(params: dict[str, Any]) -> dict[str, Any]:
        text = str(params.get("text", ""))[:4000]
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, text TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)")
            cur = db.execute("INSERT INTO notes(text) VALUES(?)", (text,))
            return {"id": cur.lastrowid}
    def search(params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", ""))[:100]
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, text TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)")
            rows = db.execute("SELECT id,text,created FROM notes WHERE text LIKE ? ORDER BY id DESC LIMIT 20",
                              (f"%{query}%",)).fetchall()
        return {"notes": rows}
    def undo_add(params: dict[str, Any]) -> dict[str, Any]:
        result = params.get("_result", {})
        note_id = int(result.get("id", 0)) if isinstance(result, dict) else 0
        with sqlite3.connect(db_path) as db:
            db.execute("DELETE FROM notes WHERE id=?", (note_id,))
        return {"deleted": bool(note_id)}
    return (ToolManifest("anotar", "Salvar uma nota local.", "low", ("notes",), run=add, undo=undo_add,
                         parameters={"text": ToolParameter(str, required=True, max_length=4000)}),
            ToolManifest("buscar_notas", "Buscar notas locais.", "low", ("notes",), run=search,
                         parameters={"query": ToolParameter(str, required=True, max_length=100)}))

def clipboard_history_tool(db_path: Path) -> ToolManifest:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    def run(params: dict[str, Any]) -> dict[str, Any]:
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS clips(id INTEGER PRIMARY KEY, text TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)")
            if params.get("capture"):
                import tkinter as tk
                root = tk.Tk(); root.withdraw()
                value = root.clipboard_get(); root.destroy()
                db.execute("INSERT INTO clips(text) VALUES(?)", (value[:4000],))
            rows = db.execute("SELECT id,text,created FROM clips ORDER BY id DESC LIMIT 10").fetchall()
        return {"items": rows}
    return ToolManifest("historico_clipboard", "Capturar ou consultar histórico local do clipboard.", "medium",
                        ("clipboard",), run=run,
                        parameters={"capture": ToolParameter(bool, default=False)})

def changed_files_tool(sandbox: Sandbox, folder_default=None) -> ToolManifest:
    baseline: dict[str, dict[str, int]] = {}
    def run(params: dict[str, Any]) -> dict[str, Any]:
        folder = Path(str(params.get("folder", ""))).expanduser().resolve()
        if not sandbox.path_allowed(folder):
            raise PermissionError("folder is outside configured allowed folders")
        files = {p.name: p.stat().st_mtime_ns for p in folder.iterdir() if p.is_file()} if folder.is_dir() else {}
        before = baseline.get(str(folder), {})
        changed = sorted(name for name, stamp in files.items() if before.get(name) != stamp)
        removed = sorted(set(before) - set(files))
        baseline[str(folder)] = files
        return {"changed_names": changed[:100], "removed_names": removed[:100], "count": len(changed)+len(removed)}
    return ToolManifest("resumo_arquivos_alterados", "Resumir nomes de arquivos modificados numa pasta.", "medium",
                        ("files",), run=run,
                        parameters={"folder": ToolParameter(str, required=True,
                                                              default=folder_default,
                                                              max_length=1024)})

def daily_summary_tool(db_path: Path) -> ToolManifest:
    def run(_params: dict[str, Any]) -> dict[str, Any]:
        if not db_path.exists():
            return {"actions_today": 0}
        with sqlite3.connect(db_path) as db:
            count = db.execute("SELECT COUNT(*) FROM actions WHERE date(created)=date('now','localtime')").fetchone()[0]
        return {"actions_today": count}
    return ToolManifest("resumo_do_dia", "Contar ações registradas hoje, sem conteúdo de atividade.", "low",
                        ("summary",), run=run)

def command_tool(sandbox: Sandbox) -> ToolManifest:
    def run(params: dict[str, Any]) -> dict[str, Any]:
        return sandbox.run_command(str(params.get("executable", "")),
                                   [str(a) for a in params.get("args", [])][:30])
    return ToolManifest("rodar_comando_permitido", "Executar um comando exato na allowlist.", "high",
                        ("system",), run=run,
                        parameters={"executable": ToolParameter(str, required=True, max_length=1024),
                                    "args": ToolParameter(list, default=[], max_length=30,
                                                          item_type=str)})

def template_tool(folder: Path) -> ToolManifest:
    def run(params: dict[str, Any]) -> dict[str, Any]:
        name = "".join(c for c in str(params.get("name", "new_tool")) if c.isalnum() or c == "_")[:40]
        if not name:
            raise ValueError("plugin name is empty")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}.py"
        if path.exists():
            raise FileExistsError(path)
        path.write_text(
            "from synapse_pet.tools.manifest import ToolManifest\n\n"
            "def run(params):\n    return {'ok': True}\n\n"
            f"MANIFEST = ToolManifest({name!r}, 'Describe this tool.', 'medium', (), run=run)\n",
            encoding="utf-8")
        return {"created": str(path)}
    return ToolManifest("criar_ferramenta_template", "Criar um esqueleto de plugin local.", "medium",
                        ("developer",), run=run,
                        parameters={"name": ToolParameter(str, default="new_tool", max_length=40)})

def builtin_tools(data_dir: Path, sandbox: Sandbox) -> list[ToolManifest]:
    add, search = notes_tools(data_dir / "notes.sqlite3")
    audit_db = data_dir / "actions.sqlite3"
    def folder_run(params: dict[str, Any]) -> dict[str, Any]:
        return open_folder(params, sandbox)
    def app_run(params: dict[str, Any]) -> dict[str, Any]:
        return open_app(params, sandbox)
    def url_run(params: dict[str, Any]) -> dict[str, Any]:
        return open_url(params, explicit_user_action=bool(params.get("explicit_user_action")))
    folder_default = lambda: str(sorted(sandbox.allowed_folders)[0]) if sandbox.allowed_folders else ""
    app_default = lambda: sorted(sandbox.allowed_apps)[0] if sandbox.allowed_apps else ""
    return [
        ToolManifest("status_sistema", "Consultar CPU, RAM e bateria.", "low", ("status",), run=status_system),
        ToolManifest("lembrete", "Criar lembrete local.", "low", ("planning",), run=reminder,
                     parameters={"minutes": ToolParameter(int, default=25, minimum=1, maximum=1440),
                                 "label": ToolParameter(str, default="Lembrete", max_length=120)}),
        ToolManifest("pausa", "Sugerir uma pausa.", "low", ("activity",), run=suggest_pause),
        ToolManifest("pomodoro", "Iniciar ciclo de foco e descanso.", "low", ("planning",), run=pomodoro,
                     parameters={"work_minutes": ToolParameter(int, default=25, minimum=5, maximum=90),
                                 "rest_minutes": ToolParameter(int, default=5, minimum=1, maximum=30)}),
        ToolManifest("abrir_pasta", "Abrir pasta autorizada.", "medium", ("files",), run=folder_run,
                     parameters={"path": ToolParameter(str, required=True, default=folder_default,
                                                         max_length=1024)}),
        ToolManifest("abrir_app", "Iniciar aplicativo permitido.", "medium", ("apps",), run=app_run,
                     parameters={"app": ToolParameter(str, required=True, default=app_default,
                                                        max_length=1024)}),
        ToolManifest("abrir_url", "Abrir endereço após ação explícita do usuário.", "high", ("web",), run=url_run,
                     parameters={"url": ToolParameter(str, required=True, max_length=2048),
                                 "explicit_user_action": ToolParameter(bool, default=False)}),
        add, search, clipboard_history_tool(data_dir / "clipboard.sqlite3"),
        changed_files_tool(sandbox, folder_default), daily_summary_tool(audit_db), command_tool(sandbox),
        template_tool(data_dir / "user_tools"),
    ]
