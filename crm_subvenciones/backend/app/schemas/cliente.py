import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CIF_RE = re.compile(r"^[A-HJNP-SUVW]\d{7}[0-9A-J]$", re.IGNORECASE)


class ClienteBase(BaseModel):
    nombre_comercial: str
    razon_social: str
    cif: str
    administrador: Optional[str] = None
    dni: Optional[str] = None
    email: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    codigo_postal: Optional[str] = None
    poblacion: Optional[str] = None
    provincia: Optional[str] = None
    notas: Optional[str] = None

    @field_validator("nombre_comercial")
    @classmethod
    def nombre_comercial_no_vacio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre comercial es obligatorio")
        return v

    @field_validator("razon_social")
    @classmethod
    def razon_social_no_vacia(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La razón social es obligatoria")
        return v

    @field_validator("cif")
    @classmethod
    def cif_formato(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("El CIF es obligatorio")
        if not _CIF_RE.match(v):
            raise ValueError(
                "CIF inválido. Debe empezar por letra (excepto I, K, L, M, O, R) "
                "seguida de 7 dígitos y un carácter alfanumérico. Ej: B12345678"
            )
        return v

    @field_validator("email")
    @classmethod
    def email_formato(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("El email es obligatorio")
        if not _EMAIL_RE.match(v):
            raise ValueError("Formato de email inválido")
        return v

    @field_validator("codigo_postal")
    @classmethod
    def cp_formato(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if v and (not v.isdigit() or len(v) != 5):
            raise ValueError("El código postal debe tener exactamente 5 dígitos")
        return v or None


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    nombre_comercial: Optional[str] = None
    razon_social: Optional[str] = None
    cif: Optional[str] = None
    administrador: Optional[str] = None
    dni: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    codigo_postal: Optional[str] = None
    poblacion: Optional[str] = None
    provincia: Optional[str] = None
    notas: Optional[str] = None
    activo: Optional[bool] = None

    @field_validator("nombre_comercial")
    @classmethod
    def nombre_comercial_no_vacio(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("El nombre comercial no puede estar vacío")
        return v

    @field_validator("cif")
    @classmethod
    def cif_formato(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().upper()
            if not _CIF_RE.match(v):
                raise ValueError("CIF inválido")
        return v

    @field_validator("email")
    @classmethod
    def email_formato(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().lower()
            if not _EMAIL_RE.match(v):
                raise ValueError("Formato de email inválido")
        return v

    @field_validator("codigo_postal")
    @classmethod
    def cp_formato(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if v and (not v.isdigit() or len(v) != 5):
            raise ValueError("El código postal debe tener exactamente 5 dígitos")
        return v or None


class ClienteResponse(BaseModel):
    id: str
    nombre_comercial: str
    razon_social: str
    cif: str
    administrador: Optional[str]
    dni: Optional[str]
    email: str
    telefono: Optional[str]
    direccion: Optional[str]
    codigo_postal: Optional[str]
    poblacion: Optional[str]
    provincia: Optional[str]
    notas: Optional[str]
    activo: bool
    fecha_alta: date
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


class ClienteListItem(BaseModel):
    id: str
    nombre_comercial: str
    razon_social: str
    cif: str
    email: str
    poblacion: Optional[str]
    provincia: Optional[str]
    activo: bool

    model_config = {"from_attributes": True}
