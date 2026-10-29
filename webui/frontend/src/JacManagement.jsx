import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ConfirmationModal from './ConfirmationModal';
import { toBotDate } from './botDate';
import Pagination from './Pagination'; // Import the Pagination component
import { useAuth } from './AuthContext';


const API_BASE_URL = '/api'; // Use relative path

function JacManagement() {

  // Auth stuff
  const { logout } = useAuth();
  // State for raw data fetched from API
  const [jacEntries, setJacEntries] = useState([]);
  // Loading and error states
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  // State for the add form visibility and input fields
  const [showAddForm, setShowAddForm] = useState(false);
  const [newUserId, setNewUserId] = useState('');
  const [newLink, setNewLink] = useState('');
  // State for the confirmation modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [itemToDelete, setItemToDelete] = useState(null);

  // --- Search State ---
  const [searchTerm, setSearchTerm] = useState('');

  // --- Pagination State ---
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(10); // Default rows per page, -1 means 'All'

  // Fetch JAC entries from the API
  const fetchJacEntries = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/jac`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'include', // <<< ADD THIS
      });

      // Check for Auth errors specifically
      if (response.status === 401 || response.status === 403) {
          console.error('Authorization failed. Logging out.');
          setError('Your session expired or you lack permission. Please log in again.');
          logout(); // Trigger logout process
          return; // Stop further processing
      }

      if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      data.sort((a, b) => new Date(b.date) - new Date(a.date));
      setJacEntries(data);
    } catch (e) {
      // Avoid logging out on general network errors unless it's an auth error
      if (!(e instanceof Error && (e.message.includes('401') || e.message.includes('403')))) {
           console.error("Failed to fetch JAC entries:", e);
           setError(`Failed to load JAC entries. (${e.message})`);
      }
    } finally {
      setIsLoading(false);
    }
  }, [logout]);


  // Fetch data when the component mounts
  useEffect(() => {
    fetchJacEntries();
  }, [fetchJacEntries]); // fetchJacEntries is stable due to useCallback

  // --- Filtering Logic ---
  const filteredJacEntries = useMemo(() => {
    if (!searchTerm) {
      return jacEntries; // Return all if no search term
    }
    const lowerCaseSearchTerm = searchTerm.toLowerCase();
    // Filter only by user_id as there's no tag field
    return jacEntries.filter(entry =>
      entry.user_id.toLowerCase().includes(lowerCaseSearchTerm)
    );
  }, [jacEntries, searchTerm]);

  // Reset page to 1 when search term changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm]);
  // --- End Filtering Logic ---

  // --- Pagination Logic ---
  // Calculate the items to display on the current page based on filtered data
  const currentTableData = useMemo(() => {
    if (rowsPerPage === -1) { // Handle 'All' option
      return filteredJacEntries;
    }
    const firstPageIndex = (currentPage - 1) * rowsPerPage;
    const lastPageIndex = firstPageIndex + rowsPerPage;
    return filteredJacEntries.slice(firstPageIndex, lastPageIndex);
  }, [filteredJacEntries, currentPage, rowsPerPage]); // Depends on filtered data now

  // Handler for changing the current page
  const handlePageChange = (page) => {
    setCurrentPage(page);
  };

  // Handler for changing the number of rows per page
  const handleRowsPerPageChange = (number) => {
    setRowsPerPage(number);
    setCurrentPage(1); // Reset to page 1 when rows per page changes
  };
  // --- End Pagination Logic ---

  // Handler for submitting the add JAC form
  const handleAddJac = async (e) => {
    e.preventDefault();
    if (!newUserId || !newLink) { setError("User ID and Link are required."); return; }
    setError(null);
    setIsLoading(true); // Indicate loading state during API call
    // The bot parses jac.date in its own format: an ISO date blocks the user for good
    const currentDate = toBotDate(new Date());

    try {
      const response = await fetch(`${API_BASE_URL}/jac`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: newUserId, link: newLink, date: currentDate }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({})); // Try to parse error JSON
        throw new Error(`HTTP error! status: ${response.status} - ${errorData.error || errorData.message || 'Unknown error'}`);
      }
      setNewUserId(''); setNewLink(''); setShowAddForm(false); fetchJacEntries();
    } catch (e) {
      console.error("Failed to add JAC entry:", e);
      setError(`Failed to add JAC entry: ${e.message}`);
    } finally { setIsLoading(false); } // Ensure loading state is turned off
  };

  // Handler for clicking the delete button (opens modal)
  const handleDeleteClick = (userId) => { setItemToDelete(userId); setIsModalOpen(true); };
  // Handler for closing the confirmation modal
  const handleCloseModal = () => { setIsModalOpen(false); setItemToDelete(null); };

  // Handler for confirming the deletion in the modal
  const handleConfirmDelete = async () => {
    if (!itemToDelete) return; // Guard clause
    setIsLoading(true); setError(null); setIsModalOpen(false); // Set loading, clear error, close modal
    try {
      const response = await fetch(`${API_BASE_URL}/jac/${itemToDelete}`, { method: 'DELETE' });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`HTTP error! status: ${response.status} - ${errorData.error || errorData.message || 'Unknown error'}`);
      }
      fetchJacEntries(); // Refresh the data after successful deletion
    } catch (e) {
      console.error("Failed to delete JAC entry:", e);
      setError(`Failed to delete JAC entry for user ${itemToDelete}: ${e.message}`);
    } finally { setIsLoading(false); setItemToDelete(null); } // Clear loading and item to delete
  };

  // Helper function to format date strings
  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    try { return new Date(dateString).toLocaleString('it-IT'); }
    catch (e) { console.warn("Could not format date:", dateString, e); return dateString; }
  };

  return (
    // Main container
    <div className="p-4 md:p-6 bg-white rounded-lg shadow border border-gray-200">
      {/* Section Title */}
      <h2 className="text-2xl font-semibold mb-4 text-gray-800">JAC Management</h2>
      {/* Error Display Area */}
      {error && <div className="mb-4 p-3 bg-red-100 text-red-700 border border-red-300 rounded-md"><strong>Error:</strong> {error}</div>}

      {/* Controls Row: Add Button and Search Input */}
      <div className="mb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          {/* Button to toggle the add form */}
          <button onClick={() => setShowAddForm(!showAddForm)} className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition duration-150 shadow focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 whitespace-nowrap order-1 sm:order-none">
            {showAddForm ? 'Cancel' : '+ Add New JAC Entry'}
          </button>
          {/* Search Input */}
          <div className="relative flex-grow order-2 sm:order-none">
             <label htmlFor="jacSearch" className="sr-only">Search JAC Entries</label>
             <input
               type="text"
               id="jacSearch"
               placeholder="Search by User ID..."
               value={searchTerm}
               onChange={(e) => setSearchTerm(e.target.value)}
               className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
             />
             {/* Search Icon */}
             <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
               <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
               </svg>
             </div>
          </div>
       </div>


      {/* Add JAC Entry Form (conditionally rendered) */}
      {showAddForm && (
        <form onSubmit={handleAddJac} className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
          <h3 className="text-lg font-medium mb-3 text-gray-700">New JAC Entry</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
            <div>
              <label htmlFor="jacUserId" className="block text-sm font-medium text-gray-700 mb-1">User ID</label>
              <input type="text" id="jacUserId" value={newUserId} onChange={(e) => setNewUserId(e.target.value)} placeholder="Discord User ID" className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500" required />
            </div>
            <div>
              <label htmlFor="jacLink" className="block text-sm font-medium text-gray-700 mb-1">Link</label>
              <input type="url" id="jacLink" value={newLink} onChange={(e) => setNewLink(e.target.value)} placeholder="http://example.com/jac" className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500" required />
            </div>
            <div>
              <button type="submit" disabled={isLoading} className="w-full px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition duration-150 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2">
                {isLoading ? 'Adding...' : 'Add Entry'}
              </button>
            </div>
          </div>
        </form>
      )}
      {/* Loading Indicator */}
      {isLoading && <p className="text-center text-gray-600 my-4">Loading JAC entries...</p>}
      {/* No Data Message (updated for search) */}
      {!isLoading && !error && filteredJacEntries.length === 0 && (
        <p className="text-center text-gray-500 my-4">
            {searchTerm ? 'No JAC entries found matching your search.' : 'No JAC entries found.'}
        </p>
      )}
      {/* Table Display (only show if not loading and there's filtered data) */}
      {!isLoading && filteredJacEntries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User ID</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Link</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date Added</th>
                <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {/* Map over the data for the current page (filtered) */}
              {currentTableData.map((entry, index) => (
                <tr key={`${entry.user_id}-${entry.date}-${index}`} className="hover:bg-gray-50 transition duration-150">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{entry.user_id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 max-w-xs truncate">
                    <a href={entry.link} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 hover:underline" title={entry.link}>{entry.link}</a>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{formatDate(entry.date)}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button onClick={() => handleDeleteClick(entry.user_id)} disabled={isLoading} className="text-red-600 hover:text-red-800 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1">Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* --- Pagination Component (uses filtered data length) --- */}
          <Pagination
            totalItems={filteredJacEntries.length} // Use filtered length
            itemsPerPage={rowsPerPage}
            currentPage={currentPage}
            onPageChange={handlePageChange}
            onItemsPerPageChange={handleRowsPerPageChange}
          />
        </div>
      )}
      {/* Confirmation Modal for Deletion */}
      <ConfirmationModal isOpen={isModalOpen} onClose={handleCloseModal} onConfirm={handleConfirmDelete} title="Confirm Deletion">
        Are you sure you want to delete all JAC entries for user ID: <strong className="font-semibold">{itemToDelete}</strong>? This action cannot be undone.
      </ConfirmationModal>
    </div>
  );
}

export default JacManagement;