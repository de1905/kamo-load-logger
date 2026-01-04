"""Backup management API endpoints."""

import csv
import io
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db, Cooperative, LoadData, SubstationSnapshot, ImportLog, now_central

router = APIRouter(prefix="/backups", tags=["Backups"])

# Backup directory
BACKUP_DIR = Path("data/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Table configurations
TABLES = {
    "cooperatives": {
        "model": Cooperative,
        "order_by": "id",
    },
    "load_data": {
        "model": LoadData,
        "order_by": "timestamp",
    },
    "substation_snapshots": {
        "model": SubstationSnapshot,
        "order_by": "snapshot_time",
    },
    "import_log": {
        "model": ImportLog,
        "order_by": "id",
    },
}


def get_backup_info(filepath: Path) -> dict:
    """Get metadata about a backup file."""
    stat = filepath.stat()

    # Try to read manifest from zip
    manifest = None
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            if 'manifest.json' in zf.namelist():
                manifest = json.loads(zf.read('manifest.json'))
    except:
        pass

    return {
        "filename": filepath.name,
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "manifest": manifest,
    }


@router.get("")
async def list_backups():
    """List all available backups."""
    backups = []

    for filepath in sorted(BACKUP_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        backups.append(get_backup_info(filepath))

    return {
        "backups": backups,
        "count": len(backups),
        "backup_dir": str(BACKUP_DIR.absolute()),
    }


@router.post("")
async def create_backup(db: Session = Depends(get_db)):
    """Generate a new backup of all tables."""
    timestamp = now_central().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.zip"
    filepath = BACKUP_DIR / filename

    manifest = {
        "created_at": now_central().isoformat(),
        "tables": {},
    }

    # Create zip file with CSVs
    with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
        for table_name, config in TABLES.items():
            model = config["model"]
            order_col = getattr(model, config["order_by"])

            # Query all rows
            rows = db.query(model).order_by(order_col).all()

            # Get column names
            columns = [c.name for c in model.__table__.columns]

            # Write to CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(columns)

            for row in rows:
                row_data = []
                for col in columns:
                    val = getattr(row, col)
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    row_data.append(val)
                writer.writerow(row_data)

            # Add CSV to zip
            csv_content = output.getvalue()
            zf.writestr(f"{table_name}.csv", csv_content)

            manifest["tables"][table_name] = {
                "rows": len(rows),
                "columns": columns,
            }

        # Add manifest
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return {
        "success": True,
        "backup": get_backup_info(filepath),
    }


@router.get("/{filename}")
async def download_backup(filename: str):
    """Download a specific backup file."""
    # Sanitize filename to prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = BACKUP_DIR / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    return FileResponse(
        filepath,
        media_type="application/zip",
        filename=filename,
    )


@router.delete("/{filename}")
async def delete_backup(filename: str):
    """Delete a specific backup file."""
    # Sanitize filename to prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = BACKUP_DIR / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    filepath.unlink()

    return {
        "success": True,
        "deleted": filename,
    }
