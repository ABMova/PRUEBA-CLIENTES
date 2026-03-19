import { useState, useEffect } from 'react'

const CAMPOS = [
  { name: 'nombre_comercial', label: 'Nombre comercial *', required: true, col: 2 },
  { name: 'razon_social',     label: 'Razón social *',     required: true, col: 2 },
  { name: 'cif',              label: 'CIF *',               required: true, col: 1 },
  { name: 'email',            label: 'Email *',             required: true, col: 1, type: 'email' },
  { name: 'administrador',    label: 'Administrador',       required: false, col: 1 },
  { name: 'dni',              label: 'DNI',                 required: false, col: 1 },
  { name: 'direccion',        label: 'Dirección',           required: false, col: 2 },
  { name: 'codigo_postal',    label: 'Código postal',       required: false, col: 1 },
  { name: 'poblacion',        label: 'Población',           required: false, col: 1 },
  { name: 'provincia',        label: 'Provincia',           required: false, col: 1 },
  { name: 'telefono',         label: 'Teléfono',            required: false, col: 1 },
  { name: 'notas',            label: 'Notas',               required: false, col: 2, textarea: true },
]

const EMPTY = {
  nombre_comercial: '', razon_social: '', cif: '', email: '',
  administrador: '', dni: '', telefono: '',
  direccion: '', codigo_postal: '', poblacion: '', provincia: '',
  notas: '',
}

export default function ClienteForm({ inicial, onGuardar, onCancelar, cargando }) {
  const [form, setForm] = useState(EMPTY)
  const [errores, setErrores] = useState({})

  useEffect(() => {
    if (inicial) {
      setForm({
        nombre_comercial: inicial.nombre_comercial ?? '',
        razon_social:     inicial.razon_social ?? '',
        cif:              inicial.cif ?? '',
        email:            inicial.email ?? '',
        administrador:    inicial.administrador ?? '',
        dni:              inicial.dni ?? '',
        telefono:         inicial.telefono ?? '',
        direccion:        inicial.direccion ?? '',
        codigo_postal:    inicial.codigo_postal ?? '',
        poblacion:        inicial.poblacion ?? '',
        provincia:        inicial.provincia ?? '',
        notas:            inicial.notas ?? '',
      })
    }
  }, [inicial])

  function onChange(e) {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
    if (errores[name]) setErrores(e => ({ ...e, [name]: undefined }))
  }

  function validar() {
    const e = {}
    if (!form.nombre_comercial.trim()) e.nombre_comercial = 'Obligatorio'
    if (!form.razon_social.trim()) e.razon_social = 'Obligatorio'
    if (!form.cif.trim()) {
      e.cif = 'Obligatorio'
    } else if (!/^[A-HJNP-SUVW]\d{7}[0-9A-J]$/i.test(form.cif.trim())) {
      e.cif = 'CIF inválido (ej: B12345678)'
    }
    if (!form.email.trim()) {
      e.email = 'Obligatorio'
    } else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) {
      e.email = 'Email inválido'
    }
    if (form.codigo_postal && (!/^\d{5}$/.test(form.codigo_postal.trim()))) {
      e.codigo_postal = 'Debe tener 5 dígitos'
    }
    return e
  }

  function onSubmit(e) {
    e.preventDefault()
    const e2 = validar()
    if (Object.keys(e2).length) { setErrores(e2); return }

    const payload = {}
    for (const [k, v] of Object.entries(form)) {
      payload[k] = v.trim() || null
    }
    // required fields must not be null
    payload.nombre_comercial = form.nombre_comercial.trim()
    payload.razon_social = form.razon_social.trim()
    payload.cif = form.cif.trim().toUpperCase()
    payload.email = form.email.trim().toLowerCase()

    onGuardar(payload)
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <div className="form-grid">
        {CAMPOS.map(({ name, label, required, col, type, textarea }) => (
          <div key={name} className={`form-field col-${col}`}>
            <label htmlFor={name}>{label}</label>
            {textarea ? (
              <textarea
                id={name} name={name} value={form[name]}
                onChange={onChange} rows={3}
                className={errores[name] ? 'error' : ''}
              />
            ) : (
              <input
                id={name} name={name} type={type || 'text'}
                value={form[name]} onChange={onChange}
                required={required}
                className={errores[name] ? 'error' : ''}
              />
            )}
            {errores[name] && <span className="campo-error">{errores[name]}</span>}
          </div>
        ))}
      </div>

      <div className="form-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancelar} disabled={cargando}>
          Cancelar
        </button>
        <button type="submit" className="btn btn-primary" disabled={cargando}>
          {cargando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </form>
  )
}
