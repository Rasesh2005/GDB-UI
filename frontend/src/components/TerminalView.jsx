import React, { useEffect } from 'react';
import { useTerminal } from '../contexts/TerminalContext';

export default function TerminalView({ onToggle, isCollapsed }) {
    const { terminalRef, fitAddonRef, ready } = useTerminal();

    useEffect(() => {
        if (!ready) return;
        const termContainer = document.getElementById('terminal-container');
        if (termContainer && terminalRef.current && !terminalRef.current._initialized) {
            terminalRef.current.open(termContainer);
            terminalRef.current._initialized = true;
            setTimeout(() => {
                if (fitAddonRef.current) fitAddonRef.current.fit();
            }, 100);
        }
        
        // Refit on expand/collapse
        setTimeout(() => {
            if (fitAddonRef.current) fitAddonRef.current.fit();
        }, 150);
    }, [ready, terminalRef, fitAddonRef, isCollapsed]);

    return (
        <div className="terminal-wrapper h-full flex flex-col bg-black overflow-hidden">
            <div className="panel-header border-b border-gray-700 bg-gray-900 z-10 flex justify-between items-center px-4 py-2">
                <span className="uppercase text-xs tracking-wider text-gray-400">TERMINAL</span>
                <button 
                  className="collapse-btn" 
                  onClick={onToggle} 
                  title={isCollapsed ? "Expand Terminal" : "Collapse Terminal"}
                >
                    <svg 
                      width="14" 
                      height="14" 
                      viewBox="0 0 24 24" 
                      fill="none" 
                      stroke="currentColor" 
                      strokeWidth="2" 
                      style={{ transform: isCollapsed ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
                    >
                        <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                </button>
            </div>
            <div 
              id="terminal-container" 
              className="flex-1 w-full h-full p-1 relative" 
              style={{ display: isCollapsed ? 'none' : 'block' }} 
            />
        </div>
    );
}
