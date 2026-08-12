// src/Login.js
import React, { useEffect, useState } from 'react';
import { useAuth } from './AuthContext'; // Import the custom hook

function Login() {
  const { login } = useAuth(); // Get the login function from context
  const [errorMsg, setErrorMsg] = useState('');

  // Check for error messages passed in URL query parameters from backend redirect
  useEffect(() => {
    const queryParams = new URLSearchParams(window.location.search);
    const error = queryParams.get('error');
    if (error) {
      switch (error) {
        case 'auth_failed':
          setErrorMsg('Authentication failed. Please try again.');
          break;
        case 'token_exchange_failed':
          setErrorMsg('Could not verify identity with Discord. Please try again.');
          break;
        case 'user_fetch_failed':
        case 'guild_fetch_failed':
          setErrorMsg('Could not fetch required information from Discord.');
          break;
        case 'not_in_guild':
          setErrorMsg('You are not a member of the required Discord server.');
          break;
        case 'unauthorized_role':
          setErrorMsg('You do not have the required moderator role in the Discord server.');
          break;
        case 'role_check_failed':
        case 'bot_permission_error':
           setErrorMsg('Could not verify your roles. Please contact an administrator.');
           break;
        default:
          setErrorMsg('An unknown login error occurred.');
          break;
      }
      // Optional: Clean the URL query parameters after reading them
      // window.history.replaceState(null, '', window.location.pathname);
    }
  }, []);

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md text-center max-w-sm w-full">
        <h1 className="text-2xl font-semibold mb-4 text-gray-800">Lord Franklin Admin Panel Access</h1>
        <p className="text-gray-600 mb-6">
          Please log in with your Discord account to continue. Access is restricted to authorized moderators.
        </p>
        {errorMsg && (
          <div className="mb-4 p-3 bg-red-100 text-red-700 border border-red-300 rounded-md text-sm">
            {errorMsg}
          </div>
        )}
        <button
          onClick={login} // Call the login function from context
          className="w-full px-4 py-2 bg-indigo-600 text-white font-semibold rounded-md hover:bg-indigo-700 transition duration-150 shadow focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 flex items-center justify-center space-x-2"
        >
          {/* Simple Discord Icon Placeholder - Replace with actual SVG/Icon if desired */}
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M20.317 4.3698a19.7913 19.7913 0 00-4.885-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4464.824-.6567 1.2944a18.1111 18.1111 0 00-7.6667 0 18.755 18.755 0 00-.6588-1.2944.0761.0761 0 00-.0785-.037A19.7151 19.7151 0 003.6861 4.3698a.0761.0761 0 00-.0371.0785C3.5828 6.1817 3.4886 7.9542 3.5191 9.6361a.0771.0771 0 00.0785.0785c.4223.0371.834.1313 1.237.2816a.0761.0761 0 00.0864-.0439c.1576-.2478.301-.5018.4343-.7617a.0751.0751 0 00-.0439-.1023 10.2436 10.2436 0 01-1.931-.5941 11.0019 11.0019 0 01-.4636-3.3114 20.5444 20.5444 0 014.0224-.6438 17.616 17.616 0 016.022 0 20.5444 20.5444 0 014.0224.6438 10.99 10.99 0 01-.4636 3.3114 10.2436 10.2436 0 01-1.931.5941.0751.0751 0 00-.0439.1023c.1333.2599.2767.5139.4343.7617a.0761.0761 0 00.0864.0439c.405-.1482.8167-.2445 1.237-.2816a.0771.0771 0 00.0785-.0785c.0305-1.6819-.0761-3.4544-.1428-5.1674a.0761.0761 0 00-.0371-.0785zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419s.9744-2.419 2.1569-2.419c1.1825 0 2.1569 1.0857 2.1569 2.419 0 1.3333-.9744 2.419-2.1569 2.419zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419s.9744-2.419 2.1569-2.419c1.1825 0 2.1569 1.0857 2.1569 2.419 0 1.3333-.9765 2.419-2.1569 2.419z" /></svg>
          <span>Login with Discord</span>
        </button>
      </div>
    </div>
  );
}

export default Login;