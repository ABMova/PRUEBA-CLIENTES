import { useState, useCallback } from 'react'
import ClientesList from './components/ClientesList'
import ClienteForm from './components/ClienteForm'
import ClienteDetalle from './components/ClienteDetalle'
import { crearCliente, actualizarCliente, obtenerCliente } from './api/clientes'

// Vistas posibles: 'lista' | 'nuevo' | 'editar' | 'detalle'
export default function App() {
  const [vista, setVista] = useState('lista')
  const [clienteActual, setClienteActual] = useState(null)
  const [error, setError] = useState(null)
  const [cargando, setCargando] = useState(false)

  async function abrirEditar(id) {
    setCargando(true)
    setError(null)
    try {
      const c = await obtenerCliente(id)
      setClienteActual(c)
      setVista('editar')
    } catch (e) {
      setError(e.message)
    } finally {
      setCargando(false)
    }
  }

  async function abrirDetalle(id) {
    setCargando(true)
    setError(null)
    try {
      const c = await obtenerCliente(id)
      setClienteActual(c)
      setVista('detalle')
    } catch (e) {
      setError(e.message)
    } finally {
      setCargando(false)
    }
  }

  async function guardarNuevo(data) {
    setCargando(true)
    setError(null)
    try {
      await crearCliente(data)
      setVista('lista')
    } catch (e) {
      setError(e.message)
    } finally {
      setCargando(false)
    }
  }

  async function guardarEdicion(data) {
    setCargando(true)
    setError(null)
    try {
      await actualizarCliente(clienteActual.id, data)
      setVista('lista')
    } catch (e) {
      setError(e.message)
    } finally {
      setCargando(false)
    }
  }

  function irALista() {
    setVista('lista')
    setClienteActual(null)
    setError(null)
  }

  return (
    <div className="app-container">
      <header className="app-header">
        <span className="app-logo" onClick={irALista}>CRM Subvenciones</span>
        <nav>
          <button className={`nav-link ${vista === 'lista' ? 'activo' : ''}`} onClick={irALista}>
            Clientes
          </button>
        </nav>
      </header>

      <main className="app-main">
        {cargando && vista === 'lista' && <p className="cargando">Cargando…</p>}

        {vista === 'lista' && (
          <ClientesList
            onNuevo={() => { setClienteActual(null); setError(null); setVista('nuevo') }}
            onVer={abrirDetalle}
            onEditar={abrirEditar}
          />
        )}

        {(vista === 'nuevo' || vista === 'editar') && (
          <div className="form-page">
            <h2>{vista === 'nuevo' ? 'Nuevo cliente' : `Editar: ${clienteActual?.nombre_comercial}`}</h2>
            {error && <div className="alert alert-error">{error}</div>}
            <ClienteForm
              inicial={vista === 'editar' ? clienteActual : null}
              onGuardar={vista === 'nuevo' ? guardarNuevo : guardarEdicion}
              onCancelar={irALista}
              cargando={cargando}
            />
          </div>
        )}

        {vista === 'detalle' && clienteActual && (
          <>
            {error && <div className="alert alert-error">{error}</div>}
            <ClienteDetalle
              cliente={clienteActual}
              onEditar={() => abrirEditar(clienteActual.id)}
              onVolver={irALista}
            />
          </>
        )}
      </main>
    </div>
  )
}
