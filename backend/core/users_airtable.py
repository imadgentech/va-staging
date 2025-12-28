from pyairtable import Table
import os
import logging
import uuid

logger = logging.getLogger(__name__)


class UsersAirtable:
    def __init__(self):
        api_key = os.getenv("AIRTABLE_API_KEY")
        base_id = os.getenv("AIRTABLE_USERS_BASE_ID")
        table_name = os.getenv("AIRTABLE_USERS_TABLE")

        if api_key and base_id and table_name:
            self.table = Table(api_key, base_id, table_name)
            logger.info("✅ Users Airtable initialized successfully")
        else:
            self.table = None
            logger.warning(
                "⚠️ Users Airtable not configured "
                f"(api_key={bool(api_key)}, base_id={bool(base_id)}, table={bool(table_name)})"
            )

    def create_user(self, data: dict):
        if not self.table:
            raise RuntimeError("Users Airtable not initialized")

        record = {
            "user_id": str(uuid.uuid4()),
            "business_name": data["business_name"],
            "full_name": data["full_name"],
            "occupation": data["occupation"],
            "email": data["email"],
            "phone": data["phone"],
            "password": data.get("password", ""), # Save the hashed password
            "status": "pending",
        }

        return self.table.create(record)

    def user_exists_by_email(self, email: str) -> bool:
        if not self.table:
            return False

        formula = f"LOWER({{email}}) = '{email.lower()}'"
        records = self.table.all(formula=formula, max_records=1)
        return len(records) > 0

    def get_user_by_email(self, email: str):
        if not self.table:
            return None

        records = self.table.all(formula=f"{{email}} = '{email}'", max_records=1)
        return records[0] if records else None

    def get_restaurant_id_for_email(self, email: str):
        user = self.get_user_by_email(email)
        if not user:
            return None

        fields = user.get("fields", {})
        return fields.get("restaurant_id")
