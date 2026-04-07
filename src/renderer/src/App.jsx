import React, { useEffect } from 'react'
import TitleBar     from './components/TitleBar'
import Toolbar      from './components/Toolbar'
import LeftPanel    from './components/LeftPanel'
import Viewport     from './components/Viewport'
import RightPanel   from './components/RightPanel'
import ChatPanel    from './components/ChatPanel'
import StatusBar    from './components/StatusBar'
import SettingsModal from './components/SettingsModal'
import { useUIStore } from './store'

export default function App() {
  const { leftPanelOpen, rightPanelOpen, chatPanelOpen, settingsOpen } = useUIStore()

  return (
    <div className="flex flex-col h-full w-full overflow-hidden"
         style={{ background: 'var(--gf-bg-base)' }}>

      {/* Custom window titlebar */}
      <TitleBar />

      {/* Main toolbar */}
      <Toolbar />

      {/* Main workspace */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left panel: scene hierarchy + tools */}
        {leftPanelOpen && <LeftPanel />}

        {/* 3D Viewport — centre, fills remaining space */}
        <Viewport />

        {/* Right panel: properties + UV + texture */}
        {rightPanelOpen && <RightPanel />}

        {/* AI Chat panel */}
        {chatPanelOpen && <ChatPanel />}
      </div>

      {/* Status bar */}
      <StatusBar />

      {/* Settings modal overlay */}
      {settingsOpen && <SettingsModal />}
    </div>
  )
}
