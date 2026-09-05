import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Merchant
from app.services.failure_lab import SCENARIO_DETAILS, SCENARIOS, run_scenario

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


@router.get("/failures/scenarios")
def list_scenarios():
    return {
        "scenarios": [
            {"code": code, "label": label, **SCENARIO_DETAILS.get(code, {})}
            for code, label in SCENARIOS.items()
        ]
    }


@router.post("/failures/{scenario}")
def trigger_failure(scenario: str, merchant_id: uuid.UUID, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.DEMO_MODE:
        raise AppError("DEMO_MODE_DISABLED", "The Failure Lab is only available when DEMO_MODE is enabled.", status_code=403)

    if scenario not in SCENARIOS:
        raise AppError("UNKNOWN_SCENARIO", f"Unknown scenario '{scenario}'.", status_code=422)

    merchant = db.get(Merchant, merchant_id)
    if not merchant:
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)

    result = run_scenario(db, merchant_id, scenario)
    return {"scenario": scenario, "label": SCENARIOS[scenario], **result}
