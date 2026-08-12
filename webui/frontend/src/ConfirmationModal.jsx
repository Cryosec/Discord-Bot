// discord-bot-v4/webui/frontend/src/ConfirmationModal.js
import React from 'react';

// Reusable Modal Component
function ConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  children,
  confirmText = "Confirm",
  confirmBgColor = "bg-red-600", // Default to red for destructive actions
  confirmHoverBgColor = "hover:bg-red-700"
}) {
  if (!isOpen) return null;

  return (
    // Using fixed positioning to overlay the whole screen
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 backdrop-blur-sm p-4" aria-labelledby="modal-title" role="dialog" aria-modal="true">
      {/* Modal panel */}
      <div className="bg-white p-6 rounded-lg shadow-xl max-w-sm w-full mx-auto">
        {/* Modal title */}
        <h2 id="modal-title" className="text-xl font-semibold mb-4 text-gray-800">{title}</h2>
        {/* Modal body content */}
        <div className="mb-6 text-gray-700">{children}</div>
        {/* Modal footer buttons */}
        <div className="flex justify-end space-x-3">
          <button
            onClick={onClose}
            type="button" // Explicitly type button to prevent form submission if inside one
            className="px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300 transition duration-150 focus:outline-none focus:ring-2 focus:ring-gray-400 focus:ring-offset-1"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            type="button"
            className={`px-4 py-2 text-white rounded-md ${confirmBgColor} ${confirmHoverBgColor} transition duration-150 focus:outline-none focus:ring-2 focus:ring-offset-1 ${confirmBgColor === 'bg-red-600' ? 'focus:ring-red-500' : 'focus:ring-blue-500'}`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmationModal;