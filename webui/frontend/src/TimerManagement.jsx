// ========================================================================
// Timer Management Component - discord-bot-v4/webui/frontend/src/TimerManagement.js
// ========================================================================
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ConfirmationModal from './ConfirmationModal';
import { toBotDate } from './botDate';
import Pagination from './Pagination';
import { useAuth } from './AuthContext';
import { apiFetch } from './api';

const API_BASE_URL = '/api'; // Use relative path

function TimerManagement() {

   const { logout } = useAuth();
  // State for raw timer data
  const [timers, setTimers] = useState([]);
  // Loading and error states
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  // State for add form visibility and fields
  const [showAddForm, setShowAddForm] = useState(false);
  const [addType, setAddType] = useState('mute'); // 'mute' or 'ban'
  const [newUserId, setNewUserId] = useState('');
  const [durationValue, setDurationValue] = useState(1);
  const [durationUnit, setDurationUnit] = useState('hours'); // 'minutes', 'hours', 'days'
  // State for confirmation modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [itemToDelete, setItemToDelete] = useState(null); // Store user_id to delete

  // --- Pagination State ---
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(10); // Default rows per page, -1 means 'All'

  // Fetch active timers from the API
  const fetchTimers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/timers`, {
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
      setTimers(data);
    } catch (e) {
      // Avoid logging out on general network errors unless it's an auth error
      if (!(e instanceof Error && (e.message.includes('401') || e.message.includes('403')))) {
           console.error("Failed to fetch timers:", e);
           setError(`Failed to load timers. (${e.message})`);
      }
    } finally {
      setIsLoading(false);
    }
  }, [logout]);

  // Fetch timers on component mount
  useEffect(() => {
    fetchTimers();
  }, [fetchTimers]);

  // --- Pagination Logic ---
  const currentTableData = useMemo(() => {
     if (rowsPerPage === -1) { // Handle 'All' option
       return timers;
     }
    const firstPageIndex = (currentPage - 1) * rowsPerPage;
    const lastPageIndex = firstPageIndex + rowsPerPage;
    return timers.slice(firstPageIndex, lastPageIndex);
  }, [timers, currentPage, rowsPerPage]);

  const handlePageChange = (page) => {
    setCurrentPage(page);
  };

  const handleRowsPerPageChange = (number) => {
    setRowsPerPage(number);
    setCurrentPage(1); // Reset page
  };
  // --- End Pagination Logic ---

  // Calculate end date based on duration input for the add form, in the
  // bot's date format (see botDate.js).
  const calculateEndDate = () => {
    const target = new Date();
    const value = parseInt(durationValue, 10);
    if (isNaN(value) || value <= 0) return null; // Basic validation

    switch (durationUnit) {
      case 'minutes':
        target.setMinutes(target.getMinutes() + value);
        break;
      case 'hours':
        target.setHours(target.getHours() + value);
        break;
      case 'days':
        target.setDate(target.getDate() + value);
        break;
      default:
        return null; // Should not happen with select dropdown
    }

    return toBotDate(target);
  };

  // Handler for submitting the add timer form
  const handleAddTimer = async (e) => {
    e.preventDefault();
    if (!newUserId) { setError("User ID is required."); return; }
    const endDate = calculateEndDate();
    if (!endDate) { setError("Invalid duration value."); return; }

    setError(null);
    setIsLoading(true);

    // Determine API endpoint and payload based on selected timer type
    const endpoint = addType === 'mute' ? `${API_BASE_URL}/timers/mute` : `${API_BASE_URL}/timers/ban`;
    const payload = addType === 'mute' ? { user_id: newUserId, endMute: endDate } : { user_id: newUserId, endBan: endDate };

    try {
      const response = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`HTTP error! status: ${response.status} - ${errorData.error || errorData.message || 'Unknown error'}`);
      }
      // Reset form, hide it, and refresh timer list
      setNewUserId(''); setDurationValue(1); setDurationUnit('hours'); setShowAddForm(false); fetchTimers();
    } catch (e) {
      console.error(`Failed to add ${addType} timer:`, e);
      setError(`Failed to add ${addType} timer: ${e.message}`);
    } finally { setIsLoading(false); }
  };

  // Handler for clicking delete (opens modal)
  const handleDeleteClick = (userId) => { setItemToDelete(userId); setIsModalOpen(true); };
  // Handler for closing the modal
  const handleCloseModal = () => { setIsModalOpen(false); setItemToDelete(null); };

  // Handler for confirming deletion in the modal
  const handleConfirmDelete = async () => {
    if (!itemToDelete) return;
    setIsLoading(true); setError(null); setIsModalOpen(false);
    try {
      const response = await apiFetch(`${API_BASE_URL}/timers/${itemToDelete}`, { method: 'DELETE' });
      if (!response.ok) {
         // Handle 404 specifically (timer not found)
         if (response.status === 404) {
             // Try to get message from response, fallback to generic
             const errorData = await response.json().catch(() => ({}));
             throw new Error(errorData.message || `Timer not found for user ${itemToDelete}. It might have already expired or been deleted.`);
         }
        // Handle other errors
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`HTTP error! status: ${response.status} - ${errorData.error || errorData.message || 'Unknown error'}`);
      }
      fetchTimers(); // Refresh list on success
    } catch (e) {
      console.error("Failed to delete timer:", e);
      setError(`Failed to delete timer for user ${itemToDelete}: ${e.message}`);
    } finally { setIsLoading(false); setItemToDelete(null); }
  };

  // Helper function to format date strings
  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    try { return new Date(dateString).toLocaleString('it-IT'); }
    catch { return dateString; }
  };

  return (
     // Main container styling
     <div className="p-4 md:p-6 bg-white rounded-lg shadow border border-gray-200">
      {/* Title */}
      <h2 className="text-2xl font-semibold mb-4 text-gray-800">Timer Management</h2>
      {/* Error display */}
      {error && <div className="mb-4 p-3 bg-red-100 text-red-700 border border-red-300 rounded-md"><strong>Error:</strong> {error}</div>}
      {/* Toggle Add Form Button */}
       <button onClick={() => setShowAddForm(!showAddForm)} className="mb-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition duration-150 shadow focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
        {showAddForm ? 'Cancel' : '+ Add New Timer'}
      </button>

       {/* Add Timer Form (conditional) */}
       {showAddForm && (
        <form onSubmit={handleAddTimer} className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
          <h3 className="text-lg font-medium mb-3 text-gray-700">New Timer</h3>
          {/* Grid layout for form elements */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
             {/* User ID Input (spans 2 columns on medium screens) */}
             <div className="md:col-span-2">
               <label htmlFor="timerUserId" className="block text-sm font-medium text-gray-700 mb-1">User ID</label>
               <input type="text" id="timerUserId" value={newUserId} onChange={(e) => setNewUserId(e.target.value)} placeholder="Discord User ID" className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500" required />
             </div>
             {/* Duration Input (Number + Unit Select) */}
             <div>
                <label htmlFor="durationValue" className="block text-sm font-medium text-gray-700 mb-1">Duration</label>
                <div className="flex">
                    {/* Duration Value */}
                    <input type="number" id="durationValue" value={durationValue} onChange={(e) => setDurationValue(e.target.value)} min="1" className="w-1/2 px-3 py-2 border border-gray-300 rounded-l-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500" required />
                    {/* Duration Unit */}
                    <select id="durationUnit" value={durationUnit} onChange={(e) => setDurationUnit(e.target.value)} className="w-1/2 px-3 py-2 border border-l-0 border-gray-300 rounded-r-md bg-white focus:outline-none focus:ring-blue-500 focus:border-blue-500">
                        <option value="minutes">Minutes</option>
                        <option value="hours">Hours</option>
                        <option value="days">Days</option>
                    </select>
                </div>
             </div>
              {/* Timer Type (Mute/Ban) and Submit Button */}
             <div>
                <label htmlFor="timerType" className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                <div className="flex space-x-2">
                    {/* Type Select */}
                    <select id="timerType" value={addType} onChange={(e) => setAddType(e.target.value)} className="flex-grow px-3 py-2 border border-gray-300 rounded-md bg-white focus:outline-none focus:ring-blue-500 focus:border-blue-500">
                        <option value="mute">Mute</option>
                        <option value="ban">Ban</option>
                    </select>
                    {/* Submit Button */}
                     <button type="submit" disabled={isLoading} className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition duration-150 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2">
                        {isLoading ? 'Adding...' : 'Add'}
                    </button>
                </div>
             </div>
           </div>
         </form>
       )}

       {/* Loading Indicator */}
       {isLoading && <p className="text-center text-gray-600 my-4">Loading timers...</p>}
       {/* No Data Message */}
       {!isLoading && !error && timers.length === 0 && <p className="text-center text-gray-500 my-4">No active timers found.</p>}
       {/* Timers Table (conditional) */}
       {!isLoading && timers.length > 0 && (
         <div className="overflow-x-auto">
           {/* Table Structure */}
           <table className="min-w-full divide-y divide-gray-200">
             {/* Table Header */}
             <thead className="bg-gray-50">
               <tr>
                 <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User ID</th>
                 <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                 <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">End Time</th>
                 <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
               </tr>
             </thead>
             {/* Table Body */}
             <tbody className="bg-white divide-y divide-gray-200">
               {/* Map over current page data */}
               {currentTableData.map((timer) => (
                 <tr key={timer.user_id} className="hover:bg-gray-50 transition duration-150">
                   {/* User ID Cell */}
                   <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{timer.user_id}</td>
                   {/* Type Cell (with badges) */}
                   <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                     {timer.mute && <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-yellow-100 text-yellow-800">Mute</span>}
                     {timer.ban && <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-red-100 text-red-800">Ban</span>}
                   </td>
                   {/* End Time Cell (show both when the user has a mute AND a ban) */}
                   <td className="px-6 py-4 text-sm text-gray-600">
                     {timer.mute && (
                       <div className="whitespace-nowrap">
                         {timer.ban && <span className="font-medium">Mute: </span>}
                         {formatDate(timer.endMute)}
                       </div>
                     )}
                     {timer.ban && (
                       <div className="whitespace-nowrap">
                         {timer.mute && <span className="font-medium">Ban: </span>}
                         {formatDate(timer.endBan)}
                       </div>
                     )}
                   </td>
                   {/* Actions Cell (Delete Button) */}
                   <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                     <button onClick={() => handleDeleteClick(timer.user_id)} disabled={isLoading} className="text-red-600 hover:text-red-800 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1">Delete</button>
                   </td>
                 </tr>
               ))}
             </tbody>
           </table>
           {/* --- Pagination Component --- */}
            <Pagination
                totalItems={timers.length}
                itemsPerPage={rowsPerPage}
                currentPage={currentPage}
                onPageChange={handlePageChange}
                onItemsPerPageChange={handleRowsPerPageChange}
            />
         </div>
       )}
       {/* Confirmation Modal */}
       <ConfirmationModal isOpen={isModalOpen} onClose={handleCloseModal} onConfirm={handleConfirmDelete} title="Confirm Deletion">
         Are you sure you want to delete the timer for user ID: <strong className="font-semibold">{itemToDelete}</strong>? This will immediately unmute/unban them if the timer hasn't expired.
       </ConfirmationModal>
     </div>
   );
}

export default TimerManagement;