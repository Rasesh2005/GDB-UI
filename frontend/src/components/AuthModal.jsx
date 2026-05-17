import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import './AuthModal.css'; // Optional: we can style this in index.css instead

export default function AuthModal({ isOpen, onClose }) {
  const { login, register } = useAuth();
  const [isLoginTabs, setIsLoginTabs] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isLoginTabs) {
        await login(username, password);
      } else {
        await register(username, password);
      }
      onClose();
    } catch (err) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-modal-overlay" onClick={onClose}>
      <div className="auth-modal" onClick={e => e.stopPropagation()}>
        <div className="auth-tabs">
          <button 
            className={isLoginTabs ? 'active' : ''} 
            onClick={() => setIsLoginTabs(true)}
          >
            Login
          </button>
          <button 
            className={!isLoginTabs ? 'active' : ''} 
            onClick={() => setIsLoginTabs(false)}
          >
            Register
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="auth-form">
          {error && <div className="auth-error">{error}</div>}
          
          <div className="form-group">
            <label>Username</label>
            <input 
              type="text" 
              required 
              value={username} 
              onChange={e => setUsername(e.target.value)}
              placeholder="Enter your username"
            />
          </div>
          
          <div className="form-group">
            <label>Password</label>
            <input 
              type="password" 
              required 
              value={password} 
              onChange={e => setPassword(e.target.value)}
              placeholder="Enter your password"
            />
          </div>
          
          <button type="submit" className="submit-btn" disabled={loading}>
            {loading ? 'Processing...' : (isLoginTabs ? 'Login' : 'Create Account')}
          </button>
        </form>
      </div>
    </div>
  );
}
