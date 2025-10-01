import React, { useState } from 'react';
import './App.css'; // Assuming you have some basic CSS

function App() {
  const [file, setFile] = useState(null);
  const [feedback, setFeedback] = useState('Upload a video to analyze the High Leg March.');
  const [loading, setLoading] = useState(false);

  const handleFileChange = (event) => {
    setFile(event.target.files[0]);
    setFeedback('File selected. Click "Analyze Drill" to process.');
  };

  const handleUpload = async () => {
    if (!file) {
      alert('Please select a video file first.');
      return;
    }

    setLoading(true);
    setFeedback('Processing video... this may take a moment.');

    const formData = new FormData();
    formData.append('video', file); // 'video' matches the key used in app.py: request.files['video']

    try {
      const response = await fetch('http://127.0.0.1:5000/upload_and_analyze', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (data.success) {
        // Display the multiline feedback string from the Python backend
        setFeedback(data.feedback);
      } else {
        setFeedback(`Analysis Failed: ${data.error}`);
      }

    } catch (error) {
      setFeedback(`Network Error: Could not connect to the backend server. Is Flask running? (${error.message})`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="App">
      <h1>NCC Drill Analysis System (MediaPipe)</h1>
      <input 
        type="file" 
        accept="video/mp4,video/avi" 
        onChange={handleFileChange} 
        disabled={loading}
      />
      <button 
        onClick={handleUpload} 
        disabled={!file || loading}>
        {loading ? 'Analyzing...' : 'Analyze Drill'}
      </button>

      <h2>Analysis Feedback</h2>
      {/* Pre-wrap ensures the newlines (\n) from Python are respected */}
      <pre className="feedback-box">
        {feedback}
      </pre>

    </div>
  );
}

export default App;