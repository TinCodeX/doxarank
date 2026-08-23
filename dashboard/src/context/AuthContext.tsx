import React, { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import type { User, AuthResponse } from '../types/auth';
import { apiFetch, getStoredTokens, setStoredTokens, clearStoredTokens } from '../api/client';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, firstName?: string, lastName?: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUserProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchUserProfile = async () => {
    try {
      const data = await apiFetch<User>('/api/auth/me/');
      setUser(data);
    } catch {
      setUser(null);
      clearStoredTokens();
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const tokens = getStoredTokens();
    if (tokens?.access) {
      fetchUserProfile();
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = async (email: string, password: string) => {
    const res = await apiFetch<AuthResponse>('/api/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setStoredTokens(res.tokens);
    setUser(res.user);
  };

  const register = async (email: string, password: string, firstName?: string, lastName?: string) => {
    const res = await apiFetch<AuthResponse>('/api/auth/register/', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        first_name: firstName || '',
        last_name: lastName || '',
      }),
    });
    setStoredTokens(res.tokens);
    setUser(res.user);
  };

  const logout = async () => {
    const tokens = getStoredTokens();
    if (tokens?.refresh) {
      try {
        await apiFetch('/api/auth/logout/', {
          method: 'POST',
          body: JSON.stringify({ refresh: tokens.refresh }),
        });
      } catch (err) {
        console.error('Logout error on backend:', err);
      }
    }
    clearStoredTokens();
    setUser(null);
  };

  const refreshUserProfile = async () => {
    await fetchUserProfile();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        refreshUserProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
