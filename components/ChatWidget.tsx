'use client';

import React, { useState, useEffect } from 'react';
import { ChatUI } from '@/components/ChatUI';
import { MessageCircle, X } from 'lucide-react';

interface ChatWidgetProps {
  containerId?: string;
  submitUrl?: string;
  statusUrl?: string;
  historyUrl?: string;
}

export function ChatWidget({
  containerId = 'chat-widget-root',
  submitUrl,
  statusUrl,
  historyUrl,
}: ChatWidgetProps) {
  const [isOpen, setIsOpen] = useState(false);

  // Get URLs from data attributes or props
  const getSubmitUrl = () => {
    const container = document.getElementById(containerId);
    return submitUrl || container?.dataset.submitUrl || '/ai/demo/submit/';
  };

  const getStatusUrl = () => {
    const container = document.getElementById(containerId);
    return statusUrl || container?.dataset.statusUrl || '/ai/demo/status/';
  };

  const getHistoryUrl = () => {
    const container = document.getElementById(containerId);
    return historyUrl || container?.dataset.historyUrl || '/ai/demo/history/';
  };

  // Update container data attributes when props change
  useEffect(() => {
    const container = document.getElementById(containerId);
    if (container) {
      if (submitUrl) {
        container.dataset.submitUrl = submitUrl;
      }
      if (statusUrl) {
        container.dataset.statusUrl = statusUrl;
      }
      if (historyUrl) {
        container.dataset.historyUrl = historyUrl;
      }
    }
  }, [containerId, submitUrl, statusUrl, historyUrl]);

  return (
    <>
      {/* Floating Button - Hidden when chat is open */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex items-center justify-center w-14 h-14 rounded-full shadow-lg transition-all duration-300 bg-brand-indigo hover:bg-brand-deep-purple text-white focus:outline-none focus:ring-2 focus:ring-brand-indigo focus:ring-offset-2"
          aria-label="Open chat"
        >
          <MessageCircle
            size={24}
            className="transition-transform duration-200"
          />
        </button>
      )}

      {/* Slide-out Panel */}
      <div
        className={`fixed top-0 right-0 h-full w-full sm:w-96 bg-white shadow-2xl z-40 transform transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        } flex flex-col`}
      >
        {/* Panel Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-brand-indigo text-white">
          <h2 className="text-lg font-semibold">AI Assistant</h2>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1 hover:bg-brand-deep-purple rounded transition-colors"
            aria-label="Close chat"
          >
            <X size={20} />
          </button>
        </div>

        {/* Chat UI Container */}
        <div className="flex-1 overflow-hidden">
          <div
            id={containerId}
            data-submit-url={getSubmitUrl()}
            data-status-url={getStatusUrl()}
            data-history-url={getHistoryUrl()}
            className="h-full"
          >
            <ChatUI
              containerId={containerId}
              onClose={() => setIsOpen(false)}
            />
          </div>
        </div>
      </div>
    </>
  );
}
