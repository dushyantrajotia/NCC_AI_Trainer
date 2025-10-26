import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import nccLogo from './assets/ncc_logo.png';
import nccUnity from './assets/ncc_unity.png';

// All external API keys and configurations are now securely handled by app.py

const DRILL_CHECKPOINTS = [
  { value: 'high_leg_march', label: 'High Leg March (Attention)' },
  { value: 'salute', label: 'NCC Salute' },
  { value: 'turn_right', label: 'Right Turn (Dahine Mur)' },
  { value: 'turn_left', label: 'Left Turn (Baen Mur)' },
];

function App() {
  const [file, setFile] = useState(null);
  const [selectedCheckpoints, setSelectedCheckpoints] = useState([]);
  const [feedback, setFeedback] = useState('Select a mode (Upload or Live) and one or more drills.');
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [imageSource, setImageSource] = useState(null);
  const [voiceLoading, setVoiceLoading] = useState(false);
  
  // --- NEW LIVE MODE STATES ---
  const [isLiveMode, setIsLiveMode] = useState(false);
  const videoRef = useRef(null); // Reference for the webcam feed video element
  const streamRef = useRef(null); // Reference for the MediaStream object
  // --- END NEW LIVE MODE STATES ---

  const resultsRef = useRef(null);
  const canvasRef = useRef(null); 

  // --- 🚀 AMAZON POLLY TTS FUNCTION (Calling Flask Backend) 🚀 ---
  const playVoiceReport = async (text) => {
    if (voiceLoading) return;

    setVoiceLoading(true);
    const report_text = text.replace(/[^a-zA-Z0-9.,;!?()\s]/g, '');

    try {
      const response = await fetch('http://127.0.0.1:5000/generate_polly_voice', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ report_text }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `Backend failed with status: ${response.status}`);
      }

      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);

      const audio = new Audio(audioUrl);
      audio.play();

      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        setVoiceLoading(false);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        setVoiceLoading(false);
        alert("Error playing audio stream.");
      };

    } catch (error) {
      console.error("Error generating Amazon Polly voice:", error);
      alert(`Voice generation failed. Please check your terminal for AWS credential errors. Details: ${error.message}`);
      setVoiceLoading(false);
    }
  };

  // --- NEW LIVE STREAM CONTROL FUNCTIONS ---
  const startLiveStream = async () => {
    setFile(null); 
    setFeedback("Live drill instructor activated. Strike a pose and click 'Capture & Analyze Frame'.");
    
    try {
      // Request camera access
      const stream = await navigator.mediaDevices.getUserMedia({ 
          video: { width: 640, height: 480 }, 
          audio: false 
      });
      streamRef.current = stream;
      videoRef.current.srcObject = stream;
      setIsLiveMode(true);
    } catch (err) {
      console.error("Error accessing webcam: ", err);
      alert("Cannot access webcam. Please check browser permissions and ensure no other app is using it.");
      setIsLiveMode(false);
    }
  };

  const stopLiveStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
    }
    setIsLiveMode(false);
    setFeedback("Live stream stopped. Select a mode to continue.");
    setImageSource(null); 
  };
  
  useEffect(() => {
    // Cleanup on component unmount or state changes
    return () => stopLiveStream();
  }, []);
  // --- END LIVE STREAM CONTROL FUNCTIONS ---

  // --- NEW LIVE FRAME ANALYZER ---
  const handleLiveAnalyze = async () => {
    if (!isLiveMode || selectedCheckpoints.length === 0) return alert('Start live stream and select a drill.');
    if (loading) return;
    
    setLoading(true);
    setProgress(1); 
    setFeedback('Capturing and analyzing live frame...');

    const videoElement = videoRef.current;
    if (!videoElement || videoElement.videoWidth === 0) {
        setLoading(false);
        setFeedback('Webcam stream is not ready.');
        return;
    }
    
    // Capture frame to an in-memory canvas
    const canvas = document.createElement('canvas');
    canvas.width = videoElement.videoWidth;
    canvas.height = videoElement.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);

    // Convert to JPEG blob and send
    canvas.toBlob(async (blob) => {
        if (!blob) {
            setLoading(false);
            setFeedback('Failed to capture frame from video stream.');
            return;
        }

        const formData = new FormData();
        formData.append('frame', blob, 'live_frame.jpg');
        formData.append('drill_types', JSON.stringify(selectedCheckpoints));

        try {
            const response = await fetch('http://127.0.0.1:5000/analyze_live_frame', {
                method: 'POST',
                body: formData,
            });
            
            setProgress(100);
            const data = await response.json();
            setTimeout(() => setLoading(false), 300);

            if (response.ok && data.success) {
                setFeedback(data.feedback);
                setImageSource(data.annotated_image_b64 || null);
                playVoiceReport(data.feedback); 

            } else {
                setFeedback(`Live Analysis Failed: ${data.error || 'Unknown error.'}`);
                setImageSource(null);
            }
        } catch (error) {
            setFeedback(`Live Network Error: ${error.message}`);
            setLoading(false);
        }
    }, 'image/jpeg', 0.8);
  };
  // --- END LIVE FRAME ANALYZER ---

  // --- EXISTING VIDEO UPLOAD/ANALYSIS FUNCTIONS ---
  const handleFileChange = (e) => {
    const uploadedFile = e.target.files[0];
    setFile(uploadedFile || null);
    setFeedback(uploadedFile ? `Selected: ${uploadedFile.name}` : 'Select a mode and one or more drills.');
    if(isLiveMode) stopLiveStream(); 
  };

  const handleCheckpointChange = (e) => {
    const { value, checked } = e.target;
    setSelectedCheckpoints(prev =>
      checked ? [...prev, value] : prev.filter(v => v !== value)
    );
  };

  const simulateProgress = () => {
    setProgress(0);
    const interval = setInterval(() => {
      setProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          return 100;
        }
        return prev + Math.floor(Math.random() * 5 + 1);
      });
    }, 300);
  };

  const handleAnalyze = async () => {
    if (!file) return alert('Please upload a video.');
    if (selectedCheckpoints.length === 0) return alert('Select at least one drill.');
    if(isLiveMode) stopLiveStream(); 

    setLoading(true);
    simulateProgress();
    setFeedback('Analyzing video...');

    const formData = new FormData();
    formData.append('video', file);
    formData.append('drill_types', JSON.stringify(selectedCheckpoints));

    try {
      const response = await fetch('http://127.0.0.1:5000/upload_and_analyze', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      setProgress(100);
      setTimeout(() => setLoading(false), 500);

      if (response.ok && data.success) {
        setFeedback(data.feedback);
        setImageSource(data.annotated_image_b64 || null);
        resultsRef.current.scrollIntoView({ behavior: 'smooth' });
        playVoiceReport(data.feedback);
      } else {
        setFeedback(`Analysis Failed: ${data.error || 'Unknown error.'}`);
        setImageSource(null);
        resultsRef.current.scrollIntoView({ behavior: 'smooth' });
      }
    } catch (error) {
      setFeedback(`Network Error: ${error.message}`);
      setImageSource(null);
      setLoading(false);
      resultsRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // --- BACKGROUND CANVAS ANIMATION (PLACEHOLDER) ---
  useEffect(() => {
    // NOTE: Keep your original canvas animation code here. 
    // I'm using a placeholder for brevity.
    const animationFrameId = requestAnimationFrame(() => {});
    return () => cancelAnimationFrame(animationFrameId);
  }, []);
  // --- END BACKGROUND CANVAS ANIMATION ---


  // --- JSX RENDER ---
  return (
    <div className="app-container">
      {/* Background Canvas */}
      <canvas id="bg-canvas" ref={canvasRef} style={{position: 'fixed',top: 0,left: 0,width: '100%',height: '100%',zIndex: -1}}></canvas>

      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <img src={nccLogo} alt="NCC Logo" className="logo" />
          <span className="ncc-text">
            <span className="ncc-red">NCC </span>
            <span className="ncc-sky">CADET </span>
            <span className="ncc-blue">CORPS</span>
          </span>
        </div>
        <h1 className="header-title">NCC DRILL ANALYZER</h1>
        <div className="header-right">
          <img src={nccUnity} alt="NCC Unity" className="logo" />
        </div>
      </header>
      <div className="header-line"></div>

      <br></br>
      
      {/* 🚀 NEW: Mode Selection Section 🚀 */}
      <h2 className="centered" style={{ marginTop: '20px', color: 'white' }}>Select Analysis Mode:</h2>
      <div className="mode-selection centered">
          <button 
              className={`mode-button ${!isLiveMode ? 'active' : ''}`}
              onClick={stopLiveStream}
          >
              Upload Video
          </button>
          <button 
              className={`mode-button ${isLiveMode ? 'active' : ''}`}
              onClick={isLiveMode ? stopLiveStream : startLiveStream}
          >
              {isLiveMode ? 'Stop Live Drill' : 'Start Live Drill'}
          </button>
      </div>
      
      <br></br>
      
      {/* Conditional Input based on mode */}
      <div className="input-analysis-container centered">
        {!isLiveMode ? (
            <div className="analyze-section">
                <input type="file" accept="video/mp4,video/avi" onChange={handleFileChange} disabled={loading} />
                <button onClick={handleAnalyze} disabled={loading || !file || selectedCheckpoints.length === 0}>
                    Analyze Uploaded Video
                </button>
                <p className="hint" style={{color: 'white', marginTop: '10px'}}>{file ? `Video Selected: ${file.name}` : 'No Video Selected'}</p>
            </div>
        ) : (
            <div className="live-section">
                {/* Webcam Feed */}
                <video ref={videoRef} autoPlay playsInline style={{ width: '100%', maxWidth: '600px', borderRadius: '8px', border: '3px solid #ccc' }}></video>
                <button onClick={handleLiveAnalyze} disabled={loading || selectedCheckpoints.length === 0}>
                    Capture & Analyze Frame
                </button>
                <p className="hint" style={{color: 'white', marginTop: '10px'}}>Perform the desired drill posture and click the button to analyze the current frame.</p>
            </div>
        )}
      </div>
      
      <br></br>

      <h2 className="centered" style={{ color: 'white' }}>Choose command to be analyzed : </h2>

      <div className="checkbox-grid">
        {DRILL_CHECKPOINTS.map(d => (
          <label key={d.value} className="checkbox-label">
            <input type="checkbox" value={d.value} onChange={handleCheckpointChange} disabled={loading} />
            {d.label}
          </label>
        ))}
      </div>

      {/* Loading Overlay */}
      {loading && (
        <div className="loading-overlay">
          <div className="loading-box">
            <p>{isLiveMode ? 'Analyzing Frame...' : `Analyzing: ${Math.min(progress, 100)}%`}</p>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${Math.min(progress, 100)}%` }}></div>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      <div ref={resultsRef} className="results-section">
        <div className="visual-feedback">
          <h2 className="centered" style={{ color: 'white' }}>Visual Feedback:</h2>
          {imageSource ? <img src={imageSource} alt="Annotated Drill" /> : <p className="text-white">No image generated.</p>}
        </div>
        <div className="analysis-report">
          <h2 className="centered" style={{ color: 'white' }}>Analysis Report:</h2>
          <pre style={{ backgroundColor: '#2c3e50', padding: '15px', borderRadius: '8px', color: '#ecf0f1' }}>{feedback}</pre>
          {feedback && (
            <button
              onClick={() => playVoiceReport(feedback)}
              disabled={voiceLoading}
              style={{
                marginTop: '15px',
                padding: '10px 20px',
                backgroundColor: voiceLoading ? '#90A4AE' : '#0D47A1',
                color: 'white',
                fontWeight: 'bold',
                border: 'none',
                borderRadius: '6px',
                cursor: voiceLoading ? 'not-allowed' : 'pointer'
              }}
            >
              🔊 {voiceLoading ? 'Generating Voice...' : 'Play Voice Report'}
            </button>
          )}
        </div>
      </div>

      <br></br>
      <br></br>
      <footer className="app-footer centered" style={{ color: 'white' }}>© 2025 NCC - CTUNIVERSITY. All Rights Reserved.</footer>
    </div>
  );
}

export default App;