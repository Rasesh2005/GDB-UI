import React, { useEffect, useRef, useState } from 'react';
import { TerminalProvider, useTerminal } from './contexts/TerminalContext';
import { DebugProvider } from './contexts/DebugContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import AuthModal from './components/AuthModal';
import ControlPanel from './components/ControlPanel';
import EditorView from './components/EditorView';
import OutputPanel from './components/OutputPanel';
import DataPanels from './components/DataPanels';
import { Group, Panel, Separator } from 'react-resizable-panels';
import './index.css';

// A styled reusable resize handle
function ResizeHandle({ className = "" }) {
  return (
    <Separator className={`resize-handle ${className}`}>
      <div className="resize-handle-inner" />
    </Separator>
  );
}

function MainApp() {
  const { sessionId } = useTerminal();
  const { isAuthModalOpen, closeAuthModal, user } = useAuth();
  const sidebarRef = useRef(null);
  const terminalRef = useRef(null);
  
  // Explicit state to trigger re-renders for UI indicators (like icons)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isTerminalCollapsed, setIsTerminalCollapsed] = useState(false);

  // Toggle functions to be passed down
  const toggleSidebar = () => {
    const sidebar = sidebarRef.current;
    if (sidebar) {
      if (sidebar.isCollapsed()) {
        sidebar.expand();
        setIsSidebarCollapsed(false);
      } else {
        sidebar.collapse();
        setIsSidebarCollapsed(true);
      }
    }
  };

  const toggleTerminal = () => {
    const terminal = terminalRef.current;
    if (terminal) {
      if (terminal.isCollapsed()) {
        terminal.expand();
        setIsTerminalCollapsed(false);
      } else {
        terminal.collapse();
        setIsTerminalCollapsed(true);
      }
    }
  };

  useEffect(() => {
    const handleResize = () => {
      const isMobile = window.innerWidth < 768;
      if (sidebarRef.current) {
        if (isMobile) {
          sidebarRef.current.collapse();
          setIsSidebarCollapsed(true);
        } else {
          sidebarRef.current.expand();
          setIsSidebarCollapsed(false);
        }
      }
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <DebugProvider sessionId={sessionId}>
      <div className="app-container">
        <AuthModal isOpen={isAuthModalOpen} onClose={closeAuthModal} />
        <ControlPanel 
          user={user} 
          onToggleSidebar={toggleSidebar} 
          isSidebarCollapsed={isSidebarCollapsed} 
        />
        <div className="workspace-container">
          <Group orientation="horizontal" autoSaveId="main-layout">
            <Panel minSize={30} defaultSize={75}>
              <Group orientation="vertical" autoSaveId="editor-layout">
                <Panel minSize={30} defaultSize={60} className="editor-panel">
                  <EditorView />
                </Panel>
                <ResizeHandle />
                <Panel 
                  ref={terminalRef}
                  collapsible={true}
                  collapsedSize={5}
                  minSize={10} 
                  defaultSize={40} 
                  className="terminal-panel"
                  onCollapse={() => setIsTerminalCollapsed(true)}
                  onExpand={() => setIsTerminalCollapsed(false)}
                >
                  <OutputPanel 
                    onToggle={toggleTerminal} 
                    isCollapsed={isTerminalCollapsed} 
                  />
                </Panel>
              </Group>
            </Panel>
            <ResizeHandle />
            <Panel
              ref={sidebarRef}
              collapsible={true}
              collapsedSize={0}
              minSize={20}
              defaultSize={25}
              className="sidebar-panel"
              onCollapse={() => setIsSidebarCollapsed(true)}
              onExpand={() => setIsSidebarCollapsed(false)}
            >
              <DataPanels />
            </Panel>
          </Group>
        </div>
      </div>
    </DebugProvider>
  );
}

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Profile from './components/Profile';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={
            <TerminalProvider>
              <MainApp />
            </TerminalProvider>
          } />
          <Route path="/profile" element={<Profile />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
