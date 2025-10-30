import React, { useState, useEffect, useRef } from 'react';

// 🚨 All file imports that caused errors have been removed.

// --- DRILL DEFINITIONS ---
const DRILL_CHECKPOINTS = [
  { value: 'high_leg_march', label: 'High Leg March (Attention)' },
  { value: 'salute', label: 'NCC Salute' },
  { value: 'turn_right', label: 'Right Turn (Dahine Mur)' },
  { value: 'turn_left', label: 'Left Turn (Baen Mur)' },
];

function App() {
  // --- STATE MANAGEMENT ---
  const [file, setFile] = useState(null);
  const [selectedCheckpoints, setSelectedCheckpoints] = useState([]);
  const [feedback, setFeedback] = useState('Welcome! Please select an analysis mode.');
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [imageSource, setImageSource] = useState(null);
  const [voiceLoading, setVoiceLoading] = useState(false);
  
  // --- LIVE MODE STATE ---
  const [isLiveMode, setIsLiveMode] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [availableDevices, setAvailableDevices] = useState([]); // Stores enumerated devices
  
  // --- REFS ---
  const videoRef = useRef(null); 
  const streamRef = useRef(null); // Ref for MediaStream
  const resultsRef = useRef(null); 
  // removed canvasRef as particle animation is removed

  // --- 🚀 AMAZON POLLY TTS FUNCTION (Calling Flask Backend) 🚀 ---
  const playVoiceReport = async (text) => {
    if (voiceLoading) return;

    setVoiceLoading(true);
    // Sanitize text for SSML and voice
    const report_text = text.replace(/[^a-zA-Z0-9.,;!?()\s]/g, '');

    try {
      const response = await fetch('http://127.0.0.1:5000/generate_polly_voice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

  // --- UTILITY: SMALL DELAY FUNCTION ---
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  
  // --- LIVE STREAM CONTROL FUNCTIONS (LOCAL/VIRTUAL WEBCAM) ---

  // 1. Get list of potential camera devices
  const getTargetDevices = () => {
    setCameraError(null);
    const videoDevices = availableDevices.filter(device => device.kind === 'videoinput');
    
    if (videoDevices.length === 0) {
        setCameraError("No video input devices found. Ensure webcam access is allowed.");
        return [];
    }
    
    const candidates = [];
    const internalDevices = [];

    // Prioritize external/virtual devices
    videoDevices.forEach(device => {
        const label = device.label.toLowerCase();
        if (label.includes('droidcam') || label.includes('iriun') || label.includes('epoccam') || !label.includes('integrated')) {
            candidates.push(device.deviceId);
        } else {
            internalDevices.push(device.deviceId);
        }
    });

    const uniqueCandidates = [...new Set(candidates)];
    // Fallback to internal devices if no external ones are found
    const finalDeviceList = uniqueCandidates.length > 0 ? uniqueCandidates : internalDevices;
    
    // Return all viable candidates to try
    return finalDeviceList;
  };
  
  // 2. Request permissions on load
  const requestMediaPermissions = async () => {
    try {
        // Request a stream first (simple access check)
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        stream.getTracks().forEach(track => track.stop()); // Immediately stop it

        // Then, enumerate and store the device list
        const devices = await navigator.mediaDevices.enumerateDevices();
        setAvailableDevices(devices);
        setFeedback("Camera setup complete. Ready to start live drill.");
    } catch (err) {
        setCameraError(`Permission Denied: ${err.name}. Please ensure your phone camera app is running and permissions are granted.`);
        setAvailableDevices([]);
        setFeedback(`Live stream blocked. See error below.`);
    }
  };
  
  // 3. Start the live stream
  const startLiveStream = async () => {
    setFile(null); 
    setFeedback("Attempting to connect to camera...");
    setCameraError(null);
    setIsLiveMode(true); // Set live mode active

    // 1. Get the list of potential device IDs
    const deviceIds = getTargetDevices();

    if (deviceIds.length === 0) {
      setFeedback(`Live stream failed. Error: ${cameraError || "No suitable camera ID found. Ensure app is connected."}`);
      setIsLiveMode(false);
      return;
    }

    let stream = null;
    let successfulDeviceId = null;
    let lastError = null;
    const MAX_ATTEMPTS = 3;
    
    // 2. Loop through candidate device IDs until a stream works, with retries
    for (const deviceId of deviceIds) {
        for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            setFeedback(`Attempting connection (Device ${deviceId.slice(0, 4)}... - Try ${attempt}/${MAX_ATTEMPTS})...`);
            try {
                // Use simplest constraints first
                const constraints = { 
                    video: { 
                        deviceId: { exact: deviceId }
                    }, 
                    audio: false 
                };
                
                stream = await navigator.mediaDevices.getUserMedia(constraints); 
                successfulDeviceId = deviceId;
                break; // Success! Break out of inner attempt loop.
            } catch (err) {
                lastError = err.name;
                console.warn(`Attempt ${attempt} failed for device ID ${deviceId}: ${err.name}`);
                await delay(attempt * 500); // Wait longer on subsequent failures
            }
        }
        if (stream) break; // Success! Break out of outer device loop.
    }

    if (!stream) {
        setFeedback(`Cannot start stream. Tried ${deviceIds.length} devices. Last Error: ${lastError || "Unknown connection failure."}`);
        setIsLiveMode(false);
        return;
    }

    // 3. Handle successful stream connection and video playback
    streamRef.current = stream;

    try {
      if (videoRef.current) {
        const video = videoRef.current;
        video.srcObject = stream;
        
        // 4. Wait for the video element to confirm stream load AND playability
        await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                if (video.readyState < 3 && video.srcObject) {
                    console.warn("Stream timed out. Attempting quick reload...");
                    video.load(); 
                    setTimeout(() => {
                        video.oncanplay = resolve; 
                        video.onerror = (e) => reject(new Error("Video reload failed."));
                    }, 1000); // Give reload 1 sec
                } else {
                    reject(new Error("Video stream load timeout/failure."));
                }
            }, 8000); // 8-second timeout

            video.oncanplay = () => {
                clearTimeout(timeout);
                setTimeout(() => {
                    if(video.srcObject) { 
                        resolve(); 
                    } else {
                        reject(new Error("Stream is playable, but srcObject is empty."));
                    }
                }, 100); 
            };
            video.onerror = (e) => {
                clearTimeout(timeout);
                reject(new Error(`Video Element Error: ${e.message || e.currentTarget.error.message}`));
            };
        });
        
        // 5. Attempt to play
        try {
            await videoRef.current.play();
            console.log("Video playback started successfully.");
        } catch (playError) {
            console.error("Video play() failed:", playError);
            throw new Error(`Video play failed: ${playError.name}. Browser might block autoplay.`);
        }
      }
      
      setCameraError(null);
      setFeedback("Live drill instructor activated. Strike a pose and click 'Capture & Analyze Frame'.");

    } catch (err) {
      console.error("Error setting up video playback:", err);
      stream.getTracks().forEach(track => track.stop()); // Clean up failed stream
      setCameraError(err.message || err.name);
      setFeedback(`Video Playback Error: ${err.message}. Please restart the Live Drill.`);
      setIsLiveMode(false);
    }
  };

  // 4. Stop the live stream
  const stopLiveStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
        videoRef.current.srcObject = null; // Detach stream from video element
        videoRef.current.load();
    }
    setIsLiveMode(false);
    setFeedback("Live stream stopped. Select a mode to continue.");
    setImageSource(null); 
    setCameraError(null);
  };
  
  // 5. Request permissions on initial load
  useEffect(() => {
    requestMediaPermissions(); 
    return () => stopLiveStream(); // Cleanup on unmount
  }, []);

  // --- LIVE FRAME ANALYZER ---
  const handleLiveAnalyze = async () => {
    if (!isLiveMode || selectedCheckpoints.length === 0) return alert('Start live stream and select a drill.');
    if (loading) return;
    
    setLoading(true);
    setProgress(1); 
    setFeedback('Capturing and analyzing live frame...');

    const videoElement = videoRef.current;
    
    // Check videoElement.readyState (3 = enough data for playback)
    if (!videoElement || videoElement.readyState < 3) { 
        setLoading(false);
        setFeedback('Webcam stream is not ready. ReadyState: ' + (videoElement ? videoElement.readyState : 'N/A'));
        return;
    }
    
    const canvas = document.createElement('canvas');
    canvas.width = videoElement.videoWidth || 640; 
    canvas.height = videoElement.videoHeight || 480; 
    const ctx = canvas.getContext('2d');
    
    try {
        // Draw image from video to canvas
        ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
    } catch (e) {
        console.error("CORS Error on drawImage:", e);
        setLoading(false);
        setFeedback("Error: Cannot capture frame. This can be caused by a cross-origin (CORS) issue with virtual cameras. Try using a standard USB webcam if possible.");
        return;
    }


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

  // --- VIDEO UPLOAD/ANALYSIS FUNCTIONS ---
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

  // --- JSX RENDER ---
  return (
    <div className="app-container">
      {/* 🚨 NEW: Inline <style> tag for a professional white theme */}
      <style>
        {`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;900&display=swap');
        
        :root {
          --ncc-red: #ef4444;
          --ncc-sky: #38bdf8;
          --ncc-blue: #2563eb;
          --bg-light: #f3f4f6;
          --bg-white: #ffffff;
          --text-dark: #111827;
          --text-light: #4b5563;
          --border-color: #d1d5db;
        }

        body {
          font-family: 'Inter', sans-serif;
          background-color: var(--bg-light);
          color: var(--text-dark);
          margin: 0;
        }

        .app-container {
          min-height: 100vh;
        }

        /* --- Header --- */
        .app-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 1rem 2rem;
          background-color: var(--bg-white);
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.07);
          border-bottom: 1px solid var(--border-color);
        }
        .header-logo {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .logo-emoji {
          font-size: 2rem;
        }
        .ncc-text {
          font-size: 1.25rem;
          font-weight: 700;
          display: flex;
          gap: 0.25rem;
        }
        .ncc-red { color: var(--ncc-red); }
        .ncc-sky { color: var(--ncc-sky); }
        .ncc-blue { color: var(--ncc-blue); }

        .header-title {
          font-size: 1.75rem;
          font-weight: 900;
          color: var(--text-dark);
        }
        
        .header-line {
          height: 4px;
          background: linear-gradient(90deg, var(--ncc-red) 33%, var(--ncc-sky) 33%, var(--ncc-sky) 66%, var(--ncc-blue) 66%);
        }
        
        .main-content {
          max-width: 1280px;
          margin: 2rem auto;
          padding: 0 1rem;
        }

        .centered {
          text-align: center;
        }
        
        .section-title {
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--text-dark);
          margin-bottom: 1.5rem;
          text-align: center;
        }

        /* --- Mode & Input --- */
        .input-analysis-container {
          max-width: 800px;
          margin: 2rem auto;
          padding: 2rem;
          background-color: var(--bg-white);
          border-radius: 12px;
          box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.07);
          border: 1px solid var(--border-color);
        }
        
        .mode-selection {
          display: flex;
          justify-content: center;
          margin-bottom: 1.5rem;
        }
        .mode-button {
          padding: 0.75rem 1.5rem;
          margin: 0 0.5rem;
          font-weight: 500;
          font-size: 0.9rem;
          border-radius: 9999px;
          transition: all 0.2s ease-in-out;
          border: 2px solid var(--ncc-blue);
          background-color: var(--bg-white);
          color: var(--ncc-blue);
          cursor: pointer;
        }
        .mode-button.active, .mode-button:hover {
          background-color: var(--ncc-blue);
          color: white;
          transform: translateY(-2px);
          box-shadow: 0 4px 10px rgba(37, 99, 235, 0.3);
        }
        
        .analyze-section button, .live-section button {
          width: 100%;
          padding: 0.75rem 1.5rem;
          margin-top: 1rem;
          font-weight: 700;
          font-size: 1rem;
          border-radius: 8px;
          background-color: var(--ncc-blue);
          color: white;
          transition: all 0.2s;
          cursor: pointer;
          border: none;
        }
        .analyze-section button:hover, .live-section button:hover {
          background-color: #1d4ed8;
          box-shadow: 0 4px 10px rgba(37, 99, 235, 0.2);
        }
        .analyze-section button:disabled, .live-section button:disabled {
          background-color: #9ca3af;
          cursor: not-allowed;
        }
        
        .analyze-section input[type="file"], .live-section input[type="text"] {
          display: block;
          width: 100%;
          padding: 0.75rem;
          border: 1px solid var(--border-color);
          border-radius: 8px;
          background-color: #f9fafb;
          color: var(--text-dark);
          box-sizing: border-box; /* Fix width issue */
        }
        .live-section input[type="text"] {
          text-align: center;
          font-size: 0.9rem;
        }

        .hint {
          color: var(--text-light);
          font-size: 0.875rem;
          margin-top: 0.75rem;
          text-align: center;
          /* Allow wrapping for long device lists */
          white-space: pre-wrap;
          word-break: break-all;
        }
        
        /* --- Checkboxes --- */
        .checkbox-grid {
          display: flex;
          justify-content: center;
          flex-wrap: wrap;
          gap: 1rem;
          margin: 2.5rem auto;
          max-width: 900px;
        }
        .checkbox-label {
          background-color: var(--bg-white);
          padding: 0.75rem 1.5rem;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s;
          border: 1px solid var(--border-color);
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
          color: var(--text-light);
          font-weight: 500;
        }
        .checkbox-label:has(input:checked) {
          background-color: #d1fae5; /* Light green */
          border-color: #10b981;
          color: #065f46;
          font-weight: 700;
          box-shadow: 0 2px 4px rgba(16, 185, 129, 0.2);
        }
        .checkbox-label input {
          margin-right: 0.5rem;
        }

        /* --- Results --- */
        .results-section {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
          gap: 2rem;
          margin: 2.5rem auto;
        }
        .visual-feedback, .analysis-report {
          padding: 1.5rem;
          background-color: var(--bg-white);
          border-radius: 12px;
          box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.07);
          border: 1px solid var(--border-color);
        }
        .visual-feedback img {
          width: 100%;
          height: auto;
          border-radius: 8px;
          margin-top: 1rem;
          border: 1px solid var(--border-color);
        }
        .analysis-report pre {
          background-color: #0f172a; /* Dark blue */
          color: #e2e8f0;
          padding: 1.5rem;
          border-radius: 8px;
          white-space: pre-wrap; /* Wrap long lines */
          word-break: break-all;
          font-family: 'Courier New', Courier, monospace;
          font-size: 0.9rem;
          line-height: 1.6;
        }
        .analysis-report button {
          padding: 0.6rem 1.2rem;
          margin-top: 1rem;
          font-weight: 700;
          border-radius: 8px;
          background-color: var(--ncc-blue);
          color: white;
          transition: all 0.2s;
          cursor: pointer;
          border: none;
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .analysis-report button:disabled {
          background-color: #9ca3af;
          cursor: not-allowed;
        }

        /* --- Footer --- */
        .app-footer {
          text-align: center;
          padding: 2rem;
          color: var(--text-light);
          font-size: 0.875rem;
          margin-top: 2rem;
        }
        
        /* --- Loading Overlay --- */
        .loading-overlay {
          position: fixed;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background: rgba(255, 255, 255, 0.8);
          backdrop-filter: blur(4px);
          display: flex;
          justify-content: center;
          align-items: center;
          z-index: 100;
        }
        .loading-box {
          background: var(--bg-white);
          padding: 2.5rem;
          border-radius: 12px;
          text-align: center;
          box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
          color: var(--text-dark);
        }
        .progress-bar {
          width: 300px;
          height: 20px;
          background-color: var(--bg-light);
          border-radius: 10px;
          margin-top: 1rem;
          overflow: hidden;
        }
        .progress-fill {
          height: 100%;
          background-color: var(--ncc-blue);
          transition: width 0.3s;
        }
        `}
      </style>

      {/* 🚨 Removed Background Canvas */}
      
      {/* Header */}
      <header className="app-header">
        <div className="header-logo">
          <span className="logo-emoji">🇮🇳</span> 
          <span className="ncc-text">
            <span className="ncc-red">NCC </span>
            <span className="ncc-sky">CADET </span>
            <span className="ncc-blue">CORPS</span>
          </span>
        </div>
        <h1 className="header-title">NCC DRILL ANALYZER</h1>
        <div className="header-logo">
          <span className="logo-emoji">🤝</span>
        </div>
      </header>
      <div className="header-line"></div>
      
      <main className="main-content">
        <div className="input-analysis-container">
          <h2 className="section-title" style={{ marginTop: 0 }}>Select Analysis Mode</h2>
          <div className="mode-selection">
              <button 
                  className={`mode-button ${!isLiveMode ? 'active' : ''}`}
                  onClick={stopLiveStream} // Stop live stream if Upload is clicked
              >
                  Upload Video
              </button>
              <button 
                  className={`mode-button ${isLiveMode ? 'active' : ''}`}
                  // Toggle start/stop
                  onClick={isLiveMode ? stopLiveStream : startLiveStream} 
              >
                  {isLiveMode ? 'Stop Live Drill' : 'Start Live Drill'}
              </button>
          </div>
          
          <hr style={{border: 0, borderTop: '1px solid var(--border-color)', margin: '1.5rem 0'}} />

          {/* Conditional Input based on mode */}
          {!isLiveMode ? (
              // Upload Mode
              <div className="analyze-section">
                  <input type="file" accept="video/mp4,video/avi" onChange={handleFileChange} disabled={loading} />
                  <button onClick={handleAnalyze} disabled={loading || !file || selectedCheckpoints.length === 0}>
                      Analyze Uploaded Video
                  </button>
                  <p className="hint">{file ? `Video Selected: ${file.name}` : 'No Video Selected'}</p>
              </div>
          ) : (
              // Live Mode (Local/Virtual Webcam)
              <div className="live-section">
                  {/* Webcam Feed */}
                  <video 
                    ref={videoRef} 
                    autoPlay 
                    playsInline 
                    muted 
                    style={{ 
                      width: '100%', 
                      maxWidth: '600px', 
                      borderRadius: '8px', 
                      border: '1px solid var(--border-color)', 
                      backgroundColor: '#e5e7eb', // Light gray background
                      aspectRatio: '16 / 9',
                      marginTop: '1rem'
                    }}
                    onError={(e) => { 
                        console.error("Video element error:", e); 
                        setCameraError("Failed to load video stream."); 
                        stopLiveStream(); 
                    }}
                  ></video>
                  
                  <button onClick={handleLiveAnalyze} disabled={loading || selectedCheckpoints.length === 0 || !isLiveMode}>
                      Capture & Analyze Frame
                  </button>
                  <p className="hint">
                      {/* Display enumerated devices for debugging */}
                      {availableDevices.length > 0 && availableDevices.map(d => d.kind === 'videoinput' && d.label ? `[Found: ${d.label}] ` : '').join('')}
                      {cameraError ? `Camera Setup Error: ${cameraError}` : "Perform drill and click Capture."}
                  </p>
              </div>
          )}
        </div>
        
        <h2 className="section-title">Choose Command to be Analyzed</h2>
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
            <h2 className="section-title" style={{ margin: 0, textAlign: 'left' }}>Visual Feedback:</h2>
            {imageSource ? 
              <img src={imageSource} alt="Annotated Drill" /> : 
              <p style={{ marginTop: '1rem', color: 'var(--text-light)' }}>No image generated.</p>
            }
          </div>
          <div className="analysis-report">
            <h2 className="section-title" style={{ margin: 0, textAlign: 'left' }}>Analysis Report:</h2>
            <pre>{feedback}</pre>
            {feedback && feedback.startsWith('JAI HIND') && ( // Only show button if analysis was successful
              <button
                onClick={() => playVoiceReport(feedback)}
                disabled={voiceLoading}
              >
                🔊 {voiceLoading ? 'Generating Voice...' : 'Play Voice Report'}
              </button>
            )}
          </div>
        </div>
      </main>

      <footer className="app-footer">
        © 2025 NCC - CTUNIVERSITY. All Rights Reserved.
      </footer>
    </div>
  );
}

export default App;

