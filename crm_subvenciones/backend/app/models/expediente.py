import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    String, Text, Boolean, Date, DateTime, Numeric,
    Enum as SAEnum, Integer, ForeignKey, Table, Column
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, generate_uuid, now_utc

if TYPE_CHECKING:
    from .cliente import Cliente
    from .organismo import Organismo
    from .colaborador import Colaborador
    from .hito import Hito
    from .documento import Documento


class EstadoExpediente(str, enum.Enum):
    borrador = "borrador"
    presentado = "presentado"
    aprobado = "aprobado"
    denegado = "denegado"
    desistido = "desistido"


class TipoAyuda(str, enum.Enum):
    neotec = "NEOTEC"
    ico = "ICO"
    cdti = "CDTI"
    horizon = "HORIZON"
    ivace = "IVACE"
    otro = "otro"


# Tabla asociativa N↔N expedientes ↔ colaboradores
expediente_colaboradores = Table(
    "expediente_colaboradores",
    Base.metadata,
    Column(
        "expediente_id", String(36),
        ForeignKey("expedientes.id", ondelete="CASCADE"),
        primary_key=True
    ),
    Column(
        "colaborador_id", String(36),
        ForeignKey("colaboradores.id", ondelete="CASCADE"),
        primary_key=True
    ),
    Column("rol_en_expediente", String(100), nullable=True),
)


class Expediente(Base):
    __tablename__ = "expedientes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    numero_exp: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True,
        comment="Ej: CDTI-2024-001. Introducido manualmente por el usuario."
    )
    descripcion_proyecto: Mapped[str] = mapped_column(String(300), nullable=False)

    # Claves foráneas
    cliente_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    organismo_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("organismos.id", ondelete="SET NULL"),
        nullable=True, index=True
    )

    # Fechas
    fecha_apertura: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    fecha_presentacion: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fecha_resolucion: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Estado y tipo
    estado: Mapped[EstadoExpediente] = mapped_column(
        SAEnum(EstadoExpediente), nullable=False, default=EstadoExpediente.borrador
    )
    tipo_ayuda: Mapped[Optional[TipoAyuda]] = mapped_column(
        SAEnum(TipoAyuda), nullable=True
    )

    # Económicos
    presupuesto_elegible: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True,
        comment="Base sobre la que aplica el porcentaje de subvención"
    )
    porcentaje_subvencion: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True,
        comment="Porcentaje de subvención sobre presupuesto elegible. Ej: 70.00"
    )
    monto_solicitado: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    monto_aprobado: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    # Texto libre
    notas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Auditoría
    creado_en: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_utc, onupdate=now_utc
    )

    # Relaciones
    cliente: Mapped["Cliente"] = relationship("Cliente", backref="expedientes")
    organismo: Mapped[Optional["Organismo"]] = relationship("Organismo", backref="expedientes")
    colaboradores: Mapped[List["Colaborador"]] = relationship(
        "Colaborador",
        secondary=expediente_colaboradores,
        back_populates="expedientes"
    )
    hitos: Mapped[List["Hito"]] = relationship(
        "Hito", back_populates="expediente",
        cascade="all, delete-orphan",
        order_by="Hito.orden, Hito.fecha_limite"
    )
    documentos: Mapped[List["Documento"]] = relationship(
        "Documento",
        primaryjoin="and_(Documento.entidad_tipo=='expediente', foreign(Documento.entidad_id)==Expediente.id)",
        viewonly=True,
        order_by="Documento.fecha_subida.desc()"
    )

    @property
    def monto_calculado(self) -> Optional[Decimal]:
        """Calcula monto solicitado desde presupuesto * porcentaje si no está introducido."""
        if self.monto_solicitado:
            return self.monto_solicitado
        if self.presupuesto_elegible and self.porcentaje_subvencion:
            return (self.presupuesto_elegible * self.porcentaje_subvencion / 100).quantize(Decimal("0.01"))
        return None

    def __repr__(self) -> str:
        return f"<Expediente {self.numero_exp!r} estado={self.estado} cliente_id={self.cliente_id}>"
