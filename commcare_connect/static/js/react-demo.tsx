import React from 'react';
import { createRoot } from 'react-dom/client';
import { ChatUI } from '@/components/ChatUI';

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', () => {
  const container = document.getElementById('react-demo-root');

  if (container) {
    const root = createRoot(container);
    root.render(
      <React.StrictMode>
        <ChatUI />
      </React.StrictMode>,
    );
  }
});
