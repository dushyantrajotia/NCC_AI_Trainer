import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import basicSsl from '@vitejs/plugin-basic-ssl'; // Import the plugin

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    basicSsl() // Add the SSL plugin here
  ],
  server: {
    https: true, // Enable HTTPS
    port: 5173, // Keep the same port
    // Optional: Open the browser automatically
    // open: true
  }
});