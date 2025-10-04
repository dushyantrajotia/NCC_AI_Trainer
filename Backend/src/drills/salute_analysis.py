import cv2
import mediapipe as mp # <-- Core MediaPipe import is here
import sys
import math
import os
import uuid
import base64

# --- IMPORT FIX ---
try:
    # Tries the relative import (Used by Flask/app.py)
    from .src.pose_utils import calculate_angle 
except ImportError:
    try:
        # Falls back to direct import (Used when running 'python salute_analysis.py' directly)
        from src.pose_utils import calculate_angle 
    except ImportError:
        # If both fail, terminate and print the error
        print("FATAL ERROR: Could not import calculate_angle from pose_utils.py. Ensure pose_utils.py is in the 'src/drills' directory.")
        sys.exit(1)

# Initialize MediaPipe Pose Drawing Utilities and Model
# 🚨 CORRECTED POSITION: Runs AFTER 'import mediapipe as mp'
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)

# --- DEFINED CONSTANTS (Tolerances for Drill Accuracy) ---
# FINGER PLACEMENT (Index finger touching the temple/eyebrow)
FINGER_Y_ALIGNMENT_TOLERANCE = 0.04 # Max vertical deviation from target (eye line)
FINGER_X_ALIGNMENT_TOLERANCE = 0.06 # Max horizontal deviation (pushes placement closer to temple)

# HAND FORM AND ARM RIGIDITY
WRIST_RIGIDITY_MIN_ANGLE = 160 # Angle at the wrist (Elbow-Wrist-Index) for rigidity.
ELBOW_RAISE_ANGLE_RANGE = (160, 180) # Arm must be nearly straight and rigid

# --- DRAWING UTILITY FUNCTION (Shared) ---
def draw_and_annotate(image, landmarks, fail_points, drill_name):
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
    RED = (0, 0, 255) # BGR format
    GREEN = (0, 255, 0) # BGR format

    # Highlight specific fail points
    if 'FINGER_POS' in fail_points:
        R_INDEX = mp_pose.PoseLandmark.RIGHT_INDEX.value
        R_EYE_OUTER = mp_pose.PoseLandmark.RIGHT_EYE_OUTER.value
        R_EAR = mp_pose.PoseLandmark.RIGHT_EAR.value
        
        # 1. Highlight the incorrect index finger position in RED
        cv2.circle(annotated_image, 
                   (int(landmarks.landmark[R_INDEX].x * w), int(landmarks.landmark[R_INDEX].y * h)), 
                   10, RED, -1)
        
        # 2. Draw a GREEN circle at the ideal target zone
        target_x = int(((landmarks.landmark[R_EYE_OUTER].x + landmarks.landmark[R_EAR].x) / 2) * w)
        target_y = int(landmarks.landmark[R_EYE_OUTER].y * h) # Use outer eye as vertical target proxy
        
        cv2.circle(annotated_image, (target_x, target_y), 10, GREEN, -1)
        fail_message += "Placement Fail "
        
    if 'HAND_FORM' in fail_points:
        R_WRIST = mp_pose.PoseLandmark.RIGHT_WRIST.value
        R_INDEX = mp_pose.PoseLandmark.RIGHT_INDEX.value
        R_ELBOW = mp_pose.PoseLandmark.RIGHT_ELBOW.value
        
        # Highlight wrist, elbow, index finger segment in RED
        cv2.line(annotated_image, 
                 (int(landmarks.landmark[R_ELBOW].x * w), int(landmarks.landmark[R_ELBOW].y * h)), 
                 (int(landmarks.landmark[R_WRIST].x * w), int(landmarks.landmark[R_WRIST].y * h)), 
                 RED, 5) 
        cv2.line(annotated_image, 
                 (int(landmarks.landmark[R_WRIST].x * w), int(landmarks.landmark[R_WRIST].y * h)), 
                 (int(landmarks.landmark[R_INDEX].x * w), int(landmarks.landmark[R_INDEX].y * h)), 
                 RED, 5) 
        fail_message += "Hand Rigidity Fail "

    if 'ELBOW_RAISE' in fail_points:
        R_SHOULDER = mp_pose.PoseLandmark.RIGHT_SHOULDER.value
        R_ELBOW = mp_pose.PoseLandmark.RIGHT_ELBOW.value
        
        # Highlight Shoulder-Elbow segment in RED
        cv2.line(annotated_image, 
                 (int(landmarks.landmark[R_SHOULDER].x * w), int(landmarks.landmark[R_SHOULDER].y * h)), 
                 (int(landmarks.landmark[R_ELBOW].x * w), int(landmarks.landmark[R_ELBOW].y * h)), 
                 RED, 5) 
        fail_message += "Elbow Angle Fail"
        
    # Put text report on top of the video
    cv2.putText(annotated_image, f"{drill_name}: {fail_message}", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    
    return annotated_image


# --- CORE ANALYSIS FUNCTION ---
def analyze_salute(video_path, analysis_dir):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": "Video file not found or corrupted.", "feedback": "Error: Video file not found or corrupted."}

    # --- TRACKING FLAGS ---
    finger_placement_succeeded = False
    hand_form_succeeded = False
    elbow_raise_succeeded = False

    # --- FRAME CAPTURE STORAGE ---
    best_failure_frame = None
    best_success_frame = None
    min_failures = float('inf')
    last_known_landmarks = None

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(image)
            
            current_frame_fail_points = []

            if results.pose_landmarks:
                lm = results.pose_landmarks.landmark
                last_known_landmarks = results.pose_landmarks
                
                # --- Landmark Extraction ---
                right_ear = (lm[mp_pose.PoseLandmark.RIGHT_EAR].x, lm[mp_pose.PoseLandmark.RIGHT_EAR].y)
                right_eye_inner = (lm[mp_pose.PoseLandmark.RIGHT_EYE_INNER].x, lm[mp_pose.PoseLandmark.RIGHT_EYE_INNER].y)
                right_eye_outer = (lm[mp_pose.PoseLandmark.RIGHT_EYE_OUTER].x, lm[mp_pose.PoseLandmark.RIGHT_EYE_OUTER].y)
                
                r_shoulder = (lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].x, lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].y)
                r_elbow = (lm[mp_pose.PoseLandmark.RIGHT_ELBOW].x, lm[mp_pose.PoseLandmark.RIGHT_ELBOW].y)
                r_wrist = (lm[mp_pose.PoseLandmark.RIGHT_WRIST].x, lm[mp_pose.PoseLandmark.RIGHT_WRIST].y)
                r_index = (lm[mp_pose.PoseLandmark.RIGHT_INDEX].x, lm[mp_pose.PoseLandmark.RIGHT_INDEX].y)

                # --- 1. FINGER PLACEMENT CHECK ---
                target_y = (right_eye_inner[1] + right_eye_outer[1]) / 2 
                target_x = (right_eye_outer[0] + right_ear[0]) / 2       
                
                y_pos_deviation = abs(r_index[1] - target_y)
                x_pos_deviation = abs(r_index[0] - target_x)
                
                finger_placement_ok = (
                    y_pos_deviation < FINGER_Y_ALIGNMENT_TOLERANCE and 
                    x_pos_deviation < FINGER_X_ALIGNMENT_TOLERANCE
                )

                # --- 2. HAND FORM CHECK (Elbow-Wrist-Index straightness) ---
                wrist_rigidity_angle = calculate_angle(r_elbow, r_wrist, r_index)
                hand_form_ok = wrist_rigidity_angle >= WRIST_RIGIDITY_MIN_ANGLE

                # --- 3. ARM RAISE/RIGIDITY CHECK (Elbow Angle) ---
                elbow_angle = calculate_angle(r_shoulder, r_elbow, r_wrist)
                elbow_raise_ok = (
                    ELBOW_RAISE_ANGLE_RANGE[0] <= elbow_angle <= ELBOW_RAISE_ANGLE_RANGE[1]
                )
                
                # --- UPDATE SUCCESS TRACKERS ---
                if finger_placement_ok:
                    finger_placement_succeeded = True
                if hand_form_ok:
                    hand_form_succeeded = True
                if elbow_raise_ok:
                    elbow_raise_succeeded = True

                # --- VISUAL FRAME CAPTURE LOGIC ---
                
                if not finger_placement_ok: current_frame_fail_points.append('FINGER_POS')
                if not hand_form_ok: current_frame_fail_points.append('HAND_FORM')
                if not elbow_raise_ok: current_frame_fail_points.append('ELBOW_RAISE')
                
                num_failures = len(current_frame_fail_points)
                
                if num_failures == 0:
                    best_success_frame = image.copy()
                    
                if num_failures > 0 and (best_failure_frame is None or num_failures > min_failures):
                    min_failures = num_failures
                    best_failure_frame = image.copy()
            
            # Note: We are no longer writing video frames here

    except Exception as e:
        error_message = f"Critical error during video processing: {str(e)}"
        final_text_report = f"\n--- ERROR ---\n{error_message}\n--- ERROR ---"
        return {"image_b64_array": [], "feedback": final_text_report}
        
    finally:
        cap.release()

    # --- IMAGE COMPILATION AND ENCODING ---
    image_b64_data = []

    # Choose the most relevant frame to display
    frame_to_use = None
    if finger_placement_succeeded and hand_form_succeeded and elbow_raise_succeeded:
        frame_to_use = best_success_frame
        final_fail_points = [] 
    else:
        frame_to_use = best_failure_frame 
        final_fail_points = []
        if not finger_placement_succeeded: final_fail_points.append('FINGER_POS')
        if not hand_form_succeeded: final_fail_points.append('HAND_FORM')
        if not elbow_raise_succeeded: final_fail_points.append('ELBOW_RAISE')


    if frame_to_use is not None and last_known_landmarks is not None:
        # Annotate the single saved frame
        annotated_image = draw_and_annotate(frame_to_use, last_known_landmarks, final_fail_points, "SALUTE")
        
        # Encode image to Base64
        _, buffer = cv2.imencode('.jpg', annotated_image)
        image_b64_data.append(f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}")
    
    # --- FINAL TEXT REPORT GENERATION ---
    feedback_lines = [f"\n--- NCC SALUTE ANALYSIS ---"]
    
    overall_correct = (finger_placement_succeeded and hand_form_succeeded and elbow_raise_succeeded)
    
    if overall_correct:
        feedback_lines.append("✅ OVERALL: PERFECT SALUTE POSTURE DETECTED.")
    else:
        feedback_lines.append("❌ OVERALL: PERFECT SALUTE POSTURE NOT DETECTED.")
    feedback_lines.append("\n- COMPONENT BREAKDOWN -")

    if finger_placement_succeeded:
        feedback_lines.append("✅ Finger Placement: Index finger successfully touched the required area (temple/eyebrow).")
    else:
        feedback_lines.append("❌ Finger Placement: Index finger was consistently off target (highlighted in red). Target spot shown in green.")

    if hand_form_succeeded:
        feedback_lines.append(f"✅ Hand Form: Hand segment was rigid (angle at wrist > {WRIST_RIGIDITY_MIN_ANGLE}°), inferring joined fingers.")
    else:
        feedback_lines.append(f"❌ Hand Form: Hand segment was not rigid (angle at wrist < {WRIST_RIGIDITY_MIN_ANGLE}°).")

    if elbow_raise_succeeded:
        feedback_lines.append("✅ Arm Rigidity: Elbow angle was straight and rigid (within the 160°-180° range).")
    else:
        feedback_lines.append("❌ Arm Rigidity: Elbow was too bent, breaking the required straight line of the arm.")
        
    final_text_report = "\n".join(feedback_lines)

    # Return dictionary with Base64 image data and text feedback
    return {"image_b64_array": image_b64_data, "feedback": final_text_report}
