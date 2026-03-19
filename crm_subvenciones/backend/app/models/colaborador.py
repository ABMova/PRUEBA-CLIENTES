from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, generate_uuid, now_utc

if TYPE_CHECKING:
    from .expediente import Expediente


class Colaborador(Base):
    __tablename__ = "colaboradores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    nif: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, unique=True)

    creado_en: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_utc, onupdate=now_utc
    )

    expedientes: Mapped[List["Expediente"]] = relationship(
        "Expediente",
        secondary="expediente_colaboradores",
        back_populates="colaboradores"
    )

    def __repr__(self) -> str:
        return f"<Colaborador id={self.id} nombre={self.nombre!r}>"
