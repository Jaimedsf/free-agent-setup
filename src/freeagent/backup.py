import shutil
from datetime import datetime
from pathlib import Path

FILES = ("config.yaml", ".env", "auth.json")
BACKUP_DIR = "freeagent-backups"


def make_backup(hermes_home: Path, omh_home: Path, now: datetime) -> Path:
    dest = hermes_home / BACKUP_DIR / now.strftime("%Y%m%d-%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        if (hermes_home / name).is_file():
            shutil.copy2(hermes_home / name, dest / name)
    if (omh_home / "routing").is_dir():
        shutil.copytree(omh_home / "routing", dest / "omh-routing", dirs_exist_ok=True)
    return dest


def restore_latest(hermes_home: Path, omh_home: Path) -> Path | None:
    root = hermes_home / BACKUP_DIR
    backups = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if not backups:
        return None
    src = backups[-1]
    for name in FILES:
        if (src / name).is_file():
            shutil.copy2(src / name, hermes_home / name)
    if (src / "omh-routing").is_dir():
        shutil.copytree(src / "omh-routing", omh_home / "routing", dirs_exist_ok=True)
    return src
