from __future__ import annotations

from .config import load_yaml
from .db import db_path


def company_status() -> dict:
    company = load_yaml("policies/company.yaml")
    return {
        "name": company.get("company", {}).get("name", "ThinkToFinish AI Software Company"),
        "version": "0.1.0",
        "operating_model": "Agent + Loop + Graph + Governance",
        "data_store": str(db_path()),
        "principles": company.get("principles", []),
    }
