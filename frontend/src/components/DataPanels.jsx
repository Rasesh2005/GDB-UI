import React, { useState } from 'react';
import { useDebugger } from '../contexts/DebugContext';
import { 
    Layers, Variable, MapPin, Activity, 
    Cpu, ChevronRight 
} from 'lucide-react';

// Collapsible Panel Wrapper
function Panel({ title, icon: Icon, children }) {
    const [isOpen, setIsOpen] = useState(true);

    return (
        <div className="state-panel">
            <div className="state-header" onClick={() => setIsOpen(!isOpen)}>
                <ChevronRight 
                    size={14} 
                    style={{ 
                        transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)', 
                        transition: 'transform 0.2s' 
                    }} 
                />
                {Icon && <Icon size={14} style={{ color: 'var(--accent)' }} />}
                <span>{title}</span>
            </div>
            {isOpen && <div className="state-content">{children}</div>}
        </div>
    );
}

// Data Views
function ThreadsView({ threads }) {
    if (!threads || threads.length === 0) return <div className="empty-state">No active threads</div>;
    return (
        <table className="data-table">
            <thead><tr><th>ID</th><th>TARGET ID</th><th>STATE</th></tr></thead>
            <tbody>
                {threads.map((t) => (
                    <tr key={t.id}>
                        <td>{t.id}</td>
                        <td title={t['target-id']}>{t['target-id']}</td>
                        <td title={t.state}>{t.state}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function StackView({ stack }) {
    if (!stack || stack.length === 0) return <div className="empty-state">No stack frames</div>;
    return (
        <table className="data-table">
            <thead><tr><th>LVL</th><th>FUNCTION</th><th>FILE:LINE</th></tr></thead>
            <tbody>
                {stack.map((f, i) => {
                    const frame = f.frame || f;
                    return (
                        <tr key={i}>
                            <td>{frame.level || 0}</td>
                            <td title={frame.func}>{frame.func || '?'}</td>
                            <td title={`${frame.file}:${frame.line}`}>{frame.file || '?'}:{frame.line || '?'}</td>
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
}

function LocalsView({ locals }) {
    if (!locals || locals.length === 0) return <div className="empty-state">No local variables</div>;
    return (
        <table className="data-table two-col">
            <thead><tr><th>NAME</th><th>VALUE</th></tr></thead>
            <tbody>
                {locals.map((v, i) => (
                    <tr key={i}>
                        <td title={v.name}>{v.name}</td>
                        <td title={v.value}>{v.value || '?'}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function BreakpointsView({ breakpoints, userBreakpoints }) {
    if (!userBreakpoints || userBreakpoints.length === 0) return <div className="empty-state">No breakpoints</div>;
    
    return (
        <table className="data-table">
            <thead><tr><th>#</th><th>TYPE</th><th>WHERE</th></tr></thead>
            <tbody>
                {userBreakpoints.map((line, i) => {
                    let gdbBp = null;
                    if (breakpoints) {
                        gdbBp = breakpoints.find(b => parseInt((b.bkpt || b).line) === line);
                        if (gdbBp) gdbBp = gdbBp.bkpt || gdbBp;
                    }
                    const num = gdbBp ? gdbBp.number : (i + 1);
                    const func = `main.cpp:${line}`;
                    return (
                        <tr key={i}><td>{num}</td><td>breakpoint</td><td title={func}>{func}</td></tr>
                    );
                })}
            </tbody>
        </table>
    );
}

function RegistersView({ registers }) {
    if (!registers || registers.length === 0) return <div className="empty-state">No registers</div>;
    return (
        <table className="data-table two-col">
            <thead><tr><th>REG</th><th>VALUE</th></tr></thead>
            <tbody>
                {registers.map((r, i) => (
                    <tr key={i}>
                        <td>r{r.number}</td>
                        <td title={r.value}>{r.value}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

export default function DataPanels() {
    const { state, userBreakpoints, mainLineNumber } = useDebugger() || { state: {}, userBreakpoints: [] };
    
    const combinedBreakpoints = React.useMemo(() => {
        let all = [...(userBreakpoints || [])];
        if (mainLineNumber && !all.includes(mainLineNumber)) {
            all.push(mainLineNumber);
        }
        return all.sort((a, b) => a - b);
    }, [userBreakpoints, mainLineNumber]);

    return (
        <div className="sidebar">
            <Panel title="CALL STACK" icon={Layers}>
                <StackView stack={state.stack} />
            </Panel>
            <Panel title="LOCAL VARIABLES" icon={Variable}>
                <LocalsView locals={state.locals} />
            </Panel>
            <Panel title="BREAKPOINTS" icon={MapPin}>
                <BreakpointsView breakpoints={state.breakpoints} userBreakpoints={combinedBreakpoints} />
            </Panel>
            <Panel title="THREADS" icon={Activity}>
                <ThreadsView threads={state.threads} />
            </Panel>
            <Panel title="REGISTERS" icon={Cpu}>
                <RegistersView registers={state.registers} />
            </Panel>
        </div>
    );
}
