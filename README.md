# Hospital Scheduler

A web-based hospital scheduling application that helps patients find available doctors based on their symptoms. Built with Python Cloud Functions, Firebase Firestore, Firebase Hosting, and a vanilla HTML/CSS/JS frontend.

## Features

- Symptom-to-specialty matching with a curated mapping (covers Cardiology, Dermatology, General Practice, Pediatrics, Orthopedics, Psychiatry, Ophthalmology, and Gastroenterology).
- HTTP Cloud Function (`get_available_doctors`) that queries Firestore for doctors with future availability.
- Single-page frontend with a teal/navy medical aesthetic, responsive layout, and ranked doctor result cards.
- Synthetic data generator using `faker` that produces realistic hospitals, doctors, patients, and appointments.

## Project structure

```
hospital-scheduler/
├── firebase.json              # Hosting + Functions + Firestore config
├── firestore.rules            # Public read on doctors/hospitals; restricted writes
├── firestore.indexes.json     # Composite indexes
├── README.md
├── public/
│   └── index.html             # Single-page frontend (HTML + CSS + JS inline)
├── functions/
│   ├── main.py                # get_available_doctors Cloud Function
│   └── requirements.txt
└── seed/
    ├── seed_firestore.py      # Synthetic data generator
    └── requirements.txt
```

## Setup

### 1. Install the Firebase CLI

```bash
npm install -g firebase-tools
```

### 2. Authenticate

```bash
firebase login
```

### 3. Connect this directory to a Firebase project

```bash
cd hospital-scheduler
firebase use --add
```

Select an existing Firebase project (or create one in the [Firebase console](https://console.firebase.google.com/) first). You'll also need to enable **Cloud Firestore** and upgrade to the **Blaze plan** since Cloud Functions require it.

### 4. Install Python dependencies

For the Cloud Function:

```bash
cd functions
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
cd ..
```

For the seed script:

```bash
cd seed
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
cd ..
```

## Seeding data

### Against real Firestore

Download a service account key from **Firebase Console → Project Settings → Service Accounts → Generate new private key**, then:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/serviceAccount.json
source seed/venv/bin/activate
python seed/seed_firestore.py --wipe
```

### Against the local emulator

```bash
firebase emulators:start --only firestore
# in another terminal:
export FIRESTORE_EMULATOR_HOST=localhost:8080
source seed/venv/bin/activate
python seed/seed_firestore.py --project hospital-schedular-nephealer --wipe
```

The script creates:

- 5 hospitals (New York, Los Angeles, Chicago, Houston, Seattle)
- 20 doctors across 8 specialties with realistic bios, contacts, and 6 future availability slots each
- 30 patients with realistic names, contact info, and symptom arrays
- 40 appointments that link patients to doctors with matching specialties

The data is generated with fixed random seeds (`Faker.seed(42)`) so seeded data is reproducible.

## Deploy

```bash
firebase deploy
```

This deploys the Cloud Function, Firestore rules + indexes, and the static frontend to Firebase Hosting. Once finished, open the Hosting URL printed in the CLI output to use the app.

## Local development

```bash
firebase emulators:start
```

This boots Functions, Firestore, and Hosting emulators together. Visit `http://localhost:5000` to see the app. The Emulator UI is at `http://localhost:4000`.

If you've already seeded the real project, the deployed frontend at the Hosting URL will work end-to-end immediately.

## How the matching works

1. The user types a symptom (e.g. `chest pain`) on the frontend.
2. The frontend POSTs `{"symptom": "chest pain"}` to `/api/get_available_doctors`.
3. `firebase.json` rewrites that path to the `get_available_doctors` Cloud Function.
4. The function maps the symptom to a specialty using `SYMPTOM_SPECIALTY_MAP` (with fuzzy substring matching as a fallback).
5. It queries `doctors` where `specialty == <mapped>`, filters out doctors with no future `available_slots`, joins in hospital info, and returns the list ranked by soonest availability.

## Trying it out

After seeding, try these symptoms to see the matching feature in action:

- `chest pain` → Cardiology
- `rash` → Dermatology
- `fever` → General Practice
- `child cough` → Pediatrics
- `back pain` → Orthopedics
- `anxiety` → Psychiatry
- `blurred vision` → Ophthalmology
- `stomach pain` → Gastroenterology

## Notes

- The `Book` button currently shows a confirmation `alert` as a placeholder — wiring it up to write an `appointments` document and remove the booked slot from the doctor's `available_slots` is the natural next step.
- Firestore rules permit public read of `doctors` and `hospitals` so the frontend can query directly if you want to skip the Cloud Function. Writes are locked down.
- The Cloud Function runs on the Python 3.12 runtime declared in `firebase.json`. Supported runtimes are `python310`, `python311`, and `python312` — Python 3.13/3.14 are not yet supported by Cloud Functions.
