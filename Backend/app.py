import base64
import json
import os
import uuid
import io 
import numpy as np 
import cv2 
import boto3 
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import traceback # Added for better error reporting

# --- CRITICAL IMPORTING FIX ---
try:
    # 🚨 Importing both video (old) and frame (new) analysis functions
    from src.drills.salute_analysis import analyze_salute, analyze_salute_frame 
    from src.drills.high_leg_march import analyze_high_leg_march, analyze_high_leg_frame
    from src.drills.turns_analysis import analyze_turn_right, analyze_turn_left, analyze_turn_right_frame, analyze_turn_left_frame
except ImportError as e:
    print(f"CRITICAL IMPORT ERROR: {e}. Ensure files are in src/drills/ and function names match.")
    print("Please ensure you have updated the drill modules with the Lazy Initialization fix.")
    
    # Define placeholder functions to prevent immediate crash if imports fail
    def fallback_analysis(*args, **kwargs): return {"feedback": f"Error: Drill module function not found ({str(e)}).", "image_b64_array": []}
    analyze_high_leg_march = analyze_high_leg_frame = fallback_analysis
    analyze_salute = analyze_salute_frame = fallback_analysis
    analyze_turn_right = analyze_turn_left = analyze_turn_right_frame = analyze_turn_left_frame = fallback_analysis


# --- AWS CONFIGURATION ---
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.environ.get('AWS_REGION', 'ap-south-1') 
POLLY_VOICE_ID = 'Matthew' 

polly_client = None
try:
    # Initialize client, Boto3 will handle credential finding
    polly_client = boto3.client(
        'polly', 
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )
except Exception as e:
    print(f"ERROR: Could not initialize AWS Polly client. Voice report will fail. Details: {e}")
    polly_client = None


# --- CONFIGURATION ---
app = Flask(__name__)
CORS(app) 
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Mapping for VIDEO analysis (full video file)
DRILL_FUNCTION_MAP_VIDEO = {
    'high_leg_march': analyze_high_leg_march,
    'salute': analyze_salute,
    'turn_right': analyze_turn_right,
    'turn_left': analyze_turn_left,
}

# Mapping for LIVE FRAME analysis (single OpenCV frame)
DRILL_FUNCTION_MAP_FRAME = {
    'high_leg_march': analyze_high_leg_frame, 
    'salute': analyze_salute_frame, 
    # Turns use the FRAME map, but the helper function executes their video logic
    'turn_right': analyze_turn_right, 
    'turn_left': analyze_turn_left,
}

# --- VOICE GENERATION ---
def create_excited_ssml(text):
    """Wraps text in SSML tags for an energetic tone."""
    ssml_content = f"""
    <speak>
        <prosody rate="fast" volume="x-loud">
            JAI HIND! 
            <break time="500ms"/>
            {text}
        </prosody>
    </speak>
    """
    return ' '.join(ssml_content.split())


@app.route('/generate_polly_voice', methods=['POST'])
def generate_polly_voice():
    """Uses Amazon Polly to synthesize speech."""
    if not polly_client:
        return jsonify({"error": "Amazon Polly client not initialized. Check AWS credentials."}), 500
    try:
        data = request.get_json()
        report_text = data.get('report_text', 'No analysis report provided.')
        ssml_text = create_excited_ssml(report_text)
        response = polly_client.synthesize_speech(
            Text=ssml_text,
            OutputFormat='mp3',
            VoiceId=POLLY_VOICE_ID,
            TextType='ssml', 
            Engine='neural' 
        )
        if "AudioStream" in response:
            audio_stream = response["AudioStream"].read()
            audio_data_io = io.BytesIO(audio_stream)
            audio_data_io.seek(0)
            return send_file(audio_data_io, mimetype='audio/mp3', as_attachment=False)
        else:
            return jsonify({"error": "Polly failed to return an audio stream."}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Failed to synthesize speech: {type(e).__name__}: {str(e)}"}), 500


# --- SHARED ANALYSIS HELPER FUNCTION ---
def execute_analysis(analysis_map, drill_types, input_data):
    """
    Helper to execute analysis, handling both video path and single frame input.
    """
    all_results = []

    for drill_key in drill_types:
        if drill_key in analysis_map:
            analysis_function = analysis_map[drill_key]
            
            temp_path = None
            
            # 1. Handle Turn Commands (Temporal movements) in Live Mode
            if drill_key in ['turn_right', 'turn_left'] and 'frame' in input_data:
                # Need to write a very short temporary video using the single frame
                frame = input_data['frame']
                h, w, _ = frame.shape
                temp_path = os.path.join(UPLOAD_FOLDER, str(uuid.uuid4()) + "_temp.avi")
                out = cv2.VideoWriter(temp_path, cv2.VideoWriter_fourcc(*'MJPG'), 5, (w, h))
                for _ in range(5): 
                     out.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)) # BGR for writer
                out.release()
                analysis_output = analysis_function(temp_path, UPLOAD_FOLDER)
                os.remove(temp_path)
            
            # 2. Handle Video Upload Mode
            elif 'video_path' in input_data:
                 analysis_output = analysis_function(input_data['video_path'], UPLOAD_FOLDER)
            
            # 3. Handle Live Frame Mode (High Leg/Salute - new fast functions)
            elif 'frame' in input_data:
                 analysis_output = analysis_function(input_data['frame'], UPLOAD_FOLDER)
                 
            else:
                 analysis_output = {"feedback": "Error: Invalid analysis input structure.", "image_b64_array": []}

            all_results.append({
                "drill_key": drill_key,
                "feedback": analysis_output.get("feedback", "No text report generated."),
                "image_b64_array": analysis_output.get("image_b64_array", [])
            })

        else:
            all_results.append({
                "drill_key": drill_key,
                "feedback": f"Error: Analysis function for '{drill_key}' not found."
            })

    # Compile final report
    final_text_report = "JAI HIND, I AM YOUR DRILL INSTRUCTOR \n\n"
    final_image_b64 = None

    for result in all_results:
        final_text_report += f"\n--- {result['drill_key'].upper().replace('_', ' ')} ANALYSIS ---\n{result['feedback']}\n-----------------------------------------------------------\n"
        if final_image_b64 is None and result['image_b64_array']:
            final_image_b64 = result['image_b64_array'][0] 
            
    return final_text_report, final_image_b64


# --- ROUTE 1: VIDEO UPLOAD (Existing) ---
@app.route('/upload_and_analyze', methods=['POST'])
def upload_file():
    """Handles video upload."""
    if 'video' not in request.files or 'drill_types' not in request.form:
        return jsonify({"error": "Missing video file or drill checkpoint selection."}), 400
    
    file = request.files['video']
    drill_types_json = request.form['drill_types']
    filepath = None
    
    try:
        selected_drills = json.loads(drill_types_json)
        file_extension = os.path.splitext(file.filename)[-1]
        unique_filename = str(uuid.uuid4()) + file_extension
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(filepath)
        
        final_text_report, final_image_b64 = execute_analysis(
            DRILL_FUNCTION_MAP_VIDEO, 
            selected_drills, 
            {'video_path': filepath}
        )

        if os.path.exists(filepath):
            os.remove(filepath)

        return jsonify({
            "success": True,
            "feedback": final_text_report,
            "annotated_image_b64": final_image_b64 
        }), 200

    except Exception as e:
        traceback.print_exc()
        error_message = f"Video Analysis failed: {type(e).__name__}: {str(e)}"
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"success": False, "error": error_message}), 500

# --- ROUTE 2: LIVE FRAME ANALYSIS (New) ---
@app.route('/analyze_live_frame', methods=['POST'])
def analyze_live_frame():
    """Handles a single image frame upload from the webcam."""
    if 'frame' not in request.files or 'drill_types' not in request.form:
        return jsonify({"error": "Missing frame file or drill checkpoint selection."}), 400
    
    frame_file = request.files['frame']
    drill_types_json = request.form['drill_types']
    
    try:
        selected_drills = json.loads(drill_types_json)

        # 1. Decode image frame into an OpenCV NumPy array
        in_memory_file = io.BytesIO(frame_file.read())
        in_memory_file.seek(0)
        file_bytes = np.asarray(bytearray(in_memory_file.read()), dtype=np.uint8)
        frame_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

        if frame_bgr is None:
            return jsonify({"error": "Could not decode image frame."}), 500
        
        # Convert BGR (OpenCV) to RGB (MediaPipe) for analysis
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        # 2. Execute analysis using the Frame Map
        final_text_report, final_image_b64 = execute_analysis(
            DRILL_FUNCTION_MAP_FRAME, 
            selected_drills, 
            {'frame': frame_rgb} 
        )

        # 3. Return the final structured response
        return jsonify({
            "success": True,
            "feedback": final_text_report,
            "annotated_image_b64": final_image_b64 
        }), 200

    except Exception as e:
        traceback.print_exc()
        error_message = f"Live Analysis failed: {type(e).__name__}: {str(e)}"
        return jsonify({"success": False, "error": error_message}), 500

if __name__ == '__main__':
    print(f"NCC Drill Analyzer Backend running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
