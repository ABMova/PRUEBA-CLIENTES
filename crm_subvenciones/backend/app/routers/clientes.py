from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.cliente import Cliente
from ..schemas.cliente import ClienteCreate, ClienteUpdate, ClienteResponse, ClienteListItem

router = APIRouter(prefix="/clientes", tags=["clientes"])


def _get_or_404(db: Session, cliente_id: str) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return cliente


@router.get("", response_model=List[ClienteListItem])
def listar_clientes(
    q: Optional[str] = Query(None, description="Búsqueda por nombre comercial, razón social, CIF o email"),
    activo: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Cliente)

    if q:
        termino = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Cliente.nombre_comercial.ilike(termino),
                Cliente.razon_social.ilike(termino),
                Cliente.cif.ilike(termino),
                Cliente.email.ilike(termino),
            )
        )

    if activo is not None:
        query = query.filter(Cliente.activo == activo)

    query = query.order_by(Cliente.nombre_comercial)
    return query.offset(skip).limit(limit).all()


@router.post("", response_model=ClienteResponse, status_code=status.HTTP_201_CREATED)
def crear_cliente(data: ClienteCreate, db: Session = Depends(get_db)):
    existente = db.query(Cliente).filter(
        func.upper(Cliente.cif) == data.cif.upper()
    ).first()
    if existente:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un cliente con el CIF {data.cif}"
        )

    cliente = Cliente(**data.model_dump())
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.get("/{cliente_id}", response_model=ClienteResponse)
def obtener_cliente(cliente_id: str, db: Session = Depends(get_db)):
    return _get_or_404(db, cliente_id)


@router.patch("/{cliente_id}", response_model=ClienteResponse)
def actualizar_cliente(
    cliente_id: str,
    data: ClienteUpdate,
    db: Session = Depends(get_db),
):
    cliente = _get_or_404(db, cliente_id)

    cambios = data.model_dump(exclude_unset=True)

    if "cif" in cambios:
        nuevo_cif = cambios["cif"].upper()
        duplicado = db.query(Cliente).filter(
            func.upper(Cliente.cif) == nuevo_cif,
            Cliente.id != cliente_id,
        ).first()
        if duplicado:
            raise HTTPException(
                status_code=409,
                detail=f"Ya existe otro cliente con el CIF {nuevo_cif}"
            )

    for campo, valor in cambios.items():
        setattr(cliente, campo, valor)

    db.commit()
    db.refresh(cliente)
    return cliente


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cliente(cliente_id: str, db: Session = Depends(get_db)):
    cliente = _get_or_404(db, cliente_id)
    db.delete(cliente)
    db.commit()
