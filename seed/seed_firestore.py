"""Seed Firestore with synthetic hospital, doctor, patient, and appointment data.

Usage:
    # Against real Firestore:
    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/serviceAccount.json
    python seed/seed_firestore.py

    # Against local emulator:
    export FIRESTORE_EMULATOR_HOST=localhost:8080
    python seed/seed_firestore.py --project hospital-schedular-nephealer
"""

from __future__ import annotations

import argparse
import os
import random
from datetime import datetime, timedelta, timezone

import firebase_admin
from faker import Faker
from firebase_admin import credentials, firestore

fake = Faker("en_US")
Faker.seed(42)
random.seed(42)


SYMPTOM_SPECIALTY_MAP: dict[str, str] = {
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

SPECIALTIES = sorted(set(SYMPTOM_SPECIALTY_MAP.values()))

CITY_PRESETS = [
    {"city": "New York",     "state": "NY", "lat": 40.7128,  "lng": -74.0060},
    {"city": "Los Angeles",  "state": "CA", "lat": 34.0522,  "lng": -118.2437},
    {"city": "Chicago",      "state": "IL", "lat": 41.8781,  "lng": -87.6298},
    {"city": "Houston",      "state": "TX", "lat": 29.7604,  "lng": -95.3698},
    {"city": "Seattle",      "state": "WA", "lat": 47.6062,  "lng": -122.3321},
]

HOSPITAL_SUFFIXES = [
    "General Hospital",
    "Medical Center",
    "Regional Hospital",
    "Memorial Hospital",
    "University Hospital",
]

DOCTOR_BIOS: dict[str, list[str]] = {
    "Cardiology": [
        "Board-certified cardiologist focused on preventive heart care.",
        "Specializes in arrhythmia management and echocardiography.",
        "Interventional cardiologist with 15 years of clinical experience.",
    ],
    "Dermatology": [
        "Treats acne, eczema, and complex skin conditions.",
        "Cosmetic and medical dermatologist with a pediatric subspecialty.",
        "Mohs-trained dermatologist focused on skin cancer screening.",
    ],
    "General Practice": [
        "Family physician offering whole-person primary care.",
        "Primary care doctor with a focus on chronic disease management.",
        "Internal medicine generalist treating adult patients of all ages.",
    ],
    "Pediatrics": [
        "Pediatrician dedicated to newborns, children, and adolescents.",
        "General pediatrician with a focus on developmental milestones.",
        "Pediatric care provider with a calm, family-friendly approach.",
    ],
    "Orthopedics": [
        "Orthopedic surgeon specializing in joints and sports injuries.",
        "Non-operative orthopedic care with a focus on rehab.",
        "Treats fractures, sprains, and chronic back pain.",
    ],
    "Psychiatry": [
        "Psychiatrist treating mood, anxiety, and sleep disorders.",
        "Integrates medication management with therapy referrals.",
        "Adult psychiatry with a focus on trauma-informed care.",
    ],
    "Ophthalmology": [
        "Comprehensive eye care including cataract and glaucoma management.",
        "Treats refractive errors, dry eye, and retinal disorders.",
        "Ophthalmologist with a subspecialty in pediatric vision.",
    ],
    "Gastroenterology": [
        "GI specialist for reflux, IBS, and endoscopic procedures.",
        "Focuses on inflammatory bowel disease and nutrition.",
        "Treats abdominal pain, nausea, and digestive disorders.",
    ],
}

HOSPITAL_SERVICE_POOL = [
    "Emergency",
    "Cardiology",
    "Dermatology",
    "Pediatrics",
    "Orthopedics",
    "Psychiatry",
    "Ophthalmology",
    "Gastroenterology",
    "Lab Testing",
    "Imaging",
    "Maternity",
    "Pharmacy",
    "Surgery",
    "Rehabilitation",
]


def initialize_firebase(project_id: str | None, credentials_path: str | None) -> None:
    if firebase_admin._apps:
        return

    if credentials_path:
        cred = credentials.Certificate(credentials_path)
        options = {"projectId": project_id} if project_id else None
        firebase_admin.initialize_app(cred, options)
    elif os.getenv("FIRESTORE_EMULATOR_HOST"):
        # Emulator mode — no real credentials needed.
        options = {"projectId": project_id or "hospital-schedular-nephealer"}
        firebase_admin.initialize_app(options=options)
    else:
        options = {"projectId": project_id} if project_id else None
        firebase_admin.initialize_app(options=options)


def wipe_collection(db, name: str) -> None:
    docs = list(db.collection(name).stream())
    if not docs:
        return
    batch = db.batch()
    for i, doc in enumerate(docs, 1):
        batch.delete(doc.reference)
        if i % 400 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()
    print(f"  wiped {len(docs)} existing {name}")


def generate_available_slots(count: int | None = None) -> list[str]:
    """Build 5-8 unique future slots on weekdays, between 8am and 5pm UTC."""
    if count is None:
        count = random.randint(5, 8)
    slots: list[str] = []
    base = datetime.now(timezone.utc)
    used: set[str] = set()
    while len(slots) < count:
        days_ahead = random.randint(1, 30)
        candidate = base + timedelta(days=days_ahead)
        if candidate.weekday() >= 5:
            continue
        hour = random.choice([8, 9, 10, 11, 13, 14, 15, 16])
        minute = random.choice([0, 30])
        slot = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
        iso = slot.isoformat()
        if iso in used:
            continue
        used.add(iso)
        slots.append(iso)
    return sorted(slots)


def seed_hospitals(db) -> list[tuple[str, dict]]:
    print("Seeding hospitals...")
    hospitals: list[tuple[str, dict]] = []
    for i, preset in enumerate(CITY_PRESETS):
        suffix = HOSPITAL_SUFFIXES[i % len(HOSPITAL_SUFFIXES)]
        name = f"{preset['city']} {suffix}"
        services = random.sample(HOSPITAL_SERVICE_POOL, k=random.randint(6, 10))
        if "Emergency" not in services:
            services.append("Emergency")

        doc = {
            "name": name,
            "location": {
                "address": fake.street_address(),
                "city": preset["city"],
                "state": preset["state"],
                "lat": preset["lat"],
                "lng": preset["lng"],
            },
            "services": services,
            "phone": fake.phone_number(),
        }

        ref = db.collection("hospitals").document()
        ref.set(doc)
        hospitals.append((ref.id, doc))
        print(f"  + {name} ({ref.id})")
    return hospitals


def seed_doctors(db, hospitals: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    print("Seeding doctors...")
    doctors: list[tuple[str, dict]] = []
    specialty_cycle: list[str] = []
    while len(specialty_cycle) < 20:
        specialty_cycle.extend(SPECIALTIES)
    specialty_cycle = specialty_cycle[:20]
    random.shuffle(specialty_cycle)

    for i in range(20):
        specialty = specialty_cycle[i]
        hospital_id, _ = random.choice(hospitals)
        first = fake.first_name()
        last = fake.last_name()
        name = f"Dr. {first} {last}"
        email_local = f"{first}.{last}".lower().replace("'", "")
        bio = random.choice(DOCTOR_BIOS[specialty])

        doc = {
            "name": name,
            "specialty": specialty,
            "contact": {
                "phone": fake.phone_number(),
                "email": f"{email_local}@hospital-scheduler.example",
            },
            "hospital_id": hospital_id,
            "available_slots": generate_available_slots(),
            "bio": bio,
        }

        ref = db.collection("doctors").document()
        ref.set(doc)
        doctors.append((ref.id, doc))
        print(f"  + {name} — {specialty} @ {hospital_id}")
    return doctors


def realistic_symptoms_for(specialty_pool: list[str]) -> list[str]:
    """Pick a small set of symptoms aligned with random specialties."""
    specialty = random.choice(specialty_pool)
    candidates = [s for s, sp in SYMPTOM_SPECIALTY_MAP.items() if sp == specialty]
    count = random.randint(1, 3)
    if len(candidates) <= count:
        return candidates
    return random.sample(candidates, k=count)


def seed_patients(db) -> list[tuple[str, dict]]:
    print("Seeding patients...")
    patients: list[tuple[str, dict]] = []
    for _ in range(30):
        name = fake.name()
        email_local = name.lower().replace(" ", ".").replace("'", "")
        symptoms = realistic_symptoms_for(SPECIALTIES)

        doc = {
            "name": name,
            "contact": {
                "phone": fake.phone_number(),
                "email": f"{email_local}@example.com",
            },
            "symptoms": symptoms,
            "appointments": [],
        }

        ref = db.collection("patients").document()
        ref.set(doc)
        patients.append((ref.id, doc))
    print(f"  + {len(patients)} patients")
    return patients


def pick_doctor_for_symptom(
    symptom: str, doctors: list[tuple[str, dict]]
) -> tuple[str, dict] | None:
    specialty = SYMPTOM_SPECIALTY_MAP.get(symptom)
    if not specialty:
        return None
    matching = [d for d in doctors if d[1]["specialty"] == specialty]
    if not matching:
        return None
    return random.choice(matching)


def seed_appointments(
    db,
    patients: list[tuple[str, dict]],
    doctors: list[tuple[str, dict]],
) -> int:
    print("Seeding appointments...")
    statuses = ["scheduled", "scheduled", "scheduled", "completed", "cancelled"]
    written = 0
    patient_updates: dict[str, list[dict]] = {}

    attempts = 0
    while written < 40 and attempts < 400:
        attempts += 1
        patient_id, patient = random.choice(patients)
        if not patient.get("symptoms"):
            continue
        symptom = random.choice(patient["symptoms"])
        match = pick_doctor_for_symptom(symptom, doctors)
        if not match:
            continue
        doctor_id, doctor = match
        slot = random.choice(doctor["available_slots"])
        hospital_ref = doctor["hospital_id"]
        hospital_id = hospital_ref.id if hasattr(hospital_ref, "id") else str(hospital_ref)
        status = random.choice(statuses)

        appt = {
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "hospital_id": hospital_id,
            "datetime": slot,
            "symptom_reason": symptom,
            "status": status,
        }
        db.collection("appointments").add(appt)
        written += 1

        patient_updates.setdefault(patient_id, []).append({
            "doctor_id": doctor_id,
            "datetime": slot,
            "status": status,
        })

    for patient_id, appts in patient_updates.items():
        db.collection("patients").document(patient_id).update({"appointments": appts})

    print(f"  + {written} appointments written")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Firestore with hospital scheduler data")
    parser.add_argument("--project", help="Firebase project ID", default=os.getenv("GCLOUD_PROJECT"))
    parser.add_argument(
        "--credentials",
        help="Path to service account JSON",
        default=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="Delete existing documents before seeding",
    )
    args = parser.parse_args()

    initialize_firebase(args.project, args.credentials)
    db = firestore.client()

    if args.wipe:
        print("Wiping existing collections...")
        for name in ("appointments", "patients", "doctors", "hospitals"):
            wipe_collection(db, name)

    hospitals = seed_hospitals(db)
    doctors = seed_doctors(db, hospitals)
    patients = seed_patients(db)
    seed_appointments(db, patients, doctors)

    print("\nDone. Try the symptom search with terms like:")
    print('  "chest pain", "rash", "fever", "child cough",')
    print('  "back pain", "anxiety", "blurred vision", "stomach pain"')


if __name__ == "__main__":
    main()
