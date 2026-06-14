# Importing all table classes here ensures SQLModel's metadata is populated
# before db.create_db_and_tables() calls SQLModel.metadata.create_all(engine).
from models.customer import Customer
from models.order import Order
from models.segment import Segment
from models.campaign import Campaign
from models.message import Message

__all__ = ["Customer", "Order", "Segment", "Campaign", "Message"]
