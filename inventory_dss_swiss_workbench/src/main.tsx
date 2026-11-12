import React from 'react';
import { createRoot } from 'react-dom/client';
import '../tokens.css';
import './styles/utilities.css';
import App from './App';

const rootElement = document.getElementById('root');
if (rootElement) {
  createRoot(rootElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}
