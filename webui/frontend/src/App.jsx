// src/App.js
/* eslint-disable react/prop-types */
import React, { useState } from 'react';

// Import Auth components
import { AuthProvider } from './AuthProvider';
import { useAuth } from './AuthContext';
import Login from './Login'; // Import the Login component

// Import Page components
import Home from './Home';
import JacManagement from './JacManagement';
import TimerManagement from './TimerManagement';
import InfractionManagement from './InfractionManagement';
import NewUsersManagement from './NewUsersManagement';

// Define tab constants
const TABS = {
  HOME: 'Home',
  JAC: 'JAC',
  TIMERS: 'Timers',
  INFRACTIONS: 'Infractions',
  NEW_USERS: 'New Users',
};

// Main application component structure
function MainApp() {
  const { authState, logout } = useAuth(); // Get auth state and logout function
  const [activeTab, setActiveTab] = useState(TABS.HOME); // Default to HOME tab

  // Function to render the component based on the active tab
  const renderActiveTabContent = () => {
    switch (activeTab) {
      case TABS.JAC:
        return <JacManagement />;
      case TABS.TIMERS:
        return <TimerManagement />;
      case TABS.INFRACTIONS:
        return <InfractionManagement />;
      case TABS.NEW_USERS:
        return <NewUsersManagement />;
      case TABS.HOME:
      default:
        return <Home />;
    }
  };

  // Helper function for tab button styling
  const getTabClassName = (tabName) => {
    return `px-3 py-1 md:px-4 md:py-2 font-medium text-sm rounded-md transition duration-150 focus:outline-none ${activeTab === tabName
        ? 'bg-blue-600 text-white shadow' // Active tab style
        : 'text-gray-300 hover:bg-gray-700 hover:text-white' // Inactive tab style
      }`;
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-gray-800 text-white shadow-md sticky top-0 z-10">
        <nav className="container mx-auto px-4 py-3 flex flex-col sm:flex-row justify-between items-center gap-3 sm:gap-4">
          {/* Title */}
          <h1 className="text-lg sm:text-xl font-bold whitespace-nowrap">Admin Panel</h1>
          {/* Tab Navigation */}
          <div className="flex space-x-1 sm:space-x-2 flex-wrap justify-center">
            {Object.values(TABS).map((tabName) => (
              <button
                key={tabName}
                onClick={() => setActiveTab(tabName)}
                className={getTabClassName(tabName)}
              >
                {tabName === TABS.JAC ? 'JAC Entries' : tabName}
              </button>
            ))}
          </div>
          {/* User Info & Logout */}
          <div className="text-sm text-gray-300 flex items-center space-x-3 whitespace-nowrap">
            <span>{authState.user?.username || 'User'}</span>
            <button
              onClick={logout}
              className="px-3 py-1 bg-red-600 text-white text-xs font-medium rounded hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 focus:ring-offset-gray-800"
            >
              Logout
            </button>
          </div>
        </nav>
      </header>
      {/* Main Content Area */}
      <main className="container mx-auto px-4 py-6">
        {renderActiveTabContent()}
      </main>
      {/* Footer */}
      <footer className="text-center py-4 text-gray-500 text-sm mt-8">
        Admin Panel for OperatorDrewski's Lord Franklin Discord Bot
      </footer>
    </div>
  );
}


// Root component that decides whether to show Login or MainApp
function App() {
  // Use a temporary component to access context easily
  const AuthChecker = () => {
    const { authState } = useAuth();

    if (authState.isLoading) {
      // Optional: More sophisticated loading spinner
      return (
        <div className="flex items-center justify-center min-h-screen bg-gray-100">
          <p className="text-gray-600">Checking authentication...</p>
        </div>
      );
    }

    if (!authState.isLoggedIn) {
      return <Login />;
    }

    // If logged in, render the main application
    return <MainApp />;
  };

  return (
    // Provide the AuthContext to the entire application
    <AuthProvider>
      <AuthChecker />
    </AuthProvider>
  );
}


export default App;