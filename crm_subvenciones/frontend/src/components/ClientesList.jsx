import { useState, useEffect, useCallback } from 'react'
import { listarClientes, eliminarCliente } from '../api/clientes'

export default function ClientesList({ onNuevo, onVer, onEditar }) {
  const [clientes, setClientes] = useState([])
  const [busqueda, setBusqueda] = useState('')
  const [filtroActivo, setFiltroActivo] = useState('')
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState(null)
  const [confirmarEliminar, setConfirmarEliminar] = useState(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    setError(null)
    try {
      const params = { q: busqueda }
      if (filtroActivo !== '') params.activo = filtroActivo === 'activo'
      const data = await listarClientes(params)
      setClientes(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setCargando(false)
    }
  }, [busqueda, filtroActivo])

  useEffect(() => {
    const t = setTimeout(cargar, 300)
    return () => clearTimeout(t)
  }, [cargar])

  async function handleEliminar(cliente) {
    try {
      await eliminarCliente(cliente.id)
      setConfirmarEliminar(null)
      cargar()
    } catch (e) {
      alert('Error al eliminar: ' + e.message)
    }
  }

  return (
    <div>
      <div className="toolbar">
        <h1>Clientes</h1>
        <button className="btn btn-primary" onClick={onNuevo}>+ Nuevo cliente</button>
      </div>

      <div className="filtros">
        <input
          className="busqueda"
          type="search"
          placeholder="Buscar por nombre, razón social, CIF o email…"
          value={busqueda}
          onChange={e => setBusqueda(e.target.value)}
        />
        <select value={filtroActivo} onChange={e => setFiltroActivo(e.target.value)}>
          <option value="">Todos</option>
          <option value="activo">Activos</option>
          <option value="inactivo">Inactivos</option>
        </select>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {cargando ? (
        <p className="cargando">Cargando…</p>
      ) : clientes.length === 0 ? (
        <div className="vacio-msg">
          {busqueda ? `Sin resultados para "${busqueda}"` : 'No hay clientes. Crea el primero.'}
        </div>
      ) : (
        <div className="tabla-wrapper">
          <table className="tabla">
            <thead>
              <tr>
                <th>Nombre comercial</th>
                <th>Razón social</th>
                <th>CIF</th>
                <th>Email</th>
                <th>Población</th>
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {clientes.map(c => (
                <tr key={c.id}>
                  <td>
                    <button className="link-btn" onClick={() => onVer(c.id)}>
                      {c.nombre_comercial}
                    </button>
                  </td>
                  <td>{c.razon_social}</td>
                  <td className="mono">{c.cif}</td>
                  <td>{c.email}</td>
                  <td>{c.poblacion || '—'}</td>
                  <td>
                    <span className={`badge ${c.activo ? 'badge-activo' : 'badge-inactivo'}`}>
                      {c.activo ? 'Activo' : 'Inactivo'}
                    </span>
                  </td>
                  <td className="acciones">
                    <button className="btn btn-sm btn-secondary" onClick={() => onEditar(c.id)}>
                      Editar
                    </button>
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => setConfirmarEliminar(c)}
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="total-registros">{clientes.length} cliente{clientes.length !== 1 ? 's' : ''}</p>
        </div>
      )}

      {confirmarEliminar && (
        <div className="modal-overlay" onClick={() => setConfirmarEliminar(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>Confirmar eliminación</h3>
            <p>
              ¿Eliminar a <strong>{confirmarEliminar.nombre_comercial}</strong>?
              Esta acción no se puede deshacer.
            </p>
            <div className="form-actions">
              <button className="btn btn-secondary" onClick={() => setConfirmarEliminar(null)}>
                Cancelar
              </button>
              <button className="btn btn-danger" onClick={() => handleEliminar(confirmarEliminar)}>
                Sí, eliminar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
