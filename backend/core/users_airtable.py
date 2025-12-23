from pyairtable import Table
import os
from datetime import datetime
import uuid

class UsersAirtable:
    def __init__(self):
        self.table = Table(
            os.getenv("AIRTABLE_API_KEY"),
            os.getenv("AIRTABLE_USERS_BASE_ID"),
            os.getenv("AIRTABLE_USERS_TABLE")
        )

    def create_user(self, data: dict):
        record = {
            "user_id": str(uuid.uuid4()),
            "business_name": data["business_name"],
            "full_name": data["full_name"],
            "occupation": data["occupation"],
            "email": data["email"],
            "phone": data["phone"],
            "status": "pending"
        }
        return self.table.create(record)

    def user_exists_by_email(self, email: str) -> bool:
        formula = f"LOWER({{email}}) = '{email.lower()}'"
        records = self.table.all(formula=formula, max_records=1)
        return len(records) > 0
    
    def get_user_by_email(self, email: str):
        records = self.table.all(formula=f"{{email}} = '{email}'")
        return records[0] if records else None

    def get_restaurant_id_for_email(self, email: str):
        user = self.get_user_by_email(email)
        if not user:
            return None
        fields = user.get("fields", {})
        return fields.get("restaurant_id")


