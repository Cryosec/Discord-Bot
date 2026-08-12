import React, { useState, useEffect, useCallback, useMemo } from 'react';
import Pagination from './Pagination';
import { useAuth } from './AuthContext';

const API_BASE_URL = '/api';

function NewUsersManagement() {
    const { logout } = useAuth();
    const [newUsers, setNewUsers] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);

    // --- Search State ---
    const [searchTerm, setSearchTerm] = useState('');

    // --- Pagination State ---
    const [currentPage, setCurrentPage] = useState(1);
    const [rowsPerPage, setRowsPerPage] = useState(10);

    // Fetch new users from the API
    const fetchNewUsers = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const response = await fetch(`${API_BASE_URL}/new-users`, {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                credentials: 'include',
            });

            if (response.status === 401 || response.status === 403) {
                console.error('Authorization failed. Logging out.');
                setError('Your session expired or you lack permission. Please log in again.');
                logout();
                return;
            }

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            setNewUsers(data);
        } catch (e) {
            if (!(e instanceof Error && (e.message.includes('401') || e.message.includes('403')))) {
                console.error("Failed to fetch new users:", e);
                setError(`Failed to load new users. (${e.message})`);
            }
        } finally {
            setIsLoading(false);
        }
    }, [logout]);

    useEffect(() => {
        fetchNewUsers();
    }, [fetchNewUsers]);

    // --- Filtering Logic ---
    const filteredNewUsers = useMemo(() => {
        if (!searchTerm) {
            return newUsers;
        }
        const lowerCaseSearchTerm = searchTerm.toLowerCase();
        return newUsers.filter(entry =>
            entry.user_id.toLowerCase().includes(lowerCaseSearchTerm)
        );
    }, [newUsers, searchTerm]);

    // Reset page to 1 when search term changes
    useEffect(() => {
        setCurrentPage(1);
    }, [searchTerm]);

    // --- Pagination Logic ---
    const currentTableData = useMemo(() => {
        if (rowsPerPage === -1) {
            return filteredNewUsers;
        }
        const firstPageIndex = (currentPage - 1) * rowsPerPage;
        const lastPageIndex = firstPageIndex + rowsPerPage;
        return filteredNewUsers.slice(firstPageIndex, lastPageIndex);
    }, [filteredNewUsers, currentPage, rowsPerPage]);

    const handlePageChange = (page) => {
        setCurrentPage(page);
    };

    const handleRowsPerPageChange = (number) => {
        setRowsPerPage(number);
        setCurrentPage(1);
    };

    return (
        <div className="p-4 md:p-6 bg-white rounded-lg shadow border border-gray-200">
            <h2 className="text-2xl font-semibold mb-4 text-gray-800">New Users Tracking</h2>
            <p className="text-gray-600 mb-4">
                Users being monitored for link spam. They are removed after sending a threshold of messages without links.
            </p>

            {error && <div className="mb-4 p-3 bg-red-100 text-red-700 border border-red-300 rounded-md"><strong>Error:</strong> {error}</div>}

            {/* Controls Row */}
            <div className="mb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                {/* Refresh Button */}
                <button
                    onClick={fetchNewUsers}
                    disabled={isLoading}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition duration-150 shadow focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 whitespace-nowrap disabled:opacity-50"
                >
                    {isLoading ? 'Refreshing...' : 'Refresh'}
                </button>
                {/* Search Input */}
                <div className="relative flex-grow">
                    <label htmlFor="newUserSearch" className="sr-only">Search New Users</label>
                    <input
                        type="text"
                        id="newUserSearch"
                        placeholder="Search by User ID..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                    />
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
                        </svg>
                    </div>
                </div>
            </div>

            {/* Loading Indicator */}
            {isLoading && <p className="text-center text-gray-600 my-4">Loading new users...</p>}

            {/* No Data Message */}
            {!isLoading && !error && filteredNewUsers.length === 0 && (
                <p className="text-center text-gray-500 my-4">
                    {searchTerm ? 'No new users found matching your search.' : 'No new users are currently being tracked.'}
                </p>
            )}

            {/* Table Display */}
            {!isLoading && filteredNewUsers.length > 0 && (
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User ID</th>
                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Message Count</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {currentTableData.map((entry) => (
                                <tr key={entry.user_id} className="hover:bg-gray-50 transition duration-150">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{entry.user_id}</td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{entry.msg_count}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <Pagination
                        totalItems={filteredNewUsers.length}
                        itemsPerPage={rowsPerPage}
                        currentPage={currentPage}
                        onPageChange={handlePageChange}
                        onItemsPerPageChange={handleRowsPerPageChange}
                    />
                </div>
            )}
        </div>
    );
}

export default NewUsersManagement;
