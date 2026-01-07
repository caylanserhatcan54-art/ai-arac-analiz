# backend/firebase.py
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")

if not service_account_json:
    raise RuntimeError("FIREBASE_SERVICE_ACCOUNT env not set")

cred_dict = json.loads(service_account_json)
cred = credentials.Certificate(cred_dict)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()
