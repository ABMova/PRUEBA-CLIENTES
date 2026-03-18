from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, generate_uuid, now_utc

if TYPE_CHECKING:
    from .cliente import Cliente


class Contacto(Base):
    __tablename__ = "contactos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    cliente_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    cargo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    es_principal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    creado_en: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc)

    # Relaciones
    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="contactos")

    def __repr__(self) -> str:
        return f"<Contacto id={self.id} nombre={self.nombre!r} cliente_id={self.cliente_id}>"
