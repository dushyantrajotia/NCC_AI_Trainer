import base64
import json
import os
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- IMPORTING ALL DRILL FUNCTIONS ---
# Ensure these files exist in src/drills/
try:
    from src.drills.salute_analysis import analyze_salute
    from src.drills.high_leg_march import analyze_high_leg_march
    from src.drills.turns_analysis import analyze_turn_right, analyze_turn_left, analyze_turn_about 
except ImportError as e:
    print(f"CRITICAL IMPORT ERROR: {e}. Ensure all files and __init__.py are in src/drills/.")
    raise

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
        
        final_text_report = f"===========================================================\nNCC MULTI-DRILL ANALYSIS START ({len(selected_drills)} checks)\n===========================================================\n"
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
