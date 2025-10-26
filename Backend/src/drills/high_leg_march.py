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

# --- DEFINED CONSTANTS (Kept for reference) ---
HIGH_LEG_Y_TOLERANCE = 0.04      
HIP_FLEXION_ANGLE_RANGE = (80, 105) 
KNEE_BEND_ANGLE_RANGE = (80, 105)  
STATIONARY_LEG_STRAIGHT = 170      

# --- LAZY INITIALIZATION HELPER FUNCTION ---
def _get_pose_model():
    """Initializes the heavy MediaPipe Pose model only if it hasn't been done yet."""
    global pose
    if pose is None:
        print("INFO: Lazily initializing MediaPipe Pose model for High Leg March analysis...")
        pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
    return pose

# --- Helper functions (draw_and_annotate is large, reusing core logic) ---

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

    # --- Start of failure highlight logic (Retaining detailed visual feedback) ---
    if 'KNEE_HEIGHT' in fail_points:
        L_KNEE = mp_pose.PoseLandmark.LEFT_KNEE.value
        L_HIP = mp_pose.PoseLandmark.LEFT_HIP.value
        R_KNEE = mp_pose.PoseLandmark.RIGHT_KNEE.value
        
        is_left_lifted = landmarks.landmark[L_KNEE].y < landmarks.landmark[R_KNEE].y
        
        active_hip_y_px = int(landmarks.landmark[L_HIP if is_left_lifted else mp_pose.PoseLandmark.RIGHT_HIP.value].y * h)
        active_knee_x_px = int(landmarks.landmark[L_KNEE if is_left_lifted else R_KNEE].x * w)
        
        cv2.line(annotated_image, 
                 (int(landmarks.landmark[L_HIP if is_left_lifted else mp_pose.PoseLandmark.RIGHT_HIP.value].x * w), active_hip_y_px), 
                 (int(landmarks.landmark[L_KNEE if is_left_lifted else R_KNEE].x * w), int(landmarks.landmark[L_KNEE if is_left_lifted else R_KNEE].y * h)), RED, 5)
        
        cv2.line(annotated_image, (active_knee_x_px - 30, active_hip_y_px), (active_knee_x_px + 30, active_hip_y_px), GREEN, 3)
        cv2.putText(annotated_image, "TARGET HEIGHT", (active_knee_x_px + 40, active_hip_y_px), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 2, cv2.LINE_AA)
        fail_message += "Height Fail "
        
    if 'KNEE_ANGLE' in fail_points:
        L_KNEE = mp_pose.PoseLandmark.LEFT_KNEE.value
        R_KNEE = mp_pose.PoseLandmark.RIGHT_KNEE.value
        knee_to_highlight = L_KNEE if (landmarks.landmark[L_KNEE].y < landmarks.landmark[R_KNEE].y) else R_KNEE
        cv2.circle(annotated_image, (int(landmarks.landmark[knee_to_highlight].x * w), int(landmarks.landmark[knee_to_highlight].y * h)), 10, RED, -1)
        fail_message += "Knee Angle Fail "

    if 'STATIONARY_LEG' in fail_points:
        L_KNEE = mp_pose.PoseLandmark.LEFT_KNEE.value
        R_KNEE = mp_pose.PoseLandmark.RIGHT_KNEE.value
        
        is_left_lifted = landmarks.landmark[L_KNEE].y < landmarks.landmark[R_KNEE].y
        
        S_HIP = mp_pose.PoseLandmark.RIGHT_HIP.value if is_left_lifted else mp_pose.PoseLandmark.LEFT_HIP.value
        S_ANKLE = mp_pose.PoseLandmark.RIGHT_ANKLE.value if is_left_lifted else mp_pose.PoseLandmark.LEFT_ANKLE.value

        cv2.line(annotated_image, (int(landmarks.landmark[S_HIP].x * w), int(landmarks.landmark[S_HIP].y * h)), 
                 (int(landmarks.landmark[S_ANKLE].x * w), int(landmarks.landmark[S_ANKLE].y * h)), RED, 5)
        fail_message += "Stationary Leg Fail"
        
    cv2.putText(annotated_image, f"{drill_name}: {fail_message}", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    
    return annotated_image

def _get_posture_feedback(landmarks, mp_pose):
    """Calculates posture compliance for a single frame (Abstracted Core Logic)."""
    lm = landmarks.landmark
    
    r_shldr = (lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].x, lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].y)
    l_shldr = (lm[mp_pose.PoseLandmark.LEFT_SHOULDER].x, lm[mp_pose.PoseLandmark.LEFT_SHOULDER].y)
    r_hip = (lm[mp_pose.PoseLandmark.RIGHT_HIP].x, lm[mp_pose.PoseLandmark.RIGHT_HIP].y)
    l_hip = (lm[mp_pose.PoseLandmark.LEFT_HIP].x, lm[mp_pose.PoseLandmark.LEFT_HIP].y)
    r_knee = (lm[mp_pose.PoseLandmark.RIGHT_KNEE].x, lm[mp_pose.PoseLandmark.RIGHT_KNEE].y)
    l_knee = (lm[mp_pose.PoseLandmark.LEFT_KNEE].x, lm[mp_pose.PoseLandmark.LEFT_KNEE].y)
    r_ankle = (lm[mp_pose.PoseLandmark.RIGHT_ANKLE].x, lm[mp_pose.PoseLandmark.RIGHT_ANKLE].y)
    l_ankle = (lm[mp_pose.PoseLandmark.LEFT_ANKLE].x, lm[mp_pose.PoseLandmark.LEFT_ANKLE].y)
    
    is_left_lifted = l_knee[1] < r_knee[1] - HIGH_LEG_Y_TOLERANCE
    is_right_lifted = r_knee[1] < l_knee[1] - HIGH_LEG_Y_TOLERANCE
    
    if not (is_left_lifted or is_right_lifted):
        return None, None 

    active_hip, active_knee, active_ankle = (l_hip, l_knee, l_ankle) if is_left_lifted else (r_hip, r_knee, r_ankle)
    support_hip, support_knee, support_ankle = (r_hip, r_knee, r_ankle) if is_left_lifted else (l_hip, l_knee, l_ankle)
    shldr_for_active_leg = l_shldr if is_left_lifted else r_shldr
    
    fail_points = []
    
    # 1. KNEE HEIGHT CHECK
    knee_height_ok = active_knee[1] <= active_hip[1] + HIGH_LEG_Y_TOLERANCE 
    if not knee_height_ok: fail_points.append('KNEE_HEIGHT')

    # 2. KNEE ANGLE CHECK
    hip_flexion_angle = calculate_angle(shldr_for_active_leg, active_hip, active_knee) 
    knee_bend_angle = calculate_angle(active_hip, active_knee, active_ankle)
    knee_angle_ok = (HIP_FLEXION_ANGLE_RANGE[0] <= hip_flexion_angle <= HIP_FLEXION_ANGLE_RANGE[1] and
                     KNEE_BEND_ANGLE_RANGE[0] <= knee_bend_angle <= KNEE_BEND_ANGLE_RANGE[1])
    if not knee_angle_ok: fail_points.append('KNEE_ANGLE')

    # 3. STATIONARY LEG CHECK
    support_knee_angle = calculate_angle(support_hip, support_knee, support_ankle)
    stationary_leg_ok = support_knee_angle > STATIONARY_LEG_STRAIGHT
    if not stationary_leg_ok: fail_points.append('STATIONARY_LEG')
    
    success_flags = {
        'knee_height': knee_height_ok,
        'knee_angle': knee_angle_ok,
        'stationary_leg': stationary_leg_ok,
    }
    
    return success_flags, fail_points


# --------------------------------------------------------------------------
# --- EXPORT 1: LIVE FRAME ANALYSIS (Fast) ---
# --------------------------------------------------------------------------
def analyze_high_leg_frame(frame_rgb, analysis_dir):
    """Analyzes a single RGB frame from the webcam (Live Mode)."""
    model = _get_pose_model() 
    results = model.process(frame_rgb)
    
    if results.pose_landmarks:
        success_flags, fail_points = _get_posture_feedback(results.pose_landmarks, mp_pose)
        
        if success_flags is None: 
            return {"image_b64_array": [], "feedback": "Posture: **Standby/Relax**. Perform the drill lift to analyze."}

        # Annotate image
        annotated_image = draw_and_annotate(frame_rgb.copy(), results.pose_landmarks, fail_points, "HIGH LEG MARCH (LIVE)")
        
        # Encode to Base64
        _, buffer = cv2.imencode('.jpg', annotated_image)
        image_b64_data = [f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"]

        # Generate simplified coaching feedback for live mode
        if not fail_points:
            feedback_text = "🌟 **Perfect Posture!** Hold the pose steady."
        else:
            feedback_text = f"❌ **Error!** Check the highlighted areas: {', '.join(fail_points).replace('_', ' ')}. Lock your stationary leg."
        
        return {"image_b64_array": image_b64_data, "feedback": feedback_text}
        
    return {"image_b64_array": [], "feedback": "No cadet detected in the frame."}


# --------------------------------------------------------------------------
# --- EXPORT 2: VIDEO ANALYSIS (Comprehensive) ---
# --------------------------------------------------------------------------
def analyze_high_leg_march(video_path, analysis_dir):
    """Analyzes a full video for cumulative performance (Video Upload Mode)."""
    model = _get_pose_model() 
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": "Video file not found or corrupted.", "feedback": "Error: Video file not found or corrupted."}

    # --- TRACKING FLAGS (Cumulative Success for the whole video) ---
    knee_height_succeeded = False
    knee_angle_succeeded = False
    stationary_leg_succeeded = False
    
    best_failure_frame_image = None
    last_known_landmarks = None
    min_failures = float('inf')

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = model.process(image)
            
            if results.pose_landmarks:
                last_known_landmarks = results.pose_landmarks
                success_flags, current_frame_fail_points = _get_posture_feedback(results.pose_landmarks, mp_pose)
                
                if success_flags:
                    if success_flags['knee_height']: knee_height_succeeded = True
                    if success_flags['knee_angle']: knee_angle_succeeded = True
                    if success_flags['stationary_leg']: stationary_leg_succeeded = True
                    
                    num_failures = len(current_frame_fail_points)
                    if num_failures > 0 and num_failures < min_failures:
                         min_failures = num_failures
                         best_failure_frame_image = image.copy()
            
    finally:
        cap.release()

    # --- Compile Final Report ---
    final_fail_points = []
    if not knee_height_succeeded: final_fail_points.append('KNEE_HEIGHT')
    if not knee_angle_succeeded: final_fail_points.append('KNEE_ANGLE')
    if not stationary_leg_succeeded: final_fail_points.append('STATIONARY_LEG')
    
    overall_correct = not final_fail_points
    
    feedback_lines = []
    if overall_correct:
         feedback_lines.append("🌟 **Excellent Drill!** Your High Leg March posture is correct and rigid.")
    else:
         feedback_lines.append(f"❌ **Action Required!** The primary areas needing attention are: {', '.join(final_fail_points).replace('_', ' ')}.")
         feedback_lines.append(f"✅ Knee Height: {'OK' if knee_height_succeeded else 'FAIL'}")
         feedback_lines.append(f"✅ Knee Angle: {'OK' if knee_angle_succeeded else 'FAIL'}")
         feedback_lines.append(f"✅ Stationary Leg: {'OK' if stationary_leg_succeeded else 'FAIL'}")
         
    final_text_report = "\n".join(feedback_lines)
    
    image_b64_data = []
    if last_known_landmarks:
        image_for_visual = best_failure_frame_image.copy() if best_failure_frame_image is not None else image.copy()
        visual_image = draw_and_annotate(image_for_visual, last_known_landmarks, final_fail_points, "HIGH LEG MARCH (VIDEO)")
        _, buffer = cv2.imencode('.jpg', visual_image)
        image_b64_data = [f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"]


    return {"image_b64_array": image_b64_data, "feedback": final_text_report}
