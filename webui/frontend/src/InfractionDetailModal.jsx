// ========================================================================
// NEW COMPONENT: InfractionDetailModal.js
// Modal to display detailed infraction information for a user
// ========================================================================
import React from 'react';

// Helper function to format date strings (can be moved to a utils file)
const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    try {
        // Use Italian locale for DD/MM/YYYY, HH:MM:SS format
        return new Date(dateString).toLocaleString('it-IT');
    } catch (e) {
        console.warn("Could not format date:", dateString, e);
        return dateString; // Return original string if formatting fails
    }
};

function InfractionDetailModal({
    isOpen,
    onClose,
    userData, // Contains { user_id, tag, warnings, kicks, bans, reasons: [{ reason, timestamp }, ...] }
    isLoading, // Loading state specifically for fetching details
    error,     // Error state specifically for fetching details
}) {
    // Don't render the modal if it's not open
    if (!isOpen) {
        return null;
    }

    // Determine content based on loading/error/data state
    let modalContent;
    if (isLoading) {
        modalContent = <p className="text-center text-gray-600 my-4">Loading details...</p>;
    } else if (error) {
        modalContent = <div className="p-3 bg-red-100 text-red-700 border border-red-300 rounded-md"><strong>Error:</strong> {error}</div>;
    } else if (!userData) {
        // Should ideally not happen if modal is opened correctly, but handle defensively
        modalContent = <p className="text-center text-gray-500 my-4">No user data available.</p>;
    } else {
        // Display user details and reasons list
        modalContent = (
            <>
                {/* User Summary */}
                <div className="mb-4 grid grid-cols-3 gap-x-4 gap-y-2 text-sm">
                    <div><strong>User ID:</strong></div>
                    <div className="col-span-2 text-gray-800">{userData.user_id}</div>

                    <div><strong>Tag:</strong></div>
                    <div className="col-span-2 text-gray-800">{userData.tag || 'N/A'}</div>

                    <div><strong>Warnings:</strong></div>
                    <div className="col-span-2 text-gray-800">{userData.warnings ?? 'N/A'}</div>

                    <div><strong>Kicks:</strong></div>
                    <div className="col-span-2 text-gray-800">{userData.kicks ?? 'N/A'}</div>

                    <div><strong>Bans:</strong></div>
                    <div className="col-span-2 text-gray-800">{userData.bans ?? 'N/A'}</div>
                </div>

                {/* Reasons List */}
                <h4 className="text-md font-semibold mb-2 text-gray-700 border-t pt-3">Reasons History</h4>
                {userData.reasons && userData.reasons.length > 0 ? (
                    <ul className="list-disc pl-5 space-y-2 max-h-60 overflow-y-auto text-sm text-gray-600 border rounded-md p-3 bg-gray-50">
                        {userData.reasons.map((item, index) => (
                            <li key={index}>
                                <span className="font-medium text-gray-800">{item.reason}</span>
                                {item.timestamp && (
                                    <span className="text-xs text-gray-500 ml-2">({formatDate(item.timestamp)})</span>
                                )}
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p className="text-sm text-gray-500 italic">No reasons recorded for this user.</p>
                )}
            </>
        );
    }

    return (
        // Modal backdrop: fixed position, covers screen, centers content, adds blur
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-60 backdrop-blur-sm p-4 transition-opacity duration-300 ease-in-out">
            {/* Modal container: white background, rounded, shadow, max width */}
            <div className="bg-white rounded-lg shadow-xl w-full max-w-lg overflow-hidden">
                {/* Modal Header: Title and Close Button */}
                <div className="flex justify-between items-center p-4 border-b">
                    <h3 className="text-xl font-semibold text-gray-800">Infraction Details</h3>
                    {/* Close button (X icon) */}
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-gray-600 focus:outline-none"
                        aria-label="Close modal"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Modal Body: Contains the user details or loading/error message */}
                <div className="p-5">
                    {modalContent}
                </div>

                {/* Modal Footer: Close button */}
                <div className="flex justify-end p-3 bg-gray-50 border-t">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 bg-gray-600 text-white text-sm rounded-md hover:bg-gray-700 transition duration-150 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-1"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}

export default InfractionDetailModal;