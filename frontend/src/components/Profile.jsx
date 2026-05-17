import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, Terminal, Code, Clock, Folder, LogOut, ArrowLeft, Pencil, Trash2, Check, X } from 'lucide-react';
import './Profile.css';

export default function Profile() {
    const { user, loading, logout } = useAuth();
    const navigate = useNavigate();
    const [projects, setProjects] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isCreating, setIsCreating] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');
    const [editingId, setEditingId] = useState(null);
    const [editName, setEditName] = useState('');
    const [error, setError] = useState('');

    useEffect(() => {
        if (!loading && !user) {
            navigate('/');
        }
    }, [user, loading, navigate]);

    useEffect(() => {
        if (user) {
            fetchProjects();
        }
    }, [user]);

    const fetchProjects = async () => {
        try {
            const res = await fetch('/api/projects');
            if (res.ok) {
                const data = await res.json();
                setProjects(data.projects);
            }
        } catch (err) {
            console.error(err);
        } finally {
            setIsLoading(false);
        }
    };

    const handleCreateProject = async (e) => {
        e.preventDefault();
        if (!newProjectName.trim()) return;
        
        setIsCreating(true);
        setError('');
        
        try {
            const res = await fetch('/api/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newProjectName })
            });
            const data = await res.json();
            
            if (res.ok) {
                setNewProjectName('');
                fetchProjects();
            } else {
                setError(data.detail || 'Failed to create project');
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setIsCreating(false);
        }
    };

    const handleUpdateProject = async (id) => {
        if (!editName.trim()) return;
        try {
            const res = await fetch(`/api/projects/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: editName })
            });
            if (res.ok) {
                setEditingId(null);
                fetchProjects();
            }
        } catch (err) {
            console.error(err);
        }
    };

    const handleDeleteProject = async (e, id, name) => {
        e.preventDefault();
        e.stopPropagation();
        if (!window.confirm(`Are you sure you want to delete project "${name}"? All files will be permanently lost.`)) return;
        
        try {
            const res = await fetch(`/api/projects/${id}`, {
                method: 'DELETE'
            });
            if (res.ok) {
                fetchProjects();
            }
        } catch (err) {
            console.error(err);
        }
    };

    const startEditing = (e, project) => {
        e.preventDefault();
        e.stopPropagation();
        setEditingId(project.id);
        setEditName(project.name);
    };

    const cancelEditing = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setEditingId(null);
    };

    if (loading || !user) return <div className="profile-loading">Loading...</div>;

    return (
        <div className="profile-container">
            <header className="profile-header">
                <div className="profile-header-left">
                    <Link to="/" className="btn icon-btn"><ArrowLeft size={18} /> Back to Editor</Link>
                    <h1>My Workspace</h1>
                </div>
                <div className="profile-user">
                    <span>{user.username}</span>
                    <button className="btn icon-btn logout-btn" onClick={logout}><LogOut size={16} /> Logout</button>
                </div>
            </header>

            <main className="profile-content">
                <div className="projects-section">
                    <div className="projects-header">
                        <h2>Projects</h2>
                        <span className="projects-count">{projects.length} Files</span>
                    </div>
                    
                    <div className="projects-grid">
                        <div className="project-card new-project-card">
                            <form onSubmit={handleCreateProject} className="new-project-form">
                                <Code size={32} className="accent-icon" />
                                <h3>Create New Project</h3>
                                <input 
                                    type="text" 
                                    placeholder="Project Name..." 
                                    value={newProjectName}
                                    onChange={(e) => setNewProjectName(e.target.value)}
                                    maxLength={40}
                                />
                                {error && <div className="error-text">{error}</div>}
                                <button type="submit" disabled={isCreating || !newProjectName.trim()} className="btn primary full-width">
                                    <Plus size={16} /> {isCreating ? 'Creating...' : 'Create Project'}
                                </button>
                            </form>
                        </div>
                        
                        {isLoading ? (
                            <div className="project-loading">Loading projects...</div>
                        ) : (
                            projects.map(project => (
                                <div key={project.id} className="project-card-wrapper">
                                    <a 
                                        href={`/?project_id=${project.id}`} 
                                        target="_blank" 
                                        rel="noopener noreferrer" 
                                        className={`project-card existing-project ${editingId === project.id ? 'is-editing' : ''}`}
                                        onClick={(e) => editingId === project.id && e.preventDefault()}
                                    >
                                        <div className="project-card-header">
                                            <Folder size={24} className="folder-icon" />
                                            <div className="project-actions">
                                                <button 
                                                    className="action-btn edit-btn" 
                                                    onClick={(e) => startEditing(e, project)}
                                                    title="Edit Name"
                                                >
                                                    <Pencil size={14} />
                                                </button>
                                                <button 
                                                    className="action-btn delete-btn" 
                                                    onClick={(e) => handleDeleteProject(e, project.id, project.name)}
                                                    title="Delete Project"
                                                >
                                                    <Trash2 size={14} />
                                                </button>
                                            </div>
                                        </div>

                                        {editingId === project.id ? (
                                            <div className="edit-mode-container" onClick={e => e.stopPropagation()}>
                                                <input 
                                                    type="text" 
                                                    value={editName}
                                                    onChange={e => setEditName(e.target.value)}
                                                    className="edit-input"
                                                    autoFocus
                                                />
                                                <div className="edit-actions">
                                                    <button className="btn icon-btn save-btn" onClick={() => handleUpdateProject(project.id)}>
                                                        <Check size={14} />
                                                    </button>
                                                    <button className="btn icon-btn cancel-btn" onClick={cancelEditing}>
                                                        <X size={14} />
                                                    </button>
                                                </div>
                                            </div>
                                        ) : (
                                            <>
                                                <h3>{project.name}</h3>
                                                <div className="project-meta">
                                                    <Clock size={14} />
                                                    <span>{new Date(project.created_at).toLocaleDateString()}</span>
                                                </div>
                                                <div className="project-hover-overlay">
                                                    <div className="btn primary"><Terminal size={14} /> Open in Editor</div>
                                                </div>
                                            </>
                                        )}
                                    </a>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
}
