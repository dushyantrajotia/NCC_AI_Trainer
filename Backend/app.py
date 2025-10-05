import base64
import json
import os
import uuid
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import boto3 # AWS SDK for Python
import io # Used for handling audio stream in memory

# --- IMPORTING ALL DRILL FUNCTIONS ---
# Ensure these files exist in src/drills/
try:
    from src.drills.salute_analysis import analyze_salute
    from src.drills.high_leg_march import analyze_high_leg_march
    from src.drills.turns_analysis import analyze_turn_right, analyze_turn_left, analyze_turn_about 
except ImportError as e:
    print(f"CRITICAL IMPORT ERROR: {e}. Ensure all files and __init__.py are in src/drills/.")
    # Note: We don't raise here so the TTS functionality can still be tested if drill analysis fails.

# --- AWS CONFIGURATION ---
# Attempt to read credentials and region from environment variables
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')

# boto3 automatically uses the AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_REGION environment variables.
AWS_REGION = os.environ.get('AWS_REGION', 'ap-south-1') 
POLLY_VOICE_ID = 'Matthew' # A standard, clear Neural voice for excited tone

# Initialize the Polly client outside the function for efficiency
polly_client = None
try:
    # ⚠️ Robust Initialization: Check if both keys are available 
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        print("INFO: Initializing AWS Polly client with explicit credentials from environment.")
        polly_client = boto3.client(
            'polly', 
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
    else:
        # Fallback to default Boto3 configuration if keys are not explicitly set
        print("INFO: AWS credentials not explicitly set in environment variables (Acess Key ID or Secret Key missing). Attempting default configuration.")
        polly_client = boto3.client('polly', region_name=AWS_REGION)

except Exception as e:
    print(f"ERROR: Could not initialize AWS Polly client: {type(e).__name__}: {str(e)}")
    polly_client = None


# --- CONFIGURATION ---
app = Flask(__name__)
CORS(app) # Enable communication with the React frontend
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Define the mapping between frontend checkpoint name and the backend function
DRILL_FUNCTION_MAP = {
    'high_leg_march': analyze_high_leg_march,
    'salute': analyze_salute,
    'turn_right': analyze_turn_right,
    'turn_left': analyze_turn_left,
    # 'about_turn': analyze_turn_about, # Uncomment this when ready
}

def create_excited_ssml(text):
    """Wraps text in SSML tags to simulate an excited/energetic tone using high rate."""
    # FIX: Removed the unsupported 'pitch' attribute for the Neural engine.
    # We set the rate to 'fast' or 'x-fast' to convey high energy/excitement.
    ssml_content = f"""
    <speak>
        <prosody rate="fast">
            JAI HIND! 
            <break time="500ms"/>
            {text}
        </prosody>
    </speak>
    """
    # Clean up excess whitespace and newline characters for SSML parsing
    return ' '.join(ssml_content.split())


@app.route('/generate_polly_voice', methods=['POST'])
def generate_polly_voice():
    """Receives text and uses Amazon Polly to synthesize speech with an energetic tone."""
    if not polly_client:
        return jsonify({"error": "Amazon Polly client not initialized. Check AWS credentials and region."}), 500

    try:
        data = request.get_json()
        report_text = data.get('report_text', 'No analysis report provided.')

        # 1. Convert the plain text report into expressive SSML
        ssml_text = create_excited_ssml(report_text)

        # 2. Call the Amazon Polly API
        response = polly_client.synthesize_speech(
            Text=ssml_text,
            OutputFormat='mp3',
            VoiceId=POLLY_VOICE_ID,
            TextType='ssml', # Crucial: tells Polly to parse the SSML tags
            Engine='neural' # Use the high-quality Neural engine
        )

        # 3. Read the audio stream from the response
        if "AudioStream" in response:
            audio_stream = response["AudioStream"].read()
            
            # 4. Use io.BytesIO to treat the audio data as an in-memory file
            audio_data_io = io.BytesIO(audio_stream)
            audio_data_io.seek(0)
            
            # Send the audio data back to the frontend
            return send_file(
                audio_data_io,
                mimetype='audio/mp3',
                as_attachment=False,
                download_name='voice_report.mp3'
            )
        else:
            return jsonify({"error": "Polly failed to return an audio stream."}), 500

    except Exception as e:
        # 🚨 DEBUGGING CHANGE: Print the full traceback to the terminal
        import traceback
        traceback.print_exc()
        
        # Log AWS-specific errors (e.g., Invalid SSML, throttling)
        print(f"AWS Polly Synthesis Error: {e}")
        return jsonify({"error": f"Failed to synthesize speech: {type(e).__name__}: {str(e)}"}), 500


@app.route('/upload_and_analyze', methods=['POST'])
def upload_file():
    """Handles video upload, multi-analysis dispatch, and returns annotated image + text report."""
    
    if 'video' not in request.files or 'drill_types' not in request.form:
        return jsonify({"error": "Missing video file or drill checkpoint selection."}), 400
    
    file = request.files['video']
    drill_types_json = request.form['drill_types']
    
    filepath = None
    all_results = []
    
    try:
        selected_drills = json.loads(drill_types_json)
        if not selected_drills:
             return jsonify({"error": "No drill checkpoints were selected for analysis."}), 400

        # 1. Save the incoming video file to a temporary location
        file_extension = os.path.splitext(file.filename)[-1]
        
        # 🚨 FIX: Use file.filename to generate a unique file path
        input_filename = file.filename
        unique_filename = str(uuid.uuid4()) + input_filename
        
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(filepath)
        
        # 2. Dispatch analysis for each selected drill
        for drill_key in selected_drills:
            if drill_key in DRILL_FUNCTION_MAP:
                analysis_function = DRILL_FUNCTION_MAP[drill_key]
                
                # Each function returns a dictionary: {"image_b64_array": [], "feedback": text_report}
                analysis_output = analysis_function(filepath, UPLOAD_FOLDER)
                
                # Append the result dictionary, including the key
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
        
        # 3. Compile final response (aggregating text and taking the first image)
        
        # --- START OF EDIT ---
        # Removed the line "YOUR NCC DRILL ANALYSIS STARTED WITH..."
        final_text_report = "JAI HIND, I AM YOUR DRILL INSTRUCTOR \n\n"
        # --- END OF EDIT ---
        final_image_b64 = None

        for result in all_results:
            final_text_report += f"\n--- {result['drill_key'].upper()} ANALYSIS ---\n{result['feedback']}\n-----------------------------------------------------------\n"
            
            # Use the first valid image found for the visual display
            if final_image_b64 is None and result['image_b64_array']:
                 final_image_b64 = result['image_b64_array'][0] 

        # 4. Clean up the original uploaded file
        if os.path.exists(filepath):
            os.remove(filepath)

        # 5. Return the final structured response
        return jsonify({
            "success": True,
            "feedback": final_text_report,
            "annotated_image_b64": final_image_b64 
        }), 200

    except Exception as e:
        # Global error handling
        error_message = f"Analysis failed due to a critical server error: {type(e).__name__}: {str(e)}"
        
        # Ensure cleanup of the original uploaded file
        if filepath and os.path.exists(filepath):
            os.remove(filepath)

        return jsonify({"success": False, "error": error_message}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
