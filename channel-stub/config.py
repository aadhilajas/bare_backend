import os
from dotenv import load_dotenv

load_dotenv()

CRM_RECEIPT_URL: str = os.getenv("CRM_RECEIPT_URL", "http://localhost:8000/api/receipts")
