from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, generate_uuid, now_utc


class Documento(Base):
    """
    Tabla polimórfica: un documento puede pertenecer a cualquier entidad.
    entidad_tipo: 'cliente' | 'expediente' | 'organismo' | 'colaborador' | 'resumen'
    entidad_id:   UUID del registro al que pertenece
    """
    __tablename__ = "documentos"

    __table_args__ = (
        Index("ix_documentos_entidad", "entidad_tipo", "entidad_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Nombre que escribe el usuario en la UI
    nombre_personalizado: Mapped[str] = mapped_column(String(200), nullable=False)

    # Metadatos del fichero físico
    nombre_fichero: Mapped[str] = mapped_column(String(300), nullable=False)
    ruta: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo_mime: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tamano_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Polimorfismo
    entidad_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    entidad_id: Mapped[str] = mapped_column(String(36), nullable=False)

    fecha_subida: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc)

    def __repr__(self) -> str:
        return (
            f"<Documento id={self.id} "
            f"nombre={self.nombre_personalizado!r} "
            f"entidad={self.entidad_tipo}:{self.entidad_id}>"
        )
