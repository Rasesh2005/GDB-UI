import React, { useState, useEffect } from 'react';
import { useDebugger } from '../contexts/DebugContext';
import { useTerminal } from '../contexts/TerminalContext';
import { useAuth } from '../contexts/AuthContext';
import {
    Play, Bug, ChevronRight, CornerDownRight,
    RotateCcw, Octagon, LogOut, User,
    Menu, Pause, Square, FolderOpen
} from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

export default function ControlPanel({ onToggleSidebar }) {
    const { connected: termConnected, runFull, code, isRunning: isProgramRunning } = useTerminal();
    const { connected: dbgConnected, state, runGdb, stepInto, stepOver, stepBack, stepOnto, continueExec, pauseExec, stopExec } = useDebugger() || {};
    const { user, openAuthModal, logout } = useAuth();
    const location = useLocation();
    const [projectName, setProjectName] = useState('');

    const isRunning = state?.status === 'running' || state?.status === 'compiling';
    const isStopped = state?.status === 'stopped';

    useEffect(() => {
        const fetchProjectName = async () => {
            const params = new URLSearchParams(location.search);
            const projectId = params.get('project_id');
            if (user && projectId) {
                try {
                    const res = await fetch('/api/projects');
                    if (res.ok) {
                        const data = await res.json();
                        const project = data.projects.find(p => p.id.toString() === projectId);
                        if (project) setProjectName(project.name);
                    }
                } catch (err) {
                    console.error('Failed to fetch project name', err);
                }
            } else {
                setProjectName('');
            }
        };
        fetchProjectName();
    }, [user, location.search]);

    return (
        <div className="toolbar">
            <div className="toolbar-actions">
                <button className="hamburger-btn" onClick={onToggleSidebar} title="Toggle Sidebar">
                    <Menu size={20} />
                </button>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <button
                        className="btn run-btn"
                        onClick={() => runFull(code)}
                        disabled={!termConnected || isProgramRunning}
                    >
                        <Play size={12} fill="currentColor" />
                        Run
                    </button>

                    <div style={{ width: '1px', height: '18px', background: 'var(--border-color)', margin: '0 8px' }} />

                    <button className="btn" onClick={runGdb} disabled={!dbgConnected || isRunning}>
                        <Bug size={12} style={{ color: '#4ec9b0' }} />
                        Debug
                    </button>
                    <button className="btn" onClick={continueExec} disabled={!dbgConnected || !isStopped}>
                        <ChevronRight size={12} />
                        Continue
                    </button>
                    <button className="btn" onClick={stepInto} title="Step Into" disabled={!dbgConnected || !isStopped}>
                        <CornerDownRight size={12} />
                        Into
                    </button>
                    <button className="btn" onClick={stepOver} title="Step Over" disabled={!dbgConnected || !isStopped}>
                        <RotateCcw size={12} style={{ transform: 'scaleX(-1)' }} />
                        Over
                    </button>
                    <button className="btn" onClick={stepBack} title="Step Back (Reverse Next)" disabled={!dbgConnected || !isStopped}>
                        <RotateCcw size={12} />
                        Back
                    </button>
                    <button className="btn" onClick={stepOnto} title="Step Onto (Reverse Step)" disabled={!dbgConnected || !isStopped}>
                        <CornerDownRight size={12} style={{ transform: 'scaleY(-1) scaleX(-1)' }} />
                        Onto
                    </button>

                    {state?.status === 'running' ? (
                        <button className="btn danger" onClick={pauseExec}>
                            <Pause size={12} />
                            Pause
                        </button>
                    ) : (isRunning || isStopped) && (
                        <button className="btn danger" onClick={stopExec}>
                            <Square size={12} fill="currentColor" />
                            Stop
                        </button>
                    )}
                </div>
            </div>

            <div className="toolbar-status">
                {user ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {projectName && (
                            <div className="project-display">
                                <FolderOpen size={14} style={{ color: '#4ec9b0', opacity: 0.8 }} />
                                <span className="project-name">{projectName}</span>
                            </div>
                        )}
                        <Link to="/profile" className="btn primary" style={{ textDecoration: 'none', padding: '4px 12px' }}>Projects</Link>
                        <div className="status-item">
                            <User size={12} style={{ color: 'var(--accent)' }} />
                            <span className="status-label" style={{ color: '#fff', fontWeight: '500' }}>{user.username}</span>
                        </div>
                        <button className="btn" style={{ padding: '2px 8px' }} onClick={logout} title="Logout">
                            <LogOut size={12} />
                        </button>
                    </div>
                ) : (
                    <button className="btn primary login-btn" onClick={openAuthModal}>Login / Register</button>
                )}

                <div style={{ width: '1px', height: '18px', background: 'var(--border-color)', margin: '0 4px' }} />

                <div className="status-item" title={termConnected ? 'Terminal Connected' : 'Terminal Offline'}>
                    <span className="status-label">TERM</span>
                    <div className={`status-badge ${termConnected ? 'connected' : 'offline'}`}>
                        {termConnected ? 'ON' : 'OFF'}
                    </div>
                </div>

                <div className="status-item" title={dbgConnected ? `Debugger: ${state?.status}` : 'Debugger Disconnected'}>
                    <span className="status-label">DBG</span>
                    <div className={`status-badge ${dbgConnected ? (state?.status === 'idle' ? 'offline' : 'connected') : 'offline'}`}>
                        {dbgConnected ? (state?.status === 'idle' ? 'IDLE' : state?.status.toUpperCase()) : 'DISC'}
                    </div>
                </div>
            </div>
        </div>
    );
}
