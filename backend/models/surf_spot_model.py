# from typing import Optional, Union, List
# from sqlalchemy import ForeignKey, String, Float
# from sqlalchemy.orm import Mapped, mapped_column, relationship
# from .base import Base


# class SurfSpot(Base):
#     __tablename__ = "surf_spots"

#     id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
#     name: Mapped[str] = mapped_column(String(255), nullable=False)
#     description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     # TODO: Replace with geometry column / point column
#     # geometry: Mapped[Geometry] = mapped_column(Geometry(geometry_type='POINT', srid=4326), nullable=False)
