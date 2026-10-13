// Pantalla de arranque: si el proceso principal la recarga con ?error=..., enseña el fallo.
(function () {
  const q = new URLSearchParams(location.search);
  if (!q.get('error')) return;
  document.getElementById('error').textContent = q.get('error');
  document.getElementById('registro').textContent = q.get('registro') || '';
  document.body.classList.add('fallo');
})();
