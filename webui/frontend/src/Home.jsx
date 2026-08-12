// ========================================================================
// NEW COMPONENT: Home.js
// Landing page displaying stats and user search
// ========================================================================
import React, { useState, useEffect, useCallback } from 'react';

const API_BASE_URL = '/api'; // Use relative path

// Simple Card component for displaying stats
function StatCard({ title, value, isLoading, icon }) {
    return (
        <div className="bg-white p-4 rounded-lg shadow border border-gray-200 flex items-center space-x-3">
            {icon && <div className="text-blue-500">{icon}</div>}
            <div>
                <dt className="text-sm font-medium text-gray-500 truncate">{title}</dt>
                <dd className="mt-1 text-2xl font-semibold text-gray-900">
                    {isLoading ? (
                        <span className="animate-pulse bg-gray-300 rounded col-span-2 inline-block h-6 w-16"></span>
                    ) : (
                        value ?? 'N/A' // Handle null/undefined values
                    )}
                </dd>
            </div>
        </div>
    );
}

// Component for displaying user search results
function SearchResultDisplay({ resultData, isLoading, error }) {
    if (isLoading) {
        return <p className="text-sm text-gray-600 animate-pulse">Searching...</p>;
    }
    if (error) {
        return <p className="text-sm text-red-600">Error: {error}</p>;
    }
    if (!resultData) {
        return <p className="text-sm text-gray-500 italic">Enter a User ID and click Search.</p>;
    }

    const { userId, data, timestamp } = resultData; // Use timestamp as key if needed

    // Check if any record exists
    const userFound = data.has_jac || data.has_active_timer || data.has_infractions;

    return (
        <div key={timestamp} className="mt-4 p-4 border rounded-md bg-gray-50 text-sm">
            <h4 className="font-semibold text-gray-800 mb-2">Results for User ID: {userId}</h4>
            {userFound ? (
                <ul className="space-y-1">
                    <li>
                        <span className={`font-medium ${data.has_jac ? 'text-green-600' : 'text-gray-500'}`}>
                            {data.has_jac ? '● Found' : '○ Not Found'}
                        </span> in JAC Entries
                    </li>
                    <li>
                        <span className={`font-medium ${data.has_active_timer ? 'text-orange-600' : 'text-gray-500'}`}>
                            {data.has_active_timer ? '● Found' : '○ Not Found'}
                        </span> in Active Timers (Mute/Ban)
                    </li>
                    <li>
                        <span className={`font-medium ${data.has_infractions ? 'text-red-600' : 'text-gray-500'}`}>
                            {data.has_infractions ? '● Found' : '○ Not Found'}
                        </span> in Infractions
                    </li>
                </ul>
            ) : (
                <p className="text-gray-600">No records found for this User ID.</p>
            )}
        </div>
    );
}


function Home() {
    // State for summary statistics
    const [stats, setStats] = useState({
        jac_count: null,
        active_mutes: null,
        active_bans: null,
        total_warnings: null,
        total_kicks: null,
        total_bans_recorded: null,
    });
    const [statsLoading, setStatsLoading] = useState(true);
    const [statsError, setStatsError] = useState(null);

    // State for user search
    const [searchUserId, setSearchUserId] = useState('');
    const [searchResult, setSearchResult] = useState(null); // Stores { userId, data, timestamp }
    const [searchLoading, setSearchLoading] = useState(false);
    const [searchError, setSearchError] = useState(null);

    // Fetch summary statistics on component mount
    const fetchStats = useCallback(async () => {
        setStatsLoading(true);
        setStatsError(null);
        try {
            const response = await fetch(`${API_BASE_URL}/stats/summary`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            setStats(data);
        } catch (e) {
            console.error("Failed to fetch summary stats:", e);
            setStatsError(`Failed to load statistics. ${e.message}`);
        } finally {
            setStatsLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStats();
    }, [fetchStats]);

    // Handle user search form submission
    const handleSearchSubmit = async (event) => {
        event.preventDefault();
        if (!searchUserId.trim()) {
            setSearchError("Please enter a User ID.");
            return;
        }
        setSearchLoading(true);
        setSearchError(null);
        setSearchResult(null); // Clear previous results

        try {
            const response = await fetch(`${API_BASE_URL}/search/user/${searchUserId.trim()}`);
            if (!response.ok) {
                 if (response.status === 400) { // Handle specific backend validation error
                     const errorData = await response.json().catch(() => ({}));
                     throw new Error(errorData.error || 'Invalid request.');
                 }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            // Add timestamp to ensure state update even if data is identical
            setSearchResult({ userId: searchUserId.trim(), data: data, timestamp: Date.now() });
        } catch (e) {
            console.error("Failed to search user:", e);
            setSearchError(`Search failed. ${e.message}`);
        } finally {
            setSearchLoading(false);
        }
    };

    // Example Icons (using simple text/emoji, replace with SVG if desired)
    const icons = {
        jac: '📄', // Document
        mute: '🔇', // Muted speaker
        ban: '🚫', // Prohibition sign
        warning: '⚠️', // Warning sign
        kick: '👢', // Boot (representing kick)
        banRecord: '⚖️', // Scales (representing ban record)
        search: '🔍' // Magnifying glass
    };


    return (
        <div className="space-y-6">
            <h2 className="text-2xl font-semibold text-gray-800">Dashboard</h2>

            {/* Statistics Section */}
            <div>
                <h3 className="text-lg font-medium text-gray-700 mb-3">Database Summary</h3>
                {statsError && <div className="mb-4 p-3 bg-red-100 text-red-700 border border-red-300 rounded-md"><strong>Error:</strong> {statsError}</div>}
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
                    <StatCard title="Total JAC Entries" value={stats.jac_count} isLoading={statsLoading} icon={icons.jac} />
                    <StatCard title="Active Mutes" value={stats.active_mutes} isLoading={statsLoading} icon={icons.mute} />
                    <StatCard title="Active Bans" value={stats.active_bans} isLoading={statsLoading} icon={icons.ban} />
                    <StatCard title="Total Warnings Recorded" value={stats.total_warnings} isLoading={statsLoading} icon={icons.warning} />
                    <StatCard title="Total Kicks Recorded" value={stats.total_kicks} isLoading={statsLoading} icon={icons.kick} />
                    <StatCard title="Total Bans Recorded" value={stats.total_bans_recorded} isLoading={statsLoading} icon={icons.banRecord} />
                </div>
            </div>

            {/* User Search Section */}
            <div className="bg-white p-4 rounded-lg shadow border border-gray-200">
                <h3 className="text-lg font-medium text-gray-700 mb-3">Quick User Search</h3>
                <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
                    <label htmlFor="userIdSearch" className="sr-only">User ID</label>
                    <input
                        type="text"
                        id="userIdSearch"
                        value={searchUserId}
                        onChange={(e) => setSearchUserId(e.target.value)}
                        placeholder="Enter Discord User ID"
                        className="flex-grow w-full sm:w-auto px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                        required
                    />
                    <button
                        type="submit"
                        disabled={searchLoading}
                        className="w-full sm:w-auto px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition duration-150 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 flex items-center justify-center space-x-2"
                    >
                        {icons.search}
                        <span>{searchLoading ? 'Searching...' : 'Search'}</span>
                    </button>
                </form>
                {/* Display Search Results */}
                <SearchResultDisplay
                    resultData={searchResult}
                    isLoading={searchLoading}
                    error={searchError}
                />
            </div>
        </div>
    );
}

export default Home;