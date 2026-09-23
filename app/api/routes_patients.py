from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.schemas.patient import PatientCreate, PatientUpdate, PatientResponse
from app.services import patient_service

router = APIRouter()


@router.get("/patients", response_model=dict)
def list_patients(
    last_name: str | None = Query(None),
    date_of_birth: str | None = Query(None),
    phone_number: str | None = Query(None),
    db: Session = Depends(get_db),
):
    patients = patient_service.get_patients(db, last_name, date_of_birth, phone_number)
    data = [PatientResponse.model_validate(p).model_dump() for p in patients]
    return {"data": data, "error": None}


@router.get("/patients/{patient_id}", response_model=dict)
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = patient_service.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail={"data": None, "error": "Patient not found."})
    return {"data": PatientResponse.model_validate(patient).model_dump(), "error": None}


@router.post("/patients", response_model=dict, status_code=201)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)):
    existing = patient_service.find_by_phone(db, payload.phone_number)
    if existing:
        raise HTTPException(
            status_code=400,
            detail={"data": None, "error": f"A patient with this phone number already exists (ID: {existing.patient_id})."}
        )
    patient = patient_service.create_patient(db, payload)
    return {"data": PatientResponse.model_validate(patient).model_dump(), "error": None}


@router.put("/patients/{patient_id}", response_model=dict)
def update_patient(patient_id: str, payload: PatientUpdate, db: Session = Depends(get_db)):
    patient = patient_service.update_patient(db, patient_id, payload)
    if not patient:
        raise HTTPException(status_code=404, detail={"data": None, "error": "Patient not found."})
    return {"data": PatientResponse.model_validate(patient).model_dump(), "error": None}


@router.delete("/patients/{patient_id}", response_model=dict)
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    success = patient_service.soft_delete_patient(db, patient_id)
    if not success:
        raise HTTPException(status_code=404, detail={"data": None, "error": "Patient not found."})
    return {"data": {"message": "Patient deleted successfully."}, "error": None}
