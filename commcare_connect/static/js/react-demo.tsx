import React from 'react';
import { createRoot } from 'react-dom/client';
import { HelloWorld } from '@/components/HelloWorld';

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', () => {
  const container = document.getElementById('react-demo-root');

  if (container) {
    const root = createRoot(container);
    root.render(
      <React.StrictMode>
        <HelloWorld />
      </React.StrictMode>,
    );
  }
});
