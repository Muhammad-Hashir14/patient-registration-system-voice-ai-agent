import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientUpdate, PatientResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)


def get_patient(db: Session, patient_id: str) -> Patient | None:
    return db.query(Patient).filter(
        Patient.patient_id == patient_id,
        Patient.deleted_at.is_(None)
    ).first()


def get_patients(
    db: Session,
    last_name: str | None = None,
    date_of_birth: str | None = None,
    phone_number: str | None = None,
) -> list[Patient]:
    query = db.query(Patient).filter(Patient.deleted_at.is_(None))
    if last_name:
        query = query.filter(Patient.last_name.ilike(f"%{last_name}%"))
    if date_of_birth:
        query = query.filter(Patient.date_of_birth == date_of_birth)
    if phone_number:
        from app.utils.validation import normalize_phone
        normalized = normalize_phone(phone_number)
        if normalized:
            query = query.filter(Patient.phone_number == normalized)
    return query.all()


def find_by_phone(db: Session, phone_number: str) -> Patient | None:
    from app.utils.validation import normalize_phone
    normalized = normalize_phone(phone_number)
    if not normalized:
        return None
    return db.query(Patient).filter(
        Patient.phone_number == normalized,
        Patient.deleted_at.is_(None)
    ).first()


def create_patient(db: Session, data: PatientCreate) -> Patient:
    patient = Patient(**data.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def update_patient(db: Session, patient_id: str, data: PatientUpdate) -> Patient | None:
    patient = get_patient(db, patient_id)
    if not patient:
        return None
    updates = data.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(patient, field, value)
    patient.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(patient)
    return patient


def soft_delete_patient(db: Session, patient_id: str) -> bool:
    patient = get_patient(db, patient_id)
    if not patient:
        return False
    patient.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return True
