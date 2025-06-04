from typing import Optional, Union, List
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class SurfSpot(Base):
    __tablename__ = "surf_spots"
