import enum
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, Boolean, Date, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum

from .base import Base, generate_uuid, now_utc

if TYPE_CHECKING:
    from .expediente import Expediente


class EstadoHito(str, enum.Enum):
    pendiente = "pendiente"
    en_curso = "en_curso"
    completado = "completado"
    vencido = "vencido"


class Hito(Base):
    __tablename__ = "hitos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    expediente_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("expedientes.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    nombre: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="Ej: Entrega memoria técnica, Justificación económica, Auditoría"
    )
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_limite: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_completado: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    estado: Mapped[EstadoHito] = mapped_column(
        SAEnum(EstadoHito), nullable=False, default=EstadoHito.pendiente
    )
    obligatorio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    orden: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Orden de visualización dentro del expediente"
    )

    creado_en: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_utc, onupdate=now_utc
    )

    expediente: Mapped["Expediente"] = relationship("Expediente", back_populates="hitos")

    def __repr__(self) -> str:
        return f"<Hito {self.nombre!r} fecha_limite={self.fecha_limite} estado={self.estado}>"
