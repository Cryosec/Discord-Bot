import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ConfirmationModal from './ConfirmationModal';
import Pagination from './Pagination';
import InfractionDetailModal from './InfractionDetailModal';
import { useAuth } from './AuthContext';

const API_BASE_URL = '/api'; // Use relative path

function InfractionManagement() {

   const { logout } = useAuth();
  // State for raw infraction summary data
  const [infractions, setInfractions] = useState([]);
  // Loading and error states for the main list
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  // State for search term
  const [searchTerm, setSearchTerm] = useState('');

  // State for the "Add Infraction" modal/form
  const [showAddForm, setShowAddForm] = useState(false);
  const [addUserId, setAddUserId] = useState('');
  const [addTag, setAddTag] = useState('');
  const [addReason, setAddReason] = useState('');
  const [addInfractionType, setAddInfractionType] = useState('warning');

  // --- State for Details Modal ---
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [selectedUserInfractions, setSelectedUserInfractions] = useState(null); // Stores full details { summary + reasons }
  const [detailLoading, setDetailLoading] = useState(false); // Loading state for fetching details
  const [detailError, setDetailError] = useState(null);     // Error state for fetching details

  // --- Pagination State ---
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  // Fetch infraction summaries from API
  const fetchInfractions = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/infractions`, {
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
      setInfractions(data);
    } catch (e) {
      // Avoid logging out on general network errors unless it's an auth error
      if (!(e instanceof Error && (e.message.includes('401') || e.message.includes('403')))) {
           console.error("Failed to fetch Infraction entries:", e);
           setError(`Failed to load Infraction entries. (${e.message})`);
      }
    } finally {
      setIsLoading(false);
    }
  }, [logout]);

  // Fetch data on mount
  useEffect(() => {
    fetchInfractions();
  }, [fetchInfractions]);

  // Filter infractions based on search term
  const filteredInfractions = useMemo(() => {
    if (!searchTerm) return infractions;
    const lowerCaseSearchTerm = searchTerm.toLowerCase();
    return infractions.filter(inf =>
      inf.user_id.toLowerCase().includes(lowerCaseSearchTerm) ||
      (inf.tag && inf.tag.toLowerCase().includes(lowerCaseSearchTerm))
    );
  }, [infractions, searchTerm]);

  // Reset page to 1 when search term changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm]);

  // --- Pagination Logic ---
  const currentTableData = useMemo(() => {
    if (rowsPerPage === -1) return filteredInfractions;
    const firstPageIndex = (currentPage - 1) * rowsPerPage;
    const lastPageIndex = firstPageIndex + rowsPerPage;
    return filteredInfractions.slice(firstPageIndex, lastPageIndex);
  }, [filteredInfractions, currentPage, rowsPerPage]);

  const handlePageChange = (page) => setCurrentPage(page);

  const handleRowsPerPageChange = (number) => {
    setRowsPerPage(number);
    setCurrentPage(1);
  };
  // --- End Pagination Logic ---

  // Handle adding a new infraction
  const handleAddInfraction = async (e) => {
     e.preventDefault();
     if (!addUserId || !addTag || !addReason) {
         setError("User ID, Tag, and Reason are required."); return;
     }
     setError(null); setIsLoading(true);
     let endpoint = '';
     switch (addInfractionType) {
         case 'kick': endpoint = `${API_BASE_URL}/kicks`; break;
         case 'ban': endpoint = `${API_BASE_URL}/bans`; break;
         default: endpoint = `${API_BASE_URL}/warnings`; break;
     }
     try {
         const response = await fetch(endpoint, {
             method: 'POST', headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ user_id: addUserId, tag: addTag, reason: addReason }),
         });
         if (!response.ok) {
             const errorData = await response.json().catch(() => ({}));
             throw new Error(`HTTP error! status: ${response.status} - ${errorData.error || errorData.message || 'Failed to add'}`);
         }
         setAddUserId(''); setAddTag(''); setAddReason(''); setShowAddForm(false);
         fetchInfractions(); // Refresh list
     } catch (e) {
         console.error(`Failed to add ${addInfractionType}:`, e);
         setError(`Failed to add ${addInfractionType}: ${e.message}`);
     } finally { setIsLoading(false); }
 };

  // --- Details Modal Logic ---
  // Function to handle opening the details modal and fetching data
  const handleViewDetails = useCallback(async (userId) => {
    // Find the basic info from the current list to show immediately
    const basicInfo = infractions.find(inf => inf.user_id === userId);
    setSelectedUserInfractions(basicInfo || { user_id: userId }); // Set basic info or just ID

    setShowDetailModal(true); // Open the modal
    setDetailLoading(true);   // Set loading state for details
    setDetailError(null);     // Clear previous detail errors

    try {
        const response = await fetch(`${API_BASE_URL}/infractions/${userId}`);
        if (!response.ok) {
            if (response.status === 404) {
                 throw new Error(`No infraction details found for user ${userId}.`);
            }
            const errorData = await response.json().catch(() => ({}));
            throw new Error(`HTTP error! status: ${response.status} - ${errorData.error || errorData.message || 'Failed to fetch details'}`);
        }
        const detailedData = await response.json();
        // Ensure reasons array exists, even if empty
        if (!detailedData.reasons) {
            detailedData.reasons = [];
        }
        setSelectedUserInfractions(detailedData); // Update state with full details (summary + reasons)
    } catch (e) {
        console.error("Failed to fetch infraction details:", e);
        setDetailError(e.message);
        // Keep basic info in selectedUserInfractions if fetch fails
    } finally {
        setDetailLoading(false); // Turn off loading state for details
    }
  }, [infractions]); // Depends on infractions list to find basic info

  // Function to close the details modal
  const handleCloseDetailModal = () => {
      setShowDetailModal(false);
      setSelectedUserInfractions(null); // Clear selected user data
      setDetailLoading(false);
      setDetailError(null);
  };
  // --- End Details Modal Logic ---

  return (
    // Main container
    <div className="p-4 md:p-6 bg-white rounded-lg shadow border border-gray-200">
      {/* Title */}
      <h2 className="text-2xl font-semibold mb-4 text-gray-800">Infraction Management</h2>
      {/* Main Error Display */}
      {error && <div className="mb-4 p-3 bg-red-100 text-red-700 border border-red-300 rounded-md"><strong>Error:</strong> {error}</div>}

      {/* Controls Row: Search and Add Button */}
      <div className="mb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
         {/* Search Input */}
        <div className="relative flex-grow">
           <label htmlFor="infractionSearch" className="sr-only">Search Infractions</label>
           <input
             type="text" id="infractionSearch" placeholder="Search by User ID or Tag..."
             value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)}
             className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
           />
           <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
             <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-400" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" /></svg>
           </div>
        </div>
         {/* Add Infraction Button */}
         <button onClick={() => setShowAddForm(true)} className="px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 transition duration-150 shadow focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 whitespace-nowrap">
           + Add Infraction
         </button>
       </div>

       {/* Add Infraction Form (Modal) */}
       {showAddForm && (
          <div className="fixed inset-0 z-40 flex items-center justify-center bg-black bg-opacity-50 backdrop-blur-sm p-4">
             <form onSubmit={handleAddInfraction} className="mb-6 p-6 bg-white rounded-lg shadow-xl border border-gray-200 w-full max-w-lg relative">
                {/* Close Button */}
                <button type="button" onClick={() => setShowAddForm(false)} className="absolute top-3 right-3 text-gray-400 hover:text-gray-600 focus:outline-none">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
                <h3 className="text-xl font-semibold mb-4 text-gray-800">Add New Infraction</h3>
                <div className="space-y-4">
                    {/* User ID */}
                    <div>
                        <label htmlFor="infUserId" className="block text-sm font-medium text-gray-700 mb-1">User ID *</label>
                        <input type="text" id="infUserId" value={addUserId} onChange={(e) => setAddUserId(e.target.value)} placeholder="Discord User ID" className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500" required />
                    </div>
                    {/* Tag */}
                    <div>
                        <label htmlFor="infTag" className="block text-sm font-medium text-gray-700 mb-1">User Tag *</label>
                        <input type="text" id="infTag" value={addTag} onChange={(e) => setAddTag(e.target.value)} placeholder="username#1234" className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500" required />
                    </div>
                    {/* Reason */}
                     <div>
                        <label htmlFor="infReason" className="block text-sm font-medium text-gray-700 mb-1">Reason *</label>
                        <textarea id="infReason" value={addReason} onChange={(e) => setAddReason(e.target.value)} placeholder="Reason for the infraction" rows={3} className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500" required />
                    </div>
                    {/* Type */}
                    <div>
                         <label htmlFor="infractionType" className="block text-sm font-medium text-gray-700 mb-1">Infraction Type *</label>
                         <select id="infractionType" value={addInfractionType} onChange={(e) => setAddInfractionType(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white focus:outline-none focus:ring-blue-500 focus:border-blue-500">
                             <option value="warning">Warning</option> <option value="kick">Kick</option> <option value="ban">Ban</option>
                         </select>
                    </div>
                    {/* Actions */}
                    <div className="flex justify-end pt-2">
                        <button type="button" onClick={() => setShowAddForm(false)} className="mr-3 px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300 transition duration-150 focus:outline-none focus:ring-2 focus:ring-gray-400">Cancel</button>
                        <button type="submit" disabled={isLoading} className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition duration-150 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2">
                            {isLoading ? 'Adding...' : 'Add Infraction'}
                        </button>
                    </div>
                </div>
            </form>
          </div>
       )}

      {/* Main Loading Indicator */}
      {isLoading && <p className="text-center text-gray-600 my-4">Loading infraction summaries...</p>}
      {/* No Data / No Search Results Message */}
      {!isLoading && !error && filteredInfractions.length === 0 && (
        <p className="text-center text-gray-500 my-4">
          {searchTerm ? 'No infractions found matching your search.' : 'No infraction records found.'}
        </p>
      )}
      {/* Infractions Table */}
      {!isLoading && filteredInfractions.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User ID</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tag</th>
                <th scope="col" className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Warnings</th>
                <th scope="col" className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Kicks</th>
                <th scope="col" className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Bans</th>
                <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {/* Map over current page data */}
              {currentTableData.map((inf) => (
                <tr key={inf.user_id} className="hover:bg-gray-50 transition duration-150">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{inf.user_id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{inf.tag || 'N/A'}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-center text-gray-600">{inf.warnings}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-center text-gray-600">{inf.kicks}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-center text-gray-600">{inf.bans}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium space-x-2">
                    {/* Updated Details Button */}
                    <button
                       onClick={() => handleViewDetails(inf.user_id)} // Call the fetch/modal handler
                       className="text-indigo-600 hover:text-indigo-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1"
                       title="View Infraction Details"
                       disabled={detailLoading && selectedUserInfractions?.user_id === inf.user_id} // Disable if loading details for this specific user
                    >
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* Pagination Component */}
          <Pagination
            totalItems={filteredInfractions.length}
            itemsPerPage={rowsPerPage}
            currentPage={currentPage}
            onPageChange={handlePageChange}
            onItemsPerPageChange={handleRowsPerPageChange}
          />
        </div>
      )}

      {/* Render the Infraction Detail Modal */}
      <InfractionDetailModal
        isOpen={showDetailModal}
        onClose={handleCloseDetailModal}
        userData={selectedUserInfractions}
        isLoading={detailLoading}
        error={detailError}
      />

    </div>
  );
}

export default InfractionManagement;