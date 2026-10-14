// La interfaz no ve Node ni el disco. Solo se expone una marca para saber que va en escritorio
// y la orden de salir (cierra la ventana; el proceso principal hace el cierre ordenado del motor).
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('mova', { esEscritorio: true, salir: () => ipcRenderer.send('mova-salir') });
