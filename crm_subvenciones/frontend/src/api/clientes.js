const BASE = '/clientes'

async function handleResponse(res) {
  if (res.status === 204) return null
  const data = await res.json()
  if (!res.ok) {
    const msg = data?.detail || 'Error en el servidor'
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export async function listarClientes({ q = '', activo } = {}) {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (activo !== undefined) params.set('activo', activo)
  const res = await fetch(`${BASE}?${params}`)
  return handleResponse(res)
}

export async function obtenerCliente(id) {
  const res = await fetch(`${BASE}/${id}`)
  return handleResponse(res)
}

export async function crearCliente(data) {
  const res = await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function actualizarCliente(id, data) {
  const res = await fetch(`${BASE}/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function eliminarCliente(id) {
  const res = await fetch(`${BASE}/${id}`, { method: 'DELETE' })
  return handleResponse(res)
}
