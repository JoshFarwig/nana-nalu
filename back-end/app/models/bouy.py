from typing import Optional, Union, List
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class Bouy(Base):
    __tablename__ = "bouys"
