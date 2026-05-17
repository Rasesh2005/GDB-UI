import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [authModalOpen, setAuthModalOpen] = useState(false);

    useEffect(() => {
        // Check if user is logged in
        fetch('/api/me')
            .then(res => {
                if (res.ok) return res.json();
                throw new Error("Not logged in");
            })
            .then(data => setUser(data))
            .catch(() => setUser(null))
            .finally(() => setLoading(false));
    }, []);

    const login = async (username, password) => {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (res.ok) {
            setUser({ username: data.username });
            setAuthModalOpen(false);
            // Ideally we'd want to reconnect the websocket, but reloading the page is cleaner for now.
            window.location.reload(); 
            return true;
        }
        throw new Error(data.detail || "Login failed");
    };

    const register = async (username, password) => {
        const res = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (res.ok) {
            return login(username, password); // Auto-login after register
        }
        throw new Error(data.detail || "Registration failed");
    };

    const logout = async () => {
        await fetch('/api/logout', { method: 'POST' });
        setUser(null);
        window.location.reload();
    };

    return (
        <AuthContext.Provider value={{
            user, loading, login, register, logout,
            isAuthModalOpen: authModalOpen,
            openAuthModal: () => setAuthModalOpen(true),
            closeAuthModal: () => setAuthModalOpen(false)
        }}>
            {children}
        </AuthContext.Provider>
    );
}

export const useAuth = () => useContext(AuthContext);
