from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[type[datetime], DateTime]] = {
        datetime: DateTime(timezone=True)
    }
