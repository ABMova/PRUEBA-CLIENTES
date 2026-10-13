// La interfaz no ve Node ni el disco. Solo se expone una marca para saber que va en escritorio.
const { contextBridge } = require('electron');
contextBridge.exposeInMainWorld('mova', { esEscritorio: true });
