import { app, shell, BrowserWindow, ipcMain, dialog } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { spawn } from 'child_process'
import fs from 'fs'

let mainWindow = null
let apiProcess = null

// ─── Start Python API backend ────────────────────────────────────────────────
function startApiServer() {
  const apiDir = is.dev
    ? join(__dirname, '../../api')
    : join(process.resourcesPath, 'api')

  const pythonExe = process.platform === 'win32' ? 'python' : 'python3'

  console.log('[GhostForge] Starting Python API at', apiDir)

  apiProcess = spawn(pythonExe, ['app.py'], {
    cwd: apiDir,
    stdio: ['ignore', 'pipe', 'pipe']
  })

  apiProcess.stdout.on('data', d => console.log('[API]', d.toString().trim()))
  apiProcess.stderr.on('data', d => console.error('[API]', d.toString().trim()))
  apiProcess.on('exit', code => console.log('[API] exited with code', code))
}

// ─── Create main window ───────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1100,
    minHeight: 700,
    frame: false,          // Custom titlebar
    backgroundColor: '#0a0a0f',
    titleBarStyle: 'hidden',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
    icon: join(__dirname, '../../resources/icons/icon.png'),
    show: false,
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// ─── IPC Handlers ─────────────────────────────────────────────────────────────

ipcMain.handle('window:minimize', () => mainWindow?.minimize())
ipcMain.handle('window:maximize', () => {
  if (mainWindow?.isMaximized()) mainWindow.unmaximize()
  else mainWindow?.maximize()
})
ipcMain.handle('window:close', () => mainWindow?.close())
ipcMain.handle('window:isMaximized', () => mainWindow?.isMaximized() ?? false)

ipcMain.handle('dialog:openFile', async (_, filters) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: filters || [
      { name: '3D Models', extensions: ['obj', 'glb', 'gltf', 'stl', 'ply', 'dae', 'fbx'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  })
  return result.canceled ? null : result.filePaths[0]
})

ipcMain.handle('dialog:saveFile', async (_, defaultName, filters) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath: defaultName,
    filters: filters || [
      { name: 'GLB', extensions: ['glb'] },
      { name: 'OBJ', extensions: ['obj'] }
    ]
  })
  return result.canceled ? null : result.filePath
})

ipcMain.handle('fs:readFile', async (_, filePath) => {
  return fs.readFileSync(filePath)
})

// ─── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  electronApp.setAppUserModelId('com.ghostforge.app')

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  startApiServer()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (apiProcess) apiProcess.kill()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  if (apiProcess) apiProcess.kill()
})
