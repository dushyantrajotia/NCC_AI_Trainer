from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import uuid
# 🚨 IMPORTANT: Import the correct function name
from src.video_upload import analyze_high_leg_march 

# --- CONFIGURATION ---
app = Flask(__name__)
# Enable CORS for frontend communication
CORS(app) 
# Directory to store uploaded videos temporarily
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/upload_and_analyze', methods=['POST'])
def upload_file():
    """Handles video upload, analysis, and temporary file path management."""
    
    if 'video' not in request.files:
        return jsonify({"error": "No file part in the request (Expected key: 'video')"}), 400
    
    file = request.files['video']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    filepath = None
    
    if file:
        # Generate a unique filename and secure the file path
        file_extension = os.path.splitext(file.filename)[-1]
        unique_filename = str(uuid.uuid4()) + file_extension
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        try:
            # 1. Save the incoming file temporarily
            file.save(filepath)
            
            # 2. Pass the DYNAMIC file path to the Python analysis function
            # This is where the user's video is analyzed.
            analysis_result_string = analyze_high_leg_march(filepath)
            
            # 3. Clean up the uploaded file
            if os.path.exists(filepath):
                os.remove(filepath)

            # 4. Return the result to the frontend
            return jsonify({"success": True, "feedback": analysis_result_string}), 200

        except Exception as e:
            # Handle any exceptions during processing or file saving
            error_message = f"Analysis failed due to a server error: {str(e)}"
            
            # Ensure file is removed even if an error occurred
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
                
            return jsonify({"success": False, "error": error_message}), 500

if __name__ == '__main__':
    # Run the Flask server on port 5000 (standard for local backend)
    app.run(debug=True, port=5000)