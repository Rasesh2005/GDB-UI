/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { useTerminal } from './TerminalContext';

const DebugContext = createContext(null);

export function DebugProvider({ sessionId, children }) {
    const { terminalRef } = useTerminal();
    const [state, setState] = useState({
        threads: [],
        stack: [],
        locals: [],
        globals: [],
        registers: [],
        breakpoints: [],
        functions: [],
        memory_map: [],
        current_frame: null,
        status: "idle",
    });

    const [connected, setConnected] = useState(false);
    const [userBreakpoints, setUserBreakpoints] = useState([]);
    const wsRef = useRef(null);

    const toggleBreakpoint = (line) => {
        setUserBreakpoints(prev => 
            prev.includes(line) ? prev.filter(l => l !== line) : [...prev, line]
        );
    };

    useEffect(() => {
        if (!sessionId) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/dbg/${sessionId}`;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => setConnected(true);

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'state_update') {
                    // Backend is always the source of truth — always apply it.
                    setState((prev) => ({ ...prev, ...data.payload }));
                } else if (['console', 'target', 'log'].includes(data.type)) {
                    if (terminalRef?.current && typeof data.payload === 'string') {
                        terminalRef.current.write(data.payload.replace(/\n/g, '\r\n'));
                    }
                } else if (data.type === 'error') {
                    console.error('GDB Error:', data.payload);
                    if (terminalRef?.current) {
                        terminalRef.current.write(`\r\n\x1b[31m[Error] ${data.payload}\x1b[0m\r\n`);
                    }
                    // On any error, assume GDB is no longer running so buttons unlock.
                    setState((prev) => ({ ...prev, status: "idle" }));
                }
            } catch (e) {
                console.error('Failed to parse WS message:', e);
            }
        };

        ws.onclose = () => {
            setConnected(false);
            // Reset status on disconnect so buttons are never permanently locked.
            setState((prev) => ({ ...prev, status: "idle" }));
        };

        return () => ws.close();
    }, [sessionId]);

    const sendCommand = (cmd) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ command: cmd }));
        }
    };

    // Optimistic: mark status="running" immediately so the UI reflects the intent
    // without waiting for the *running async record to arrive from GDB.
    const _sendExec = (cmd) => {
        setState((prev) => ({ ...prev, status: "running" }));
        sendCommand(cmd);
    };

    const runGdb = () => {
        if (terminalRef?.current) {
            terminalRef.current.write('\r\n\x1b[33mCompiling and starting GDB...\x1b[0m\r\n');
        }
        // COMPILE_AND_RUN is async on the server; optimistically mark as compiling
        // only after it's confirmed — so we don't disable buttons during compile.
        setState((prev) => ({ ...prev, status: "compiling" }));
        
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ command: 'COMPILE_AND_RUN', breakpoints: userBreakpoints }));
        }
    };

    const stepInto    = () => _sendExec('-exec-step');
    const stepOver    = () => _sendExec('-exec-next');
    const continueExec = () => _sendExec('-exec-continue');
    const stepBack = () => _sendExec("-exec-next --reverse");
    const stepOnto      = () => _sendExec("-exec-step --reverse");
    const pauseExec   = () => sendCommand('-exec-interrupt');  // don't optimistically change state
    const stopExec    = () => {
        setState((prev) => ({ ...prev, status: "idle" }));
        sendCommand('STOP_EXECUTION');
    };

    return (
        <DebugContext.Provider value={{
            state,
            connected,
            userBreakpoints,
            toggleBreakpoint,
            sendCommand,
            runGdb,
            stepInto,
            stepOver,
            stepBack,
            stepOnto,
            continueExec,
            pauseExec,
            stopExec
        }}>
            {children}
        </DebugContext.Provider>
    );
}

export const useDebugger = () => useContext(DebugContext);
