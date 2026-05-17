import React, { useEffect, useRef } from 'react';
import { useTerminal } from '../contexts/TerminalContext';
import { ChevronDown, Terminal as TerminalIcon, Keyboard, FileText, AlertCircle, Loader2 } from 'lucide-react';

export default function OutputPanel({ onToggle, isCollapsed }) {
    const { 
        terminalRef, fitAddonRef, ready, 
        stdout, stderr, runInput, setRunInput, 
        executionTime, isRunning, activeTab, setActiveTab 
    } = useTerminal();

    const terminalContainerRef = useRef(null);

    useEffect(() => {
        if (!ready || activeTab !== 'terminal' || isCollapsed) return;
        
        const termContainer = terminalContainerRef.current;
        if (termContainer && terminalRef.current) {
            if (!terminalRef.current.element) {
                terminalRef.current.open(termContainer);
            } else if (terminalRef.current.element.parentElement !== termContainer) {
                termContainer.appendChild(terminalRef.current.element);
            }
            
            // Comprehensive fitting logic
            const resizeObserver = new ResizeObserver(() => {
                if (fitAddonRef.current && terminalRef.current?.element) {
                    try {
                        fitAddonRef.current.fit();
                    } catch (e) {
                        console.warn("Terminal fit failed", e);
                    }
                }
            });
            
            resizeObserver.observe(termContainer);
            
            setTimeout(() => {
                if (terminalRef.current) {
                    terminalRef.current.focus();
                }
            }, 50);

            return () => resizeObserver.disconnect();
        }
    }, [ready, terminalRef, fitAddonRef, isCollapsed, activeTab]);

    const renderContent = () => {
        if (isCollapsed) return null;

        return (
            <div className="content-area">
                {activeTab === 'terminal' && (
                    <div 
                        ref={terminalContainerRef}
                        id="terminal-container" 
                        className="h-full w-full" 
                    />
                )}

                {activeTab === 'input' && (
                    <div className="input-section">
                        <div className="input-header">STANDARD INPUT</div>
                        <textarea
                            className="input-textarea"
                            placeholder="Enter stdin for your program..."
                            value={runInput}
                            onChange={(e) => setRunInput(e.target.value)}
                        />
                    </div>
                )}

                {activeTab === 'stdout' && (
                    <div className="stdout-section" style={{position: 'relative'}}>
                        {isRunning && (
                            <div className="loading-overlay">
                                <Loader2 className="spinner" size={32} />
                                <span style={{marginTop: '12px', fontSize: '13px', fontWeight: '500'}}>Running...</span>
                            </div>
                        )}
                        {stdout || <span style={{opacity: 0.3, fontStyle: 'italic'}}>No output yet.</span>}
                        {executionTime !== null && (
                            <div className="execution-info">
                                Program finished in {executionTime}ms
                            </div>
                        )}
                    </div>
                )}

                {activeTab === 'stderr' && (
                    <div className="stderr-section">
                        {stderr || <span style={{opacity: 0.3, fontStyle: 'italic'}}>No errors.</span>}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="output-panel">
            <div className="tab-bar">
                <button 
                    onClick={() => setActiveTab('terminal')}
                    className={`tab-btn ${activeTab === 'terminal' ? 'active' : ''}`}
                >
                    <TerminalIcon size={14} />
                    TERMINAL
                </button>
                <button 
                    onClick={() => setActiveTab('input')}
                    className={`tab-btn ${activeTab === 'input' ? 'active' : ''}`}
                >
                    <Keyboard size={14} />
                    INPUT
                </button>
                <button 
                    onClick={() => setActiveTab('stdout')}
                    className={`tab-btn ${activeTab === 'stdout' ? 'active' : ''}`}
                >
                    <FileText size={14} />
                    STDOUT
                </button>
                <button 
                    onClick={() => setActiveTab('stderr')}
                    className={`tab-btn ${activeTab === 'stderr' ? 'active' : ''}`}
                >
                    <AlertCircle size={14} />
                    STDERR
                    {stderr && <div style={{width: '6px', height: '6px', background: 'var(--danger)', borderRadius: '50%', marginLeft: '4px'}} />}
                </button>
                
                <div style={{flex: 1}} />
                
                <button 
                  className="tab-btn"
                  style={{padding: '0 12px'}}
                  onClick={onToggle} 
                >
                    <ChevronDown 
                        size={16} 
                        style={{ transform: isCollapsed ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
                    />
                </button>
            </div>
            
            {renderContent()}
        </div>
    );
}
