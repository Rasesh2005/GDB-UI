import React, { useState, useEffect, useRef } from 'react';
import { useTerminal } from '../contexts/TerminalContext';
import { useDebugger } from '../contexts/DebugContext';
import Editor from '@monaco-editor/react';
import { Settings, Save, Sparkles, Languages } from 'lucide-react';
import { themes } from '../utils/monacoThemes';


export default function EditorView() {
    const { sessionId, code, setCode } = useTerminal();
    const { userBreakpoints = [], mainLineNumber, toggleBreakpoint = () => { }, state } = useDebugger() || {};
    const executionLineRef = useRef([]);
    const [isInitialLoad, setIsInitialLoad] = useState(true);
    const [saveStatus, setSaveStatus] = useState('Auto-saved');
    const [statusColor, setStatusColor] = useState('status-muted');
    const timerRef = useRef(null);
    const editorRef = useRef(null);
    const monacoRef = useRef(null);
    const decorationsRef = useRef([]);

    const [theme, setTheme] = useState('vs-dark');
    const [isSavingTheme, setIsSavingTheme] = useState(false);
    const [user, setUser] = useState(null);

    const toggleBreakpointRef = useRef(toggleBreakpoint);
    useEffect(() => {
        toggleBreakpointRef.current = toggleBreakpoint;
    }, [toggleBreakpoint]);

    const handleEditorDidMount = (editor, monaco) => {
        editorRef.current = editor;
        monacoRef.current = monaco;

        // Define custom themes
        Object.keys(themes).forEach(key => {
            monaco.editor.defineTheme(key, themes[key]);
        });

        editor.onMouseDown((e) => {
            if (e.target.type === monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN) {
                const lineNumber = e.target.position.lineNumber;
                if (toggleBreakpointRef.current) {
                    toggleBreakpointRef.current(lineNumber);
                }
            }
        });

        // Setup keyboard shortcuts
        // Option + Shift + F (Standard Mac VS Code)
        editor.addCommand(monaco.KeyMod.Alt | monaco.KeyMod.Shift | monaco.KeyCode.KeyF, () => {
            handleFormat();
        });
        
        // Command + Shift + F (Native-feeling Mac shortcut)
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyF, () => {
            handleFormat();
        });
    };

    // Fetch existing code and user info (including theme)
    useEffect(() => {
        if (!sessionId || !isInitialLoad) return;

        // Fetch user info to get the stored theme if they are authenticated
        fetch('/api/me')
            .then(res => res.json())
            .then(data => {
                if (data && data.theme) {
                    setTheme(data.theme);
                    setUser(data);
                }
            })
            .catch(() => {
                // If not logged in, user remains null and theme remains vs-dark
            });

        let retryCount = 0;
        const fetchCode = () => {
            fetch(`/api/code/${sessionId}`)
                .then(res => {
                    if (!res.ok && retryCount < 1) {
                        retryCount++;
                        setTimeout(fetchCode, 1000); 
                        return;
                    }
                    return res.json();
                })
                .then(data => {
                    if (data && data.code) {
                        setCode(data.code);
                    }
                    setIsInitialLoad(false); 
                })
                .catch(err => {
                    console.error("Failed to load existing code", err);
                    setIsInitialLoad(false);
                });
        };

        fetchCode();
    }, [sessionId, isInitialLoad]);

    useEffect(() => {
        if (!editorRef.current || !monacoRef.current) return;

        const newDecorations = userBreakpoints.map(line => ({
            range: new monacoRef.current.Range(line, 1, line, 1),
            options: {
                isWholeLine: false,
                glyphMarginClassName: 'breakpoint-glyph'
            }
        }));

        if (mainLineNumber && !userBreakpoints.includes(mainLineNumber)) {
            newDecorations.push({
                range: new monacoRef.current.Range(mainLineNumber, 1, mainLineNumber, 1),
                options: {
                    isWholeLine: false,
                    glyphMarginClassName: 'breakpoint-glyph unremovable'
                }
            });
        }

        decorationsRef.current = editorRef.current.deltaDecorations(decorationsRef.current, newDecorations);
    }, [userBreakpoints, mainLineNumber]);

    // Handle execution highlights (current line being debugged)
    useEffect(() => {
        if (!editorRef.current || !monacoRef.current) return;

        const currentLine = state?.current_frame?.line;
        const newDecorations = [];

        if (currentLine) {
            const line = parseInt(currentLine);
            newDecorations.push({
                range: new monacoRef.current.Range(line, 1, line, 1),
                options: {
                    isWholeLine: true,
                    className: 'execution-line-highlight',
                    glyphMarginClassName: 'execution-line-glyph',
                    marginClassName: 'execution-line-margin'
                }
            });
            
            // Reveal the line if it's not in view
            editorRef.current.revealLineInCenterIfOutsideViewport(line);
        }

        executionLineRef.current = editorRef.current.deltaDecorations(
            executionLineRef.current, 
            newDecorations
        );
    }, [state?.current_frame?.line]);

    useEffect(() => {
        if (!sessionId || isInitialLoad) return;

        setSaveStatus('Saving...');
        setStatusColor('status-white');

        if (timerRef.current) clearTimeout(timerRef.current);

        timerRef.current = setTimeout(() => {
            fetch(`/sync/${sessionId}`, {
                method: 'POST',
                body: code
            }).then(() => {
                setSaveStatus('Saved');
                setStatusColor('status-success');
                setTimeout(() => {
                    setSaveStatus('Auto-saved');
                    setStatusColor('status-muted');
                }, 2000);
            }).catch(err => {
                setSaveStatus('Save error');
                setStatusColor('status-danger');
            });
        }, 500);

        return () => clearTimeout(timerRef.current);
    }, [code, sessionId, isInitialLoad]);

    const handleThemeChange = (newTheme) => {
        setTheme(newTheme);
        if (user) {
            // Persist theme to database for authenticated users
            setIsSavingTheme(true);
            fetch('/api/user/theme', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ theme: newTheme })
            })
            .finally(() => setIsSavingTheme(false));
        }
    };

    const handleFormat = async () => {
        if (!editorRef.current || !sessionId) return;
        
        setSaveStatus('Formatting...');
        try {
            const currentCode = editorRef.current.getValue();
            const res = await fetch(`/api/format/${sessionId}`, {
                method: 'POST',
                body: currentCode
            });
            
            const data = await res.json();
            if (data.status === 'ok') {
                setCode(data.code);
                setSaveStatus('Formatted');
                setTimeout(() => setSaveStatus('Auto-saved'), 2000);
            } else {
                setSaveStatus('Format error');
            }
        } catch (err) {
            console.error("Formatting failed", err);
            setSaveStatus('Format error');
        }
    };

    return (
        <div className="editor-container">
            <div className="panel-header editor-header">
                <div className="header-left">
                    <Sparkles className="icon-sparkles" size={14} />
                    <span>main.cpp</span>
                    {user && <span className="user-indicator">/ {user.username}</span>}
                </div>
                <div className="header-right editor-controls">
                    <div id="save-status" className={statusColor}>{saveStatus}</div>
                    
                    <div className="theme-selector-container">
                        <select 
                            className="theme-selector" 
                            value={theme} 
                            onChange={(e) => handleThemeChange(e.target.value)}
                        >
                            <option value="vs-dark">VS Dark</option>
                            <option value="monokai">Monokai</option>
                            <option value="dracula">Dracula</option>
                            <option value="one-dark">One Dark</option>
                            <option value="github-light">GitHub Light</option>
                            <option value="nord">Nord</option>
                            <option value="solarized-dark">Solarized Dark</option>
                        </select>
                    </div>

                    <button className="btn-format" onClick={handleFormat} title="Format Code (Alt+Shift+F)">
                        <Languages size={14} />
                        Format
                    </button>
                </div>
            </div>
            <div className="monaco-wrapper">
                <Editor
                    height="100%"
                    language="cpp"
                    theme={theme}
                    value={code}
                    onChange={(value) => setCode(value || '')}
                    onMount={handleEditorDidMount}
                    options={{
                        fontSize: 14,
                        minimap: { enabled: false },
                        scrollBeyondLastLine: false,
                        automaticLayout: true,
                        readOnly: false,
                        lineNumbers: 'on',
                        glyphMargin: true,
                        padding: { top: 10, bottom: 10 }
                    }}
                />
            </div>
        </div>
    );
}
