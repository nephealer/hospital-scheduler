"""HTTP Cloud Function: match patient symptoms to available doctors."""

import json
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import firestore
from firebase_functions import https_fn, options

firebase_admin.initialize_app()


SYMPTOM_SPECIALTY_MAP = {
    "chest pain": "Cardiology",
    "heart palpitations": "Cardiology",
    "shortness of breath": "Cardiology",
    "high blood pressure": "Cardiology",
    "irregular heartbeat": "Cardiology",

    "rash": "Dermatology",
    "acne": "Dermatology",
    "eczema": "Dermatology",
    "skin irritation": "Dermatology",
    "mole change": "Dermatology",
    "hair loss": "Dermatology",

    "fever": "General Practice",
    "cough": "General Practice",
    "sore throat": "General Practice",
    "headache": "General Practice",
    "fatigue": "General Practice",
    "body ache": "General Practice",
    "cold": "General Practice",
    "flu": "General Practice",

    "child cough": "Pediatrics",
    "child fever": "Pediatrics",
    "child rash": "Pediatrics",
    "ear infection": "Pediatrics",
    "vaccination": "Pediatrics",
    "growth concerns": "Pediatrics",

    "joint pain": "Orthopedics",
    "back pain": "Orthopedics",
    "fracture": "Orthopedics",
    "sprain": "Orthopedics",
    "knee pain": "Orthopedics",
    "shoulder pain": "Orthopedics",

    "anxiety": "Psychiatry",
    "depression": "Psychiatry",
    "insomnia": "Psychiatry",
    "panic attacks": "Psychiatry",
    "mood swings": "Psychiatry",

    "blurred vision": "Ophthalmology",
    "eye pain": "Ophthalmology",
    "red eye": "Ophthalmology",
    "vision loss": "Ophthalmology",

    "stomach pain": "Gastroenterology",
    "nausea": "Gastroenterology",
    "acid reflux": "Gastroenterology",
    "diarrhea": "Gastroenterology",
    "constipation": "Gastroenterology",
}


def _json_response(data: dict, status: int = 200) -> https_fn.Response:
    return https_fn.Response(
        json.dumps(data),
        status=status,
        mimetype="application/json",
    )


def _map_symptom_to_specialty(symptom: str) -> str | None:
    if not symptom:
        return None
    key = symptom.strip().lower()
    if key in SYMPTOM_SPECIALTY_MAP:
        return SYMPTOM_SPECIALTY_MAP[key]
    for symptom_key, specialty in SYMPTOM_SPECIALTY_MAP.items():
        if symptom_key in key or key in symptom_key:
            return specialty
    return None


def _next_future_slot(slots: list[str], now_iso: str) -> str | None:
    future = [s for s in (slots or []) if s > now_iso]
    if not future:
        return None
    return min(future)


def _build_doctor_payload(doctor_doc, hospitals_cache: dict, now_iso: str) -> dict | None:
    data = doctor_doc.to_dict() or {}
    next_slot = _next_future_slot(data.get("available_slots", []), now_iso)
    if not next_slot:
        return None

    hospital_ref = data.get("hospital_id")
    hospital_info = {"name": "Unknown Hospital", "city": "", "state": "", "phone": ""}

    if hospital_ref is not None:
        hospital_id = hospital_ref.id if hasattr(hospital_ref, "id") else str(hospital_ref)
        hospital = hospitals_cache.get(hospital_id)
        if hospital:
            location = hospital.get("location", {}) or {}
            hospital_info = {
                "id": hospital_id,
                "name": hospital.get("name", "Unknown Hospital"),
                "city": location.get("city", ""),
                "state": location.get("state", ""),
                "address": location.get("address", ""),
                "phone": hospital.get("phone", ""),
            }

    return {
        "id": doctor_doc.id,
        "name": data.get("name", ""),
        "specialty": data.get("specialty", ""),
        "bio": data.get("bio", ""),
        "contact": data.get("contact", {}),
        "next_available_slot": next_slot,
        "hospital": hospital_info,
    }


@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=["*"],
        cors_methods=["get", "post", "options"],
    )
)
def get_available_doctors(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":
        return https_fn.Response("", status=204)

    if req.method != "POST":
        return _json_response({"error": "Only POST is supported"}, 405)

    try:
        body = req.get_json(silent=True) or {}
    except Exception:
        body = {}

    symptom = (body.get("symptom") or "").strip()
    if not symptom:
        return _json_response({"error": "Missing 'symptom' in request body"}, 400)

    specialty = _map_symptom_to_specialty(symptom)
    if not specialty:
        return _json_response({
            "symptom": symptom,
            "specialty": None,
            "doctors": [],
            "message": (
                "We could not map that symptom to a specialty. "
                "Try terms like 'chest pain', 'rash', 'fever', 'child cough', "
                "'back pain', 'anxiety', or 'blurred vision'."
            ),
        }, 200)

    db = firestore.client()

    hospitals_cache: dict = {}
    for h in db.collection("hospitals").stream():
        hospitals_cache[h.id] = h.to_dict()

    now_iso = datetime.now(timezone.utc).isoformat()

    doctors_query = db.collection("doctors").where("specialty", "==", specialty).stream()

    payload = []
    for doc in doctors_query:
        entry = _build_doctor_payload(doc, hospitals_cache, now_iso)
        if entry:
            payload.append(entry)

    payload.sort(key=lambda d: d["next_available_slot"])

    return _json_response({
        "symptom": symptom,
        "specialty": specialty,
        "count": len(payload),
        "doctors": payload,
    }, 200)
