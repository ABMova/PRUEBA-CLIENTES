import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Text, Boolean, Date, DateTime, Numeric, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, generate_uuid, now_utc


class TipoOrganismo(str, enum.Enum):
    nacional = "nacional"
    autonomico = "autonómico"
    europeo = "europeo"


class InstrumentoAyuda(str, enum.Enum):
    fondo_perdido = "fondo_perdido"
    prestamo = "prestamo"
    bonificacion = "bonificacion"
    mixto = "mixto"


class Organismo(Base):
    __tablename__ = "organismos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    nombre: Mapped[str] = mapped_column(
        String(150), nullable=False, unique=True, index=True,
        comment="Ej: CDTI, ICO, IVACE, AEI, Comisión Europea"
    )
    tipo: Mapped[TipoOrganismo] = mapped_column(SAEnum(TipoOrganismo), nullable=False)
    instrumento: Mapped[InstrumentoAyuda] = mapped_column(
        SAEnum(InstrumentoAyuda), nullable=False,
        comment="Naturaleza económica de la ayuda"
    )

    # Límites económicos de la convocatoria
    intensidad_maxima: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True,
        comment="% máximo de ayuda sobre presupuesto elegible. Ej: 70.00"
    )
    presupuesto_max_proyecto: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True,
        comment="Importe máximo concedible por proyecto en €"
    )

    # Convocatoria
    url_convocatoria: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    requisitos_legales: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Requisitos mínimos: forma jurídica, antigüedad, CNAE admitidos, etc."
    )
    plazo_apertura: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    plazo_cierre: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Gestor del organismo
    contacto_gestor: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    email_gestor: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    notas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Auditoría
    creado_en: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_utc, onupdate=now_utc
    )

    def __repr__(self) -> str:
        return f"<Organismo {self.nombre!r} tipo={self.tipo} instrumento={self.instrumento}>"
