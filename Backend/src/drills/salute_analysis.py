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
    from .pose_utils import calculate_angle 
except ImportError:
    try:
        from src.pose_utils import calculate_angle 
    except ImportError:
        print("FATAL ERROR: Could not import calculate_angle from pose_utils.py.")
        sys.exit(1)

# Initialize MediaPipe components
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose
pose = None # 🚨 CRITICAL FIX: Lazy Initialization Placeholder

# --- DEFINED CONSTANTS (Tolerances for Drill Accuracy) ---
FINGER_Y_ALIGNMENT_TOLERANCE = 0.04 
FINGER_X_ALIGNMENT_TOLERANCE = 0.06 
WRIST_RIGIDITY_MIN_ANGLE = 160 
ELBOW_RAISE_ANGLE_RANGE = (160, 180) 

# --- LAZY INITIALIZATION HELPER FUNCTION ---
def _get_pose_model():
    """Initializes the heavy MediaPipe Pose model only if it hasn't been done yet."""
    global pose
    if pose is None:
        print("INFO: Lazily initializing MediaPipe Pose model for Salute analysis...")
        pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
    return pose

# --- DRAWING UTILITY FUNCTION (Shared) ---
def draw_and_annotate(image, landmarks, fail_points, drill_name):
    """Draws landmarks and highlights failure points."""
    h, w, _ = image.shape
    
    mp_drawing.draw_landmarks(
        image, landmarks, mp_pose.POSE_CONNECTIONS,
        mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
        mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2)
    )

    annotated_image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    fail_message = ""
    RED = (0, 0, 255) 
    GREEN = (0, 255, 0) 

    # Highlight specific fail points 
    if 'FINGER_POS' in fail_points:
        R_INDEX = mp_pose.PoseLandmark.RIGHT_INDEX.value
        R_EYE_OUTER = mp_pose.PoseLandmark.RIGHT_EYE_OUTER.value
        R_EAR = mp_pose.PoseLandmark.RIGHT_EAR.value
        
        cv2.circle(annotated_image, (int(landmarks.landmark[R_INDEX].x * w), int(landmarks.landmark[R_INDEX].y * h)), 10, RED, -1)
        target_x = int(((landmarks.landmark[R_EYE_OUTER].x + landmarks.landmark[R_EAR].x) / 2) * w)
        target_y = int(landmarks.landmark[R_EYE_OUTER].y * h)
        cv2.circle(annotated_image, (target_x, target_y), 10, GREEN, -1)
        fail_message += "Placement Fail "
        
    if 'HAND_FORM' in fail_points:
        R_WRIST = mp_pose.PoseLandmark.RIGHT_WRIST.value
        R_INDEX = mp_pose.PoseLandmark.RIGHT_INDEX.value
        R_ELBOW = mp_pose.PoseLandmark.RIGHT_ELBOW.value
        
        cv2.line(annotated_image, (int(landmarks.landmark[R_ELBOW].x * w), int(landmarks.landmark[R_ELBOW].y * h)), 
                 (int(landmarks.landmark[R_WRIST].x * w), int(landmarks.landmark[R_WRIST].y * h)), RED, 5) 
        cv2.line(annotated_image, (int(landmarks.landmark[R_WRIST].x * w), int(landmarks.landmark[R_WRIST].y * h)), 
                 (int(landmarks.landmark[R_INDEX].x * w), int(landmarks.landmark[R_INDEX].y * h)), RED, 5) 
        fail_message += "Hand Rigidity Fail "

    if 'ELBOW_RAISE' in fail_points:
        R_SHOULDER = mp_pose.PoseLandmark.RIGHT_SHOULDER.value
        R_ELBOW = mp_pose.PoseLandmark.RIGHT_ELBOW.value
        
        cv2.line(annotated_image, (int(landmarks.landmark[R_SHOULDER].x * w), int(landmarks.landmark[R_SHOULDER].y * h)), 
                 (int(landmarks.landmark[R_ELBOW].x * w), int(landmarks.landmark[R_ELBOW].y * h)), RED, 5) 
        fail_message += "Elbow Angle Fail"
        
    cv2.putText(annotated_image, f"{drill_name}: {fail_message}", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    
    return annotated_image

# --- CORE LOGIC: ABSTRACTED POSTURE CHECK ---
def _get_salute_posture_feedback(landmarks, mp_pose):
    """Calculates posture compliance for a single frame."""
    lm = landmarks.landmark
    
    right_ear = (lm[mp_pose.PoseLandmark.RIGHT_EAR].x, lm[mp_pose.PoseLandmark.RIGHT_EAR].y)
    right_eye_outer = (lm[mp_pose.PoseLandmark.RIGHT_EYE_OUTER].x, lm[mp_pose.PoseLandmark.RIGHT_EYE_OUTER].y)
    r_shoulder = (lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].x, lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].y)
    r_elbow = (lm[mp_pose.PoseLandmark.RIGHT_ELBOW].x, lm[mp_pose.PoseLandmark.RIGHT_ELBOW].y)
    r_wrist = (lm[mp_pose.PoseLandmark.RIGHT_WRIST].x, lm[mp_pose.PoseLandmark.RIGHT_WRIST].y)
    r_index = (lm[mp_pose.PoseLandmark.RIGHT_INDEX].x, lm[mp_pose.PoseLandmark.RIGHT_INDEX].y)

    fail_points = []
    
    # 1. FINGER PLACEMENT CHECK
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

def analyze_salute_frame(frame_rgb, analysis_dir):
    """Analyzes a single RGB frame from the webcam (Live Mode)."""
    model = _get_pose_model() 
    results = model.process(frame_rgb)
    
    if results.pose_landmarks:
        success_flags, fail_points = _get_salute_posture_feedback(results.pose_landmarks, mp_pose)
        
        annotated_image = draw_and_annotate(frame_rgb.copy(), results.pose_landmarks, fail_points, "SALUTE (LIVE)")
        
        _, buffer = cv2.imencode('.jpg', annotated_image)
        image_b64_data = [f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"]

        if not fail_points:
            feedback_text = "🌟 **Perfect Salute!** Hold the position with rigidity."
        else:
            feedback_text = f"❌ **Error!** Fix highlighted areas: {', '.join(fail_points).replace('_', ' ')}. Maintain arm and wrist lock."
        
        return {"image_b64_array": image_b64_data, "feedback": feedback_text}
        
    return {"image_b64_array": [], "feedback": "No cadet detected in the frame or hand is not raised."}


# --------------------------------------------------------------------------
# --- EXPORT 2: VIDEO ANALYSIS (Comprehensive) ---
# --------------------------------------------------------------------------
def analyze_salute(video_path, analysis_dir):
    """Analyzes a full video for cumulative performance (Video Upload Mode)."""
    model = _get_pose_model() 
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": "Video file not found or corrupted.", "feedback": "Error: Video file not found or corrupted."}

    finger_placement_succeeded = False
    hand_form_succeeded = False
    elbow_raise_succeeded = False

    best_failure_frame_image = None
    last_known_landmarks = None

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = model.process(image)
            
            if results.pose_landmarks:
                last_known_landmarks = results.pose_landmarks
                success_flags, current_frame_fail_points = _get_salute_posture_feedback(results.pose_landmarks, mp_pose)
                
                if success_flags:
                    if success_flags['finger_placement']: finger_placement_succeeded = True
                    if success_flags['hand_form']: hand_form_succeeded = True
                    if success_flags['elbow_raise']: elbow_raise_succeeded = True
                
                    if current_frame_fail_points and best_failure_frame_image is None:
                        best_failure_frame_image = image.copy()
            
    finally:
        cap.release()

    final_fail_points = []
    if not finger_placement_succeeded: final_fail_points.append('FINGER_POS')
    if not hand_form_succeeded: final_fail_points.append('HAND_FORM')
    if not elbow_raise_succeeded: final_fail_points.append('ELBOW_RAISE')
    
    overall_correct = not final_fail_points
    
    feedback_lines = []
    if overall_correct:
         feedback_lines.append("🌟 **Outstanding Salute!** Your salute was performed correctly during the video.")
    else:
         feedback_lines.append(f"❌ **Action Required!** Areas: {', '.join(final_fail_points).replace('_', ' ')}.")
         feedback_lines.append(f"✅ Placement: {'OK' if finger_placement_succeeded else 'FAIL'}")
         feedback_lines.append(f"✅ Hand Form: {'OK' if hand_form_succeeded else 'FAIL'}")
         feedback_lines.append(f"✅ Arm Rigidity: {'OK' if elbow_raise_succeeded else 'FAIL'}")
         
    final_text_report = "\n".join(feedback_lines)
    
    image_b64_data = []
    if last_known_landmarks:
        image_for_visual = best_failure_frame_image.copy() if best_failure_frame_image is not None else image.copy()
        visual_image = draw_and_annotate(image_for_visual, last_known_landmarks, final_fail_points, "SALUTE (VIDEO)")
        
        _, buffer = cv2.imencode('.jpg', visual_image)
        image_b64_data = [f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"]


    return {"image_b64_array": image_b64_data, "feedback": final_text_report}
