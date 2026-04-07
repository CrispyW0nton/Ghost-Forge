import { contextBridge, ipcRenderer } from 'electron'

// Expose safe APIs to renderer via window.ghostforge
contextBridge.exposeInMainWorld('ghostforge', {
  // Window controls
  window: {
    minimize:    () => ipcRenderer.invoke('window:minimize'),
    maximize:    () => ipcRenderer.invoke('window:maximize'),
    close:       () => ipcRenderer.invoke('window:close'),
    isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
  },
  // Native file dialogs
  dialog: {
    openFile: (filters) => ipcRenderer.invoke('dialog:openFile', filters),
    saveFile: (name, filters) => ipcRenderer.invoke('dialog:saveFile', name, filters),
  },
  // File system helpers
  fs: {
    readFile: (path) => ipcRenderer.invoke('fs:readFile', path),
  },
  // Platform info
  platform: process.platform,
})
