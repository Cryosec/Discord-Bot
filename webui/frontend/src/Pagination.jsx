// ========================================================================
// NEW COMPONENT: Pagination.js
// Reusable component for table pagination controls
// ========================================================================
import React from 'react';

// Define the options for rows per page
const ROWS_PER_PAGE_OPTIONS = [10, 20, 50, 100];

function Pagination({
  totalItems,
  itemsPerPage,
  currentPage,
  onPageChange,
  onItemsPerPageChange,
}) {
  // Calculate the total number of pages
  // If itemsPerPage is 'All' (-1), there's only 1 page
  const totalPages = itemsPerPage === -1 ? 1 : Math.ceil(totalItems / itemsPerPage);

  // Handler for changing the number of items per page
  const handleItemsPerPageChange = (event) => {
    const newItemsPerPage = parseInt(event.target.value, 10); // Use -1 to represent 'All'
    onItemsPerPageChange(newItemsPerPage);
  };

  // Handler for navigating to the previous page
  const handlePreviousPage = () => {
    if (currentPage > 1) {
      onPageChange(currentPage - 1);
    }
  };

  // Handler for navigating to the next page
  const handleNextPage = () => {
    if (currentPage < totalPages) {
      onPageChange(currentPage + 1);
    }
  };

  // Don't render pagination if there are no items or only one page is needed
  if (totalItems === 0 || totalPages <= 1) {
    // Still show the 'Rows per page' selector if there are items
    if (totalItems > ROWS_PER_PAGE_OPTIONS[0]) {
         return (
             <div className="mt-4 flex justify-end items-center space-x-2 text-sm text-gray-600">
                <span>Rows per page:</span>
                <select
                    value={itemsPerPage}
                    onChange={handleItemsPerPageChange}
                    className="px-2 py-1 border border-gray-300 rounded-md bg-white focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                >
                    {ROWS_PER_PAGE_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                            {option}
                        </option>
                    ))}
                    <option value={-1}>All</option> {/* Use -1 for All */}
                </select>
             </div>
         );
    }
    return null; // Hide pagination completely if not needed
  }

  // Calculate the start and end item numbers for the current page view
  const startItem = (currentPage - 1) * itemsPerPage + 1;
  const endItem = Math.min(currentPage * itemsPerPage, totalItems);

  return (
    <div className="mt-4 flex flex-col md:flex-row justify-between items-center space-y-2 md:space-y-0 text-sm text-gray-600">
      {/* Rows per page selector */}
      <div className="flex items-center space-x-2">
        <span>Rows per page:</span>
        <select
          value={itemsPerPage}
          onChange={handleItemsPerPageChange}
          className="px-2 py-1 border border-gray-300 rounded-md bg-white focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
        >
          {ROWS_PER_PAGE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
          <option value={-1}>All</option> {/* Use -1 for All */}
        </select>
      </div>

      {/* Page information and navigation */}
      <div className="flex items-center space-x-4">
        <span>
          {startItem}-{endItem} of {totalItems}
        </span>
        <div className="flex items-center space-x-1">
          <button
            onClick={handlePreviousPage}
            disabled={currentPage === 1}
            className="px-2 py-1 border border-gray-300 rounded-md hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="Previous Page"
          >
            {/* SVG for Previous Arrow (Heroicon: chevron-left) */}
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
          </button>
          <span className="px-2">
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={handleNextPage}
            disabled={currentPage === totalPages}
            className="px-2 py-1 border border-gray-300 rounded-md hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="Next Page"
          >
            {/* SVG for Next Arrow (Heroicon: chevron-right) */}
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

export default Pagination;