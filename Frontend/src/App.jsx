import React, { useState, useEffect } from 'react';
import { Download, AlertTriangle, Image, CheckCircle } from 'lucide-react'; 

// Define the available drill checkpoints. Must match keys in app.py's DRILL_FUNCTION_MAP.
const DRILL_CHECKPOINTS = [
  { value: 'high_leg_march', label: 'High Leg March (Attention)' },
  { value: 'salute', label: 'NCC Salute' },
  { value: 'turn_right', label: 'Right Turn (Dahine Mur)' },
  { value: 'turn_left', label: 'Left Turn (Baen Mur)' },
];

function App() {
  const [file, setFile] = useState(null);
  const [selectedCheckpoints, setSelectedCheckpoints] = useState([DRILL_CHECKPOINTS[0].value]);
  const [feedback, setFeedback] = useState('Select one or more drills and upload a video.');
  const [loading, setLoading] = useState(false);
  const [fileName, setFileName] = useState('');
  const [imageSource, setImageSource] = useState(null); // Stores the Base64 image URL
  const [showError, setShowError] = useState(''); 

  // Effect to clear potential error message
  useEffect(() => {
    if (showError) {
      const timer = setTimeout(() => setShowError(''), 5000);
      return () => clearTimeout(timer);
    }
  }, [showError]);

  const handleFileChange = (event) => {
    const uploadedFile = event.target.files[0];
    setFile(uploadedFile);
    setFileName(uploadedFile ? uploadedFile.name : '');
    setImageSource(null); // Clear previous image source
    setFeedback(`File selected: ${uploadedFile ? uploadedFile.name : ''}. Click Analyze Drill.`);
  };

  const handleCheckpointChange = (event) => {
    const { value, checked } = event.target;

    setSelectedCheckpoints(prev => 
      checked 
        ? [...prev, value] // Add to array if checked
        : prev.filter(v => v !== value) // Remove from array if unchecked
    );
  };

  const handleUpload = async () => {
    if (!file) {
      setShowError('Please select a video file first.');
      return;
    }
    if (selectedCheckpoints.length === 0) {
      setShowError('Please select at least one drill checkpoint to analyze.');
      return;
    }

    setLoading(true);
    setImageSource(null);
    setFeedback('Processing video... analyzing frames and generating annotated image. This may take a moment.');

    const formData = new FormData();
    formData.append('video', file); 
    formData.append('drill_types', JSON.stringify(selectedCheckpoints)); 

    try {
      const response = await fetch('http://127.0.0.1:5000/upload_and_analyze', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (response.ok && data.success) {
        // Success: Set text report and image source
        setFeedback(data.feedback);
        if (data.annotated_image_b64) {
            setImageSource(data.annotated_image_b64);
        } else {
            setImageSource(null);
            setFeedback(data.feedback + "\n\n(Note: No failure or success image was produced for this analysis.)");
        }
      } else {
        // Failure: Display specific error message from the backend
        setFeedback(`Analysis Failed (HTTP ${response.status} Error): ${data.error || 'Unknown error. Check the Flask console.'}`);
        setImageSource(null);
      }

    } catch (error) {
      setFeedback(`Network Error: Could not connect to the backend server. Is Flask running on port 5000? Error: ${error.message}`);
      setImageSource(null);
    } finally {
      setLoading(false);
    }
  };

  const getDrillLabels = () => selectedCheckpoints.map(value => DRILL_CHECKPOINTS.find(d => d.value === value)?.label).join(', ');

  return (
    <div style={styles.container}>
      <h1 style={styles.header}>NCC Drill Procedure Analyzer</h1>
      
      {showError && (
        <div style={styles.errorBox}>
          <AlertTriangle size={20} style={{marginRight: '8px'}} />
          {showError}
        </div>
      )}

      <div style={styles.controlGroup}>
        <label style={styles.label}>Select Checkpoints:</label>
        <div style={styles.checkboxContainer}>
          {DRILL_CHECKPOINTS.map((drill) => (
            <label key={drill.value} style={styles.checkboxLabel}>
              <input
                type="checkbox"
                value={drill.value}
                checked={selectedCheckpoints.includes(drill.value)}
                onChange={handleCheckpointChange}
                disabled={loading}
                style={styles.checkboxInput}
              />
              {drill.label}
            </label>
          ))}
        </div>
      </div>

      <div style={styles.uploadSection}>
        <label style={styles.label}>Upload Video (MP4/AVI):</label>
        <div style={{display: 'flex', gap: '10px', alignItems: 'center'}}>
            <input 
              type="file" 
              accept="video/mp4,video/avi" 
              onChange={handleFileChange} 
              disabled={loading}
              style={styles.fileInput}
            />
        </div>
        {fileName && <p style={styles.fileNameText}>Selected: {fileName} | Analyzing: {getDrillLabels()}</p>}
      </div>

      <button 
        onClick={handleUpload} 
        disabled={!file || loading || selectedCheckpoints.length === 0}
        style={styles.button(loading)}
      >
        {loading ? 'Analyzing...' : 'Analyze Drill'}
      </button>

      <div style={styles.reportLayout}>
        {/* --- Visual Feedback (Image Display) --- */}
        <div style={styles.imageColumn}>
            <h2 style={styles.feedbackHeader}>Visual Feedback</h2>
            <div style={styles.imageBox}>
                {loading && <div style={styles.placeholder}><Image size={48} color="#ccc" /><p style={{color: '#999'}}>Generating Annotated Image...</p></div>}
                
                {/* 🚨 RENDER IMAGE HERE 🚨 */}
                {!loading && imageSource && (
                    <img src={imageSource} alt="Annotated Drill Posture" style={styles.imagePlayer} />
                )}
                
                {!loading && !imageSource && <div style={styles.placeholder}><Image size={48} color="#ccc" /><p style={{color: '#999'}}>Upload video to begin analysis.</p></div>}
            </div>
            
        </div>

        {/* --- Text Feedback Report --- */}
        <div style={styles.reportColumn}>
            <h2 style={styles.feedbackHeader}>Analysis Report</h2>
            <pre style={styles.feedbackBox}>
              {feedback}
            </pre>
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: {
    maxWidth: '1000px',
    margin: '40px auto',
    padding: '25px',
    fontFamily: 'Inter, sans-serif',
    borderRadius: '16px',
    boxShadow: '0 12px 24px rgba(0, 0, 0, 0.2)',
    backgroundColor: '#F7F9FC',
    textAlign: 'center',
  },
  header: {
    color: '#1565C0', 
    marginBottom: '15px',
    borderBottom: '3px solid #E0E0E0',
    paddingBottom: '10px',
  },
  errorBox: {
    backgroundColor: '#FFCDD2',
    color: '#C62828',
    padding: '12px',
    borderRadius: '8px',
    marginBottom: '20px',
    fontWeight: 'bold',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  controlGroup: {
    marginBottom: '20px',
  },
  label: {
    fontWeight: 'bold',
    marginBottom: '8px',
    color: '#333',
    alignSelf: 'flex-start',
    width: '100%',
    textAlign: 'left',
  },
  checkboxContainer: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '20px',
    padding: '15px',
    border: '1px solid #B0BEC5',
    borderRadius: '10px',
    backgroundColor: '#E3F2FD',
    width: '100%',
    justifyContent: 'space-between',
    boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.1)',
  },
  checkboxLabel: {
    display: 'flex',
    alignItems: 'center',
    cursor: 'pointer',
    fontSize: '15px',
    color: '#1F2937',
    flexBasis: '48%', 
    textAlign: 'left',
  },
  checkboxInput: {
    marginRight: '8px',
    minWidth: '18px',
    minHeight: '18px',
    accentColor: '#1565C0',
  },
  uploadSection: {
    marginBottom: '25px',
    textAlign: 'left',
  },
  fileInput: {
    padding: '10px 0',
    border: 'none',
    backgroundColor: 'transparent',
    fontSize: '15px',
  },
  fileNameText: {
    marginTop: '10px',
    color: '#00796B',
    fontSize: '14px',
    paddingTop: '5px',
    borderTop: '1px dotted #B0BEC5',
  },
  button: (loading) => ({
    padding: '14px 30px',
    backgroundColor: loading ? '#64B5F6' : '#1565C0',
    color: 'white',
    border: 'none',
    borderRadius: '10px',
    fontSize: '18px',
    fontWeight: 'bold',
    cursor: loading ? 'not-allowed' : 'pointer',
    transition: 'background-color 0.3s ease, box-shadow 0.3s ease',
    width: '100%',
    boxShadow: '0 4px 10px rgba(0, 0, 0, 0.2)',
    opacity: loading ? 0.9 : 1,
  }),
  reportLayout: {
    marginTop: '30px',
    display: 'flex',
    gap: '25px',
    textAlign: 'left',
    '@media (max-width: 768px)': {
        flexDirection: 'column',
    },
  },
  imageColumn: {
    flex: 1,
    minWidth: '400px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    '@media (max-width: 768px)': {
        minWidth: 'auto',
        width: '100%',
    },
  },
  reportColumn: {
    flex: 1,
    minWidth: '400px',
    '@media (max-width: 768px)': {
        minWidth: 'auto',
        width: '100%',
    },
  },
  feedbackHeader: {
    color: '#1565C0',
    marginBottom: '15px',
    fontSize: '20px',
    textAlign: 'center',
  },
  imageBox: { 
    width: '100%',
    aspectRatio: '4/3', 
    backgroundColor: '#E0E0E0',
    borderRadius: '10px',
    overflow: 'hidden',
    boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
  },
  imagePlayer: { 
    width: '100%',
    height: '100%',
    objectFit: 'contain',
  },
  placeholder: {
    textAlign: 'center',
    padding: '40px',
  },
  feedbackBox: {
    backgroundColor: '#FFFFFF',
    border: '1px solid #B0BEC5',
    borderRadius: '10px',
    padding: '15px',
    whiteSpace: 'pre-wrap', 
    wordWrap: 'break-word',
    minHeight: '300px',
    fontSize: '14px',
    color: '#1F2937',
    overflowX: 'auto',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  },
};

export default App;
