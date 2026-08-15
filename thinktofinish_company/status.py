from __future__ import annotations

from .config import load_yaml
from .db import db_path


def company_status() -> dict:
    company = load_yaml("policies/company.yaml")
    return {
        "name": company.get("company", {}).get("name", "ThinkToFinish AI Software Company"),
        "version": "0.2.0",
        "operating_model": "Company Core → Work Intelligence → Execution Runtime → Coding Owner",
        "layers": {
            "company_core": "ThinkToFinish",
            "work_intelligence": "Oh My Hermes (preferred)",
            "execution_runtime": "Hermes Agent",
            "implementation": "selected coding owner",
        },
        "data_store": str(db_path()),
        "principles": company.get("principles", []),
    }
