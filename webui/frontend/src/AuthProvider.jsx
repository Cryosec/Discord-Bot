// src/AuthProvider.js
import React, { useState, useEffect, useCallback, useRef } from 'react';
import AuthContext from './AuthContext';
import { setUnauthorizedHandler } from './api';

const API_BASE_URL = '/api'; // Use relative path
const STATUS_POLL_INTERVAL_MS = 5 * 60 * 1000; // Re-check the session while logged in

export const AuthProvider = ({ children }) => {
  const [authState, setAuthState] = useState({
    isLoggedIn: false,
    user: null,
    isLoading: true, // Start loading
    error: null,
  });

  // Function to check authentication status with the backend
  // silent: background poll, no loading state and no logout on network errors
  const checkAuthStatus = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setAuthState((prev) => ({ ...prev, isLoading: true, error: null }));
    }
    try {
      const response = await fetch(`${API_BASE_URL}/auth/status`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
        // Include credentials (session cookie) in the request
        credentials: 'include',
      });

      // Check for network errors (fetch resolves even for 4xx/5xx)
      if (!response.ok && response.status !== 401 && response.status !== 403) {
          // Handle unexpected errors differently than auth failures
          console.error(`Auth status check failed with status: ${response.status}`);
          throw new Error(`Failed to check auth status (${response.status})`);
      }

      const data = await response.json();

      if (response.ok && data.is_logged_in) {
        setAuthState({
          isLoggedIn: true,
          user: data.user,
          isLoading: false,
          error: null,
        });
      } else {
        // Handle cases where response is OK but not logged in, or 401/403
        setAuthState({
          isLoggedIn: false,
          user: null,
          isLoading: false,
          error: null, // Don't treat 'not logged in' as an error state here
        });
      }
    } catch (error) {
      console.error('Error checking authentication status:', error);
      if (silent) {
        return; // Keep the current state: the next poll tries again
      }
      setAuthState({
        isLoggedIn: false,
        user: null,
        isLoading: false,
        error: error.message || 'Could not connect to server.', // Provide error feedback
      });
    }
  }, []);

  // Check auth status when the provider mounts
  useEffect(() => {
    checkAuthStatus();
  }, [checkAuthStatus]);

  // Poll the status while logged in: the backend re-checks the mod role, so an
  // idle dashboard logs out after a role removal
  useEffect(() => {
    if (!authState.isLoggedIn) {
      return undefined;
    }
    const intervalId = setInterval(() => {
      checkAuthStatus({ silent: true });
    }, STATUS_POLL_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, [authState.isLoggedIn, checkAuthStatus]);

  // Function to initiate the Discord login flow
  const login = () => {
    // Redirect the browser to the backend login endpoint
    // The backend will handle the redirect to Discord
    window.location.href = `${API_BASE_URL}/auth/discord/login`;
  };

  // Function to log the user out
  const logout = async () => {
    setAuthState((prev) => ({ ...prev, isLoading: true })); // Indicate loading
    try {
      const response = await fetch(`${API_BASE_URL}/auth/logout`, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
        },
        credentials: 'include',
      });

      if (!response.ok) {
          // Handle potential errors during logout API call
          console.error(`Logout failed with status: ${response.status}`);
          throw new Error('Logout failed');
      }

      // Clear frontend state regardless of minor backend issues if needed,
      // but ideally wait for backend confirmation.
      setAuthState({
        isLoggedIn: false,
        user: null,
        isLoading: false,
        error: null,
      });
       // Optionally redirect to login or home page after logout
       // window.location.href = '/'; // Or a dedicated logged-out page
    } catch (error) {
      console.error('Logout error:', error);
      // Keep user potentially logged in if backend fails, but show error?
      // Or force logout on frontend anyway? Forcing logout is safer.
       setAuthState({
        isLoggedIn: false, // Force logout on frontend even if API fails
        user: null,
        isLoading: false,
        error: 'Logout failed. Please clear cookies if issues persist.',
      });
    }
  };

  // apiFetch calls this on a 401 (through a ref: logout changes on every render)
  const logoutRef = useRef(logout);
  logoutRef.current = logout;
  useEffect(() => {
    setUnauthorizedHandler(() => logoutRef.current());
    return () => setUnauthorizedHandler(null);
  }, []);

  // Value provided by the context
  const contextValue = {
    authState,
    login,
    logout,
    checkAuthStatus // Expose checkAuthStatus if needed externally
  };

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
};