import enum
from datetime import date, datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Text, Boolean, Date, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, generate_uuid, now_utc

if TYPE_CHECKING:
    from .contacto import Contacto
    from .documento import Documento


class TamanoEmpresa(str, enum.Enum):
    micropyme = "micropyme"
    pyme = "pyme"
    grande = "grande"


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )

    # Identificación
    nombre_comercial: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    razon_social: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    cif: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True
    )

    # Representante legal
    administrador: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    dni: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Contacto
    email: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Ubicación
    direccion: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    codigo_postal: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    poblacion: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    provincia: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Actividad económica (conservados para compatibilidad futura)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    codigo_cnae: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True,
        comment="Código CNAE-2009, ej: 6201"
    )
    tamano_empresa: Mapped[Optional[TamanoEmpresa]] = mapped_column(
        SAEnum(TamanoEmpresa), nullable=True
    )

    # Control
    fecha_alta: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Auditoría
    creado_en: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_utc, onupdate=now_utc
    )

    # Relaciones
    contactos: Mapped[List["Contacto"]] = relationship(
        "Contacto", back_populates="cliente",
        cascade="all, delete-orphan",
        order_by="Contacto.es_principal.desc()"
    )
    documentos: Mapped[List["Documento"]] = relationship(
        "Documento",
        primaryjoin="and_(Documento.entidad_tipo=='cliente', foreign(Documento.entidad_id)==Cliente.id)",
        viewonly=True,
        order_by="Documento.fecha_subida.desc()"
    )

    def __repr__(self) -> str:
        return f"<Cliente id={self.id} nombre_comercial={self.nombre_comercial!r}>"
