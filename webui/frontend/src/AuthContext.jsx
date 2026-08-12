// src/AuthContext.js
import React, { createContext, useContext } from 'react';

// Define the initial shape of the context
const AuthContext = createContext({
  authState: {
    isLoggedIn: false,
    user: null, // Will store { id, username }
    isLoading: true, // Start in loading state until status is checked
    error: null, // To store any auth-related errors
  },
  login: () => {}, // Function to initiate login redirect
  logout: async () => {}, // Function to initiate logout
});

// Custom hook for easy context consumption
export const useAuth = () => {
  return useContext(AuthContext);
};

export default AuthContext;