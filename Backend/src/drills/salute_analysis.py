import cv2
import mediapipe as mp
import sys
import math
import os
import uuid
import base64
import numpy as np

# --- IMPORT FIX ---
try:
    # Attempt relative import first
    from .pose_utils import calculate_angle 
except ImportError:
    try:
        # Fallback for direct execution/testing
        from src.pose_utils import calculate_angle 
    except ImportError:
        print("FATAL ERROR: Could not import calculate_angle from pose_utils.py.")
        sys.exit(1)

# Initialize MediaPipe components (but NOT the heavy model yet)
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

# 🚨 CRITICAL FIX: LAZY INITIALIZATION
# The 'pose' object is now a placeholder and will be initialized only when needed.
pose = None 

# --- DEFINED CONSTANTS (Tolerances for Drill Accuracy) ---
FINGER_Y_ALIGNMENT_TOLERANCE = 0.08 # Increased from 0.04
FINGER_X_ALIGNMENT_TOLERANCE = 0.12 # Increased from 0.06 
WRIST_RIGIDITY_MIN_ANGLE = 160 
ELBOW_RAISE_ANGLE_RANGE = (160, 180) # Upper arm and forearm should be nearly straight/rigid

# 🚨 MODIFIED: Head Stability Thresholds (Loosened for real-world use)
HEAD_STABILITY_VERY_GOOD_THRESHOLD = 0.02 # Increased from 0.01
HEAD_STABILITY_MODERATE_THRESHOLD = 0.05 # Increased from 0.03

# --- LAZY INITIALIZATION HELPER FUNCTION ---
def _get_pose_model():
    """Initializes and returns the MediaPipe Pose model instance."""
    global pose
    if pose is None:
        print("INFO: Lazily initializing MediaPipe Pose model for Salute analysis...")
        # Initialize with your desired confidence values
        pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
    return pose

# --- DRAWING UTILITY FUNCTION (Shared) ---
def draw_and_annotate(image, landmarks, fail_points, drill_name):
    """Draws landmarks and highlights failure points."""
    h, w, _ = image.shape
    
    # Draw all standard MediaPipe connections (green)
    mp_drawing.draw_landmarks(
        image, 
        landmarks, 
        mp_pose.POSE_CONNECTIONS,
        mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
        mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2)
    )

    # Convert image to BGR for OpenCV drawing 
    annotated_image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    
    fail_message = ""
    RED = (0, 0, 255) 
    GREEN = (0, 255, 0)
    WHITE = (255, 255, 255)

    # Check for valid landmarks before drawing
    if not landmarks or not landmarks.landmark:
        return annotated_image

    # Highlight specific fail points
    if 'FINGER_POS' in fail_points:
        R_INDEX = mp_pose.PoseLandmark.RIGHT_INDEX.value
        R_EYE_OUTER = mp_pose.PoseLandmark.RIGHT_EYE_OUTER.value
        R_EAR = mp_pose.PoseLandmark.RIGHT_EAR.value
        
        if R_INDEX < len(landmarks.landmark) and R_EYE_OUTER < len(landmarks.landmark) and R_EAR < len(landmarks.landmark):
            cv2.circle(annotated_image, (int(landmarks.landmark[R_INDEX].x * w), int(landmarks.landmark[R_INDEX].y * h)), 10, RED, -1)
            target_x = int(((landmarks.landmark[R_EYE_OUTER].x + landmarks.landmark[R_EAR].x) / 2) * w)
            target_y = int(landmarks.landmark[R_EYE_OUTER].y * h)
            # Draw a larger green target zone to reflect new tolerance
            cv2.circle(annotated_image, (target_x, target_y), int(FINGER_X_ALIGNMENT_TOLERANCE * w / 2), GREEN, 2)
            fail_message += "Placement Fail "
        
    if 'HAND_FORM' in fail_points:
        R_WRIST = mp_pose.PoseLandmark.RIGHT_WRIST.value
        R_INDEX = mp_pose.PoseLandmark.RIGHT_INDEX.value
        R_ELBOW = mp_pose.PoseLandmark.RIGHT_ELBOW.value
        
        if R_WRIST < len(landmarks.landmark) and R_INDEX < len(landmarks.landmark) and R_ELBOW < len(landmarks.landmark):
            # Highlight wrist segment in RED
            cv2.line(annotated_image, (int(landmarks.landmark[R_ELBOW].x * w), int(landmarks.landmark[R_ELBOW].y * h)), 
                     (int(landmarks.landmark[R_WRIST].x * w), int(landmarks.landmark[R_WRIST].y * h)), RED, 5) 
            cv2.line(annotated_image, (int(landmarks.landmark[R_WRIST].x * w), int(landmarks.landmark[R_WRIST].y * h)), 
                     (int(landmarks.landmark[R_INDEX].x * w), int(landmarks.landmark[R_INDEX].y * h)), RED, 5) 
            fail_message += "Hand Rigidity Fail "

    if 'ELBOW_RAISE' in fail_points:
        R_SHOULDER = mp_pose.PoseLandmark.RIGHT_SHOULDER.value
        R_ELBOW = mp_pose.PoseLandmark.RIGHT_ELBOW.value
        
        if R_SHOULDER < len(landmarks.landmark) and R_ELBOW < len(landmarks.landmark):
            cv2.line(annotated_image, (int(landmarks.landmark[R_SHOULDER].x * w), int(landmarks.landmark[R_SHOULDER].y * h)), 
                     (int(landmarks.landmark[R_ELBOW].x * w), int(landmarks.landmark[R_ELBOW].y * h)), RED, 5) 
            fail_message += "Elbow Angle Fail"
        
    cv2.putText(annotated_image, f"{drill_name}: {fail_message}", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, WHITE, 2, cv2.LINE_AA)
    
    return annotated_image

# --- CORE LOGIC: ABSTRACTED POSTURE CHECK ---
def _get_salute_posture_feedback(landmarks, mp_pose_module):
    """Calculates posture compliance for a single frame."""
    if not landmarks or not landmarks.landmark:
        return None, None
        
    lm = landmarks.landmark
    
    # Define required landmarks
    R_EAR = mp_pose_module.PoseLandmark.RIGHT_EAR
    R_EYE_OUTER = mp_pose_module.PoseLandmark.RIGHT_EYE_OUTER
    R_SHOULDER = mp_pose_module.PoseLandmark.RIGHT_SHOULDER
    R_ELBOW = mp_pose_module.PoseLandmark.RIGHT_ELBOW
    R_WRIST = mp_pose_module.PoseLandmark.RIGHT_WRIST
    R_INDEX = mp_pose_module.PoseLandmark.RIGHT_INDEX
    R_NOSE = mp_pose_module.PoseLandmark.NOSE # 🚨 NEW: Added NOSE for stability check

    required_landmarks = [R_EAR, R_EYE_OUTER, R_SHOULDER, R_ELBOW, R_WRIST, R_INDEX, R_NOSE]
    
    # Check visibility
    for lmk_enum in required_landmarks:
        if lmk_enum.value >= len(lm) or lm[lmk_enum.value].visibility < 0.5:
            return None, ["Low Visibility"] # Fail if key points aren't visible

    # Landmark Extraction
    right_ear = (lm[R_EAR.value].x, lm[R_EAR.value].y)
    right_eye_outer = (lm[R_EYE_OUTER.value].x, lm[R_EYE_OUTER.value].y)
    r_shoulder = (lm[R_SHOULDER.value].x, lm[R_SHOULDER.value].y)
    r_elbow = (lm[R_ELBOW.value].x, lm[R_ELBOW.value].y)
    r_wrist = (lm[R_WRIST.value].x, lm[R_WRIST.value].y)
    r_index = (lm[R_INDEX.value].x, lm[R_INDEX.value].y)

    fail_points = []
    
    # 1. FINGER PLACEMENT CHECK (Uses updated, larger tolerances)
    target_y = right_eye_outer[1]
    target_x = (right_eye_outer[0] + right_ear[0]) / 2
    
    y_pos_deviation = abs(r_index[1] - target_y)
    x_pos_deviation = abs(r_index[0] - target_x)
    
    finger_placement_ok = (y_pos_deviation < FINGER_Y_ALIGNMENT_TOLERANCE and 
                           x_pos_deviation < FINGER_X_ALIGNMENT_TOLERANCE)
    if not finger_placement_ok: fail_points.append('FINGER_POS')

    # 2. HAND FORM CHECK (Wrist rigidity/straightness)
    wrist_rigidity_angle = calculate_angle(r_elbow, r_wrist, r_index)
    hand_form_ok = wrist_rigidity_angle >= WRIST_RIGIDITY_MIN_ANGLE
    if not hand_form_ok: fail_points.append('HAND_FORM')

    # 3. ARM RAISE/RIGIDITY CHECK (Elbow Angle)
    elbow_angle = calculate_angle(r_shoulder, r_elbow, r_wrist)
    elbow_raise_ok = (ELBOW_RAISE_ANGLE_RANGE[0] <= elbow_angle <= ELBOW_RAISE_ANGLE_RANGE[1])
    if not elbow_raise_ok: fail_points.append('ELBOW_RAISE')
    
    success_flags = {
        'finger_placement': finger_placement_ok,
        'hand_form': hand_form_ok,
        'elbow_raise': elbow_raise_ok,
    }
    
    return success_flags, fail_points


# --------------------------------------------------------------------------
# --- EXPORT 1: LIVE FRAME ANALYSIS (Fast) ---
# --------------------------------------------------------------------------
def analyze_salute_frame(frame_rgb, analysis_dir):
    """Analyzes a single RGB frame from the webcam (Live Mode)."""
    model = _get_pose_model() # Get/Initialize the model
    results = model.process(frame_rgb)
    
    if results.pose_landmarks:
        success_flags, fail_points = _get_salute_posture_feedback(results.pose_landmarks, mp_pose)
        
        if success_flags is None:
            feedback_text = f"Posture: **{'Low Visibility' if fail_points and 'Low Visibility' in fail_points else 'Standby/Relax'}**. Perform the salute to analyze."
            annotated_image = draw_and_annotate(frame_rgb.copy(), results.pose_landmarks, fail_points or [], "SALUTE (LIVE)")
            _, buffer = cv2.imencode('.jpg', annotated_image)
            image_b64_data = [f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"]
            return {"image_b64_array": image_b64_data, "feedback": feedback_text}
            
        # Annotate image
        annotated_image = draw_and_annotate(frame_rgb.copy(), results.pose_landmarks, fail_points, "SALUTE (LIVE)")
        
        # Encode to Base64
        _, buffer = cv2.imencode('.jpg', annotated_image)
        image_b64_data = [f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"]

        # 🚨 MODIFIED: Added note about stability check
        if not fail_points:
            feedback_text = "🌟 **Perfect Salute!** Hold the position. (Head stability analyzed in video mode)"
        else:
            feedback_text = f"❌ **Error!** Fix highlighted areas: {', '.join(fail_points).replace('_', ' ')}. (Head stability analyzed in video mode)"
        
        return {"image_b64_array": image_b64_data, "feedback": feedback_text}
        
    return {"image_b64_array": [], "feedback": "No cadet detected in the frame."}


# --------------------------------------------------------------------------
# --- EXPORT 2: VIDEO ANALYSIS (Comprehensive) ---
# --------------------------------------------------------------------------
def analyze_salute(video_path, analysis_dir):
    """Analyzes a full video for cumulative performance (Video Upload Mode)."""
    model = _get_pose_model() # Get/Initialize the model
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": "Video file not found or corrupted.", "feedback": "Error: Video file not found or corrupted."}

    # --- TRACKING FLAGS (Cumulative Success for the whole video) ---
    finger_placement_succeeded = False
    hand_form_succeeded = False
    elbow_raise_succeeded = False
    
    # 🚨 NEW: List to store head positions during the salute
    head_positions = []

    best_failure_frame_image = None
    best_success_frame_image = None
    last_known_landmarks = None
    min_failures_in_frame = float('inf')
    best_failure_points_for_frame = []
    found_valid_pose = False

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = model.process(image)
            
            if results.pose_landmarks:
                last_known_landmarks = results.pose_landmarks
                success_flags, current_frame_fail_points = _get_salute_posture_feedback(results.pose_landmarks, mp_pose)
                
                # Skip frames with low visibility
                if success_flags is None:
                    continue
                
                found_valid_pose = True
                
                # 🚨 NEW: Store head position if salute pose is active
                nose_lmk = results.pose_landmarks.landmark[mp_pose.PoseLandmark.NOSE.value]
                if nose_lmk.visibility > 0.5:
                    head_positions.append((nose_lmk.x, nose_lmk.y))

                # Update cumulative success tracking
                if success_flags['finger_placement']: finger_placement_succeeded = True
                if success_flags['hand_form']: hand_form_succeeded = True
                if success_flags['elbow_raise']: elbow_raise_succeeded = True
                
                num_failures = len(current_frame_fail_points)

                # Capture failure frame for visualization
                if num_failures > 0 and num_failures < min_failures_in_frame:
                    min_failures_in_frame = num_failures
                    best_failure_frame_image = image.copy()
                    best_failure_points_for_frame = current_frame_fail_points
                
                if num_failures == 0 and best_success_frame_image is None:
                    best_success_frame_image = image.copy()
            
    finally:
        cap.release()

    # --- Head Stability Calculation ---
    head_stability_feedback = "✅ Head Stability: Not enough data."
    if len(head_positions) > 10: # Require at least 10 frames of data
        x_coords = [pos[0] for pos in head_positions]
        y_coords = [pos[1] for pos in head_positions]
        std_dev_x = np.std(x_coords)
        std_dev_y = np.std(y_coords)
        total_deviation = std_dev_x + std_dev_y # Simple deviation metric

        if total_deviation <= HEAD_STABILITY_VERY_GOOD_THRESHOLD:
            head_stability_feedback = "✅ Head Stability: Properly stable (Very Good)."
        elif total_deviation <= HEAD_STABILITY_MODERATE_THRESHOLD:
            head_stability_feedback = "⚠️ Head Stability: Moderately stable (Keep improving)."
        else:
            head_stability_feedback = "❌ Head Stability: Moving too much (Kindly work on that)."
    elif found_valid_pose:
        head_stability_feedback = "✅ Head Stability: Pose held too briefly to measure."


    # --- Compile Final Report ---
    if not found_valid_pose:
        return {"image_b64_array": [], "feedback": "❌ Analysis Failed: No valid salute posture detected in the video."}
        
    final_fail_points = []
    if not finger_placement_succeeded: final_fail_points.append('FINGER_POS')
    if not hand_form_succeeded: final_fail_points.append('HAND_FORM')
    if not elbow_raise_succeeded: final_fail_points.append('ELBOW_RAISE')
    
    overall_correct = not final_fail_points
    
    # Determine which frame to show
    frame_to_use_for_annotation = None
    fail_points_for_annotation = []
    
    if overall_correct and best_success_frame_image is not None:
        frame_to_use_for_annotation = best_success_frame_image
        fail_points_for_annotation = []
    elif not overall_correct and best_failure_frame_image is not None:
        frame_to_use_for_annotation = best_failure_frame_image
        fail_points_for_annotation = best_failure_points_for_frame
    elif last_known_landmarks is not None and 'image' in locals(): # Fallback to last frame
        frame_to_use_for_annotation = image 
        fail_points_for_annotation = final_fail_points
    
    # Generate the text report
    feedback_lines = []
    if overall_correct:
         feedback_lines.append("🌟 **Outstanding Salute!** Your salute was performed correctly during the video.")
         feedback_lines.append("✅ OVERALL: PERFECT SALUTE POSTURE DETECTED.")
    else:
         failure_messages = [f"❌ {fail.replace('_', ' ')}" for fail in final_fail_points]
         feedback_lines.append(f"❌ **Action Required!** Areas: **{', '.join(failure_messages)}**.")
         feedback_lines.append("Please look at the annotated image for guidance.")

    feedback_lines.append("\n--- COMPONENT BREAKDOWN ---")
    feedback_lines.append(f"✅ Finger Placement: {'Achieved' if finger_placement_succeeded else '❌ FAIL - Index finger was off target.'}")
    feedback_lines.append(f"✅ Hand Form: {'Rigid' if hand_form_succeeded else '❌ FAIL - Lock your wrist and join fingers.'}")
    feedback_lines.append(f"✅ Arm Rigidity: {'Correct' if elbow_raise_succeeded else '❌ FAIL - Elbow was too bent.'}")
    feedback_lines.append(f"{head_stability_feedback}") # 🚨 NEW: Added stability feedback
         
    final_text_report = "\n".join(feedback_lines)
    
    image_b64_data = []
    if frame_to_use_for_annotation is not None and last_known_landmarks is not None:
        visual_image = draw_and_annotate(frame_to_use_for_annotation.copy(), last_known_landmarks, fail_points_for_annotation, "SALUTE (VIDEO)")
        _, buffer = cv2.imencode('.jpg', visual_image)
        image_b64_data = [f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"]


    return {"image_b64_array": image_b64_data, "feedback": final_text_report}

