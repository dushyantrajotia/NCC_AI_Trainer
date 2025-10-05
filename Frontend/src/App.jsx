import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import nccLogo from './assets/ncc_logo.png';
import nccUnity from './assets/ncc_unity.png';

const DRILL_CHECKPOINTS = [
  { value: 'high_leg_march', label: 'High Leg March (Attention)' },
  { value: 'salute', label: 'NCC Salute' },
  { value: 'turn_right', label: 'Right Turn (Dahine Mur)' },
  { value: 'turn_left', label: 'Left Turn (Baen Mur)' },
];

function App() {
  const [file, setFile] = useState(null);
  const [selectedCheckpoints, setSelectedCheckpoints] = useState([]);
  const [feedback, setFeedback] = useState('Select one or more drills and upload a video.');
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [imageSource, setImageSource] = useState(null);

  const playVoiceReport = (text) => {
    if ('speechSynthesis' in window) {
      // Remove symbols/emojis and extra non-alphanumeric characters
      const cleanText = text.replace(/[^a-zA-Z0-9.,;!?()\s]/g, '');
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.rate = 1;   // normal speed
      utterance.pitch = 1;  // normal pitch
      window.speechSynthesis.speak(utterance);
    }
  };

  const resultsRef = useRef(null);

  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    // Ensure canvas fills the window
    function resizeCanvas() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resizeCanvas();

    const particles = [];
    const numParticles = 60;

    class Particle {
      constructor() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.size = Math.random() * 3 + 1;
        this.speedX = Math.random() * 1 - 0.5;
        this.speedY = Math.random() * 1 - 0.5;
        this.color = `rgba(255, 255, 255, ${Math.random() * 0.5 + 0.3})`;
      }
      update() {
        this.x += this.speedX;
        this.y += this.speedY;
        if (this.x > canvas.width) this.x = 0;
        if (this.x < 0) this.x = canvas.width;
        if (this.y > canvas.height) this.y = 0;
        if (this.y < 0) this.y = canvas.height;
      }
      draw() {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fillStyle = this.color;
        ctx.fill();
      }
    }

    for (let i = 0; i < numParticles; i++) {
      particles.push(new Particle());
    }

    let animationFrameId;

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach(p => {
        p.update();
        p.draw();
      });
      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    window.addEventListener('resize', resizeCanvas);
    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);


  const handleFileChange = (e) => {
    const uploadedFile = e.target.files[0];
    setFile(uploadedFile || null);
    setFeedback(uploadedFile ? `Selected: ${uploadedFile.name}` : 'Select one or more drills and upload a video.');
  };

  const handleCheckpointChange = (e) => {
    const { value, checked } = e.target;
    setSelectedCheckpoints(prev =>
      checked ? [...prev, value] : prev.filter(v => v !== value)
    );
  };

  const getDrillLabels = () => selectedCheckpoints.map(val => DRILL_CHECKPOINTS.find(d => d.value === val)?.label).join(', ');

  const simulateProgress = () => {
    setProgress(0);
    const interval = setInterval(() => {
      setProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          return 100;
        }
        return prev + Math.floor(Math.random() * 5 + 1); // increment 1-5%
      });
    }, 300);
  };

  const handleAnalyze = async () => {
    if (!file) return alert('Please upload a video.');
    if (selectedCheckpoints.length === 0) return alert('Select at least one drill.');

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
      setTimeout(() => setLoading(false), 500); // small delay for smooth transition

      if (response.ok && data.success) {
        setFeedback(data.feedback);
        setImageSource(data.annotated_image_b64 || null);
        resultsRef.current.scrollIntoView({ behavior: 'smooth' });
        playVoiceReport(data.feedback)
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

  return (
    <div className="app-container">
      {/* Background Canvas */}
      <canvas id="bg-canvas"ref={canvasRef} style={{position: 'fixed',top: 0,left: 0,width: '100%',height: '100%',zIndex: -1}}></canvas>

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

      {/* Analyze Section */}
      <div className="analyze-section">
        <input type="file" accept="video/mp4,video/avi" onChange={handleFileChange} />
        <button onClick={handleAnalyze} disabled={loading || !file || selectedCheckpoints.length === 0}>Analyze</button>
      </div>

      <br></br>

      <h2 className="centered">Choose command to be analyzed : </h2>

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
            <p>Analyzing: {Math.min(progress, 100)}%</p>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${Math.min(progress, 100)}%` }}></div>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      <div ref={resultsRef} className="results-section">
        <div className="visual-feedback">
          <h2 className="centered">Visual Feedback:</h2>
          {imageSource ? <img src={imageSource} alt="Annotated Drill" /> : <p>No image generated.</p>}
        </div>
        <div className="analysis-report">
          <h2 className="centered">Analysis Report:</h2>
          <pre>{feedback}</pre>
          {feedback && (
            <button
              onClick={() => playVoiceReport(feedback)}
              style={{
                marginTop: '15px',
                padding: '10px 20px',
                backgroundColor: '#0D47A1',
                color: 'white',
                fontWeight: 'bold',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer'
              }}
            >
              🔊 Play Voice Report
            </button>
          )}
        </div>
      </div>

      <br></br>
      <br></br>
      <footer className="app-footer centered">© 2025 NCC - CTUNIVERSITY. All Rights Reserved.</footer>
    </div>
  );
}

export default App;
