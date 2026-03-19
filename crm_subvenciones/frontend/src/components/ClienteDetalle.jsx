export default function ClienteDetalle({ cliente, onEditar, onVolver }) {
  const campo = (label, valor) => (
    <div className="detalle-campo">
      <span className="detalle-label">{label}</span>
      <span className="detalle-valor">{valor || <em className="vacio">—</em>}</span>
    </div>
  )

  return (
    <div className="detalle-card">
      <div className="detalle-header">
        <div>
          <h2>{cliente.nombre_comercial}</h2>
          <p className="detalle-razon">{cliente.razon_social}</p>
        </div>
        <span className={`badge ${cliente.activo ? 'badge-activo' : 'badge-inactivo'}`}>
          {cliente.activo ? 'Activo' : 'Inactivo'}
        </span>
      </div>

      <div className="detalle-seccion">
        <h3>Identificación</h3>
        <div className="detalle-grid">
          {campo('CIF', cliente.cif)}
          {campo('Email', cliente.email)}
          {campo('Teléfono', cliente.telefono)}
        </div>
      </div>

      <div className="detalle-seccion">
        <h3>Representante legal</h3>
        <div className="detalle-grid">
          {campo('Administrador', cliente.administrador)}
          {campo('DNI', cliente.dni)}
        </div>
      </div>

      <div className="detalle-seccion">
        <h3>Dirección</h3>
        <div className="detalle-grid">
          {campo('Dirección', cliente.direccion)}
          {campo('Código postal', cliente.codigo_postal)}
          {campo('Población', cliente.poblacion)}
          {campo('Provincia', cliente.provincia)}
        </div>
      </div>

      {cliente.notas && (
        <div className="detalle-seccion">
          <h3>Notas</h3>
          <p className="detalle-notas">{cliente.notas}</p>
        </div>
      )}

      <div className="detalle-meta">
        <span>Alta: {new Date(cliente.fecha_alta).toLocaleDateString('es-ES')}</span>
        <span>Modificado: {new Date(cliente.actualizado_en).toLocaleString('es-ES')}</span>
      </div>

      <div className="form-actions">
        <button className="btn btn-secondary" onClick={onVolver}>← Volver</button>
        <button className="btn btn-primary" onClick={onEditar}>Editar</button>
      </div>
    </div>
  )
}
