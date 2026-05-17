import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';

const TerminalContext = createContext(null);

export function TerminalProvider({ children }) {
    const [sessionId, setSessionId] = useState(null);
    const [connected, setConnected] = useState(false);
    const [ready, setReady] = useState(false);
    const [stdout, setStdout] = useState('');
    const [stderr, setStderr] = useState('');
    const [runInput, setRunInput] = useState('');
    const [code, setCode] = useState('#include <iostream>\n\nint main() {\n    std::cout << "Hello from Sandbox!\\n";\n    return 0;\n}\n');
    const [executionTime, setExecutionTime] = useState(null);
    const [isRunning, setIsRunning] = useState(false);
    const [activeTab, setActiveTab] = useState('terminal');

    const terminalRef = useRef(null);
    const wsRef = useRef(null);
    const fitAddonRef = useRef(null);

    useEffect(() => {
        const term = new Terminal({
            theme: { background: '#000', foreground: '#d4d4d4' },
            fontFamily: 'Consolas, monospace',
            fontSize: 13,
            cursorBlink: true,
        });

        const fitAddon = new FitAddon();
        term.loadAddon(fitAddon);
        terminalRef.current = term;
        fitAddonRef.current = fitAddon;
        setReady(true);

        term.writeln('\x1b[33mConnecting to sandbox backend...\x1b[0m');

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const urlParams = new URLSearchParams(window.location.search);
        const projectId = urlParams.get('project_id');
        const queryStr = projectId ? `?project_id=${projectId}` : '';
        const wsUrl = `${protocol}//${window.location.host}/ws/terminal${queryStr}`;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            term.writeln('\x1b[32m[+] Connection established. Waiting for container...\x1b[0m');
            setConnected(true);
        };

        ws.onmessage = (event) => {
            if (typeof event.data === 'string' && event.data.startsWith('SESSION_ID:')) {
                const sid = event.data.split(':')[1];
                term.writeln(`\x1b[32m[+] Connected to minimal Ubuntu sandbox (session: ${sid})\x1b[0m`);
                term.writeln('\x1b[36mHint: To compile and run, type: g++ -g main.cpp -o main && ./main\x1b[0m');
                setSessionId(sid);
            } else if (event.data instanceof Blob) {
                const reader = new FileReader();
                reader.onload = () => {
                    term.write(new Uint8Array(reader.result));
                };
                reader.readAsArrayBuffer(event.data);
            } else {
                term.write(event.data);
            }
        };

        ws.onclose = () => {
            setConnected(false);
            term.writeln('\r\n\x1b[31m[!] Terminal connection lost\x1b[0m');
        };

        term.onData((data) => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(data);
            }
        });

        const handleResize = () => fitAddon.fit();
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            if (wsRef.current) wsRef.current.close();
            if (terminalRef.current) terminalRef.current.dispose();
        };
    }, []);

    const runFull = async (code) => {
        if (!sessionId) return;
        setIsRunning(true);
        setActiveTab('stdout');
        setStdout('');
        setStderr('');
        setExecutionTime(null);

        try {
            const res = await fetch(`/api/run_full/${sessionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code, input: runInput })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                setStdout(data.stdout);
                setStderr(data.stderr);
                setExecutionTime(data.time_ms);
            } else {
                setStderr(data.stderr || 'An unknown error occurred during execution.');
            }
        } catch (err) {
            setStderr(`Failed to connect to backend: ${err.message}`);
        } finally {
            setIsRunning(false);
        }
    };

    return (
        <TerminalContext.Provider value={{ 
            sessionId, connected, ready, terminalRef, fitAddonRef,
            stdout, setStdout, stderr, setStderr, runInput, setRunInput,
            code, setCode,
            executionTime, isRunning, runFull, activeTab, setActiveTab
        }}>
            {children}
        </TerminalContext.Provider>
    );
}

export const useTerminal = () => useContext(TerminalContext);
