from __future__ import annotations
import argparse
from pathlib import Path
from .runtime.engine import APP_DATA, PetEngine
from .runtime.persistence import SnapshotStore

def main() -> None:
    parser = argparse.ArgumentParser(description="Local Synapse Pet companion")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--ticks", type=int, default=100)
    parser.add_argument("--export-creature", type=Path, help="write a single ZIP creature backup")
    parser.add_argument("--import-creature", type=Path, help="restore a ZIP creature backup")
    parser.add_argument("--reset-affect", action="store_true",
                        help="reset mood and affect to neutral without changing learned weights")
    args = parser.parse_args()
    store = SnapshotStore(APP_DATA / "creature")
    if args.import_creature:
        store.import_zip(args.import_creature, APP_DATA / "episodes.sqlite3")
    engine = PetEngine()
    if args.reset_affect:
        engine.reset_affect_to_neutral(save=True)
        print("Mood and affect reset to neutral; learned weights were preserved.")
        return
    if args.export_creature:
        engine.save()
        engine.store.export_zip(args.export_creature, engine.memory.path)
        print(f"Backup written: {args.export_creature}")
        return
    if args.headless:
        for _ in range(args.ticks):
            engine.tick({"input_rate": .3, "window_category": "codigo", "activity": .5, "hour": .5})
        print(f"ticks={engine.network.tick_count} neurons={engine.network.population.size}")
        return
    from .ui.qt_app import PetWindow
    PetWindow(engine).run()

if __name__ == "__main__":
    main()
