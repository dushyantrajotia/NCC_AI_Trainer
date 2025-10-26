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
ATTENTION_ANKLE_GAP = 0.03 # Max normalized X-diff for heels to be considered touching
ATTENTION_KNEE_STRAIGHT = 170 # Min angle for straight knee (Hip-Knee-Ankle)
KNEE_BEND_SNAP_MIN = 80      # Min knee bend detected during the snap lift (active lift)
HEEL_LIFT_MIN_DIFF = 0.015 # Max normalized Y-difference (Toe Y - Heel Y) required to confirm the heel initiated the pivot/lift.

# --- LAZY INITIALIZATION HELPER FUNCTION ---
def _get_pose_model():
    """Initializes the heavy MediaPipe Pose model only if it hasn't been done yet."""
    global pose
    if pose is None:
        print("INFO: Lazily initializing MediaPipe Pose model for Turns analysis...")
        pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
    return pose

# --- DRAWING UTILITY FUNCTION (Shared) ---
def draw_and_annotate_turn(image, landmarks, fail_points, drill_name):
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
    RED = (0, 0, 255) # BGR format
    
    # Highlight the relevant moving foot based on the drill name
    is_right_turn = (drill_name == "Right Turn")
    
    L_HEEL = mp_pose.PoseLandmark.LEFT_HEEL.value
    L_TOE = mp_pose.PoseLandmark.LEFT_FOOT_INDEX.value
    R_HEEL = mp_pose.PoseLandmark.RIGHT_HEEL.value
    R_TOE = mp_pose.PoseLandmark.RIGHT_FOOT_INDEX.value
    L_ANKLE = mp_pose.PoseLandmark.LEFT_ANKLE.value
    R_ANKLE = mp_pose.PoseLandmark.RIGHT_ANKLE.value
    L_KNEE = mp_pose.PoseLandmark.LEFT_KNEE.value
    R_KNEE = mp_pose.PoseLandmark.RIGHT_KNEE.value

    fail_message = ""
    
    # 1. Heel Disengagement Failure (Initial phase)
    if 'HEEL_DISENGAGE' in fail_points:
        heel_lm = landmarks.landmark[L_HEEL if is_right_turn else R_HEEL]
        toe_lm = landmarks.landmark[L_TOE if is_right_turn else R_TOE]
        
        cv2.line(annotated_image, (int(heel_lm.x * w), int(heel_lm.y * h)), (int(toe_lm.x * w), int(toe_lm.y * h)), RED, 5)
        fail_message += "Pivot Dragged "
        
    # 2. Snap Motion Failure (Mid phase)
    if 'SNAP_LIFT' in fail_points:
        moving_knee = L_KNEE if is_right_turn else R_KNEE
        cv2.circle(annotated_image, (int(landmarks.landmark[moving_knee].x * w), int(landmarks.landmark[moving_knee].y * h)), 10, RED, -1)
        fail_message += "No Lift "
        
    # 3. Final Position Failure (End phase)
    if 'FINAL_POS' in fail_points:
        cv2.circle(annotated_image, (int(landmarks.landmark[L_ANKLE].x * w), int(landmarks.landmark[L_ANKLE].y * h)), 10, RED, -1) 
        cv2.circle(annotated_image, (int(landmarks.landmark[R_ANKLE].x * w), int(landmarks.landmark[R_ANKLE].y * h)), 10, RED, -1)
        fail_message += "Unsnapped Feet"
        
    cv2.putText(annotated_image, f"{drill_name}: {fail_message}", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    
    return annotated_image

# --------------------------------------------------------------------------
# --- CORE ANALYSIS LOGIC (HELPER FUNCTION) ---
# --------------------------------------------------------------------------
def analyze_turn_logic(video_path, analysis_dir, drill_name):
    """Analyzes a full video for the turn movement."""
    model = _get_pose_model() 
    is_right_turn = (drill_name == "Right Turn")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"image_b64_array": [], "feedback": f"Error: Could not open video file for {drill_name} analysis."}
    
    # --- TRACKING FLAGS (Cumulative Success) ---
    final_snap_achieved = False 
    snap_motion_detected = False 
    heel_disengagement_detected = False

    # --- FRAME CAPTURE STORAGE ---
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
                lm = results.pose_landmarks.landmark 
                last_known_landmarks = results.pose_landmarks
                
                # --- Landmark Extraction & Checks ---
                R_HIP = (lm[mp_pose.PoseLandmark.RIGHT_HIP].x, lm[mp_pose.PoseLandmark.RIGHT_HIP].y)
                L_HIP = (lm[mp_pose.PoseLandmark.LEFT_HIP].x, lm[mp_pose.PoseLandmark.LEFT_HIP].y)
                R_ANKLE = (lm[mp_pose.PoseLandmark.RIGHT_ANKLE].x, lm[mp_pose.PoseLandmark.RIGHT_ANKLE].y)
                L_ANKLE = (lm[mp_pose.PoseLandmark.LEFT_ANKLE].x, lm[mp_pose.PoseLandmark.LEFT_ANKLE].y)
                R_KNEE = (lm[mp_pose.PoseLandmark.RIGHT_KNEE].x, lm[mp_pose.PoseLandmark.RIGHT_KNEE].y)
                L_KNEE = (lm[mp_pose.PoseLandmark.LEFT_KNEE].x, lm[mp_pose.PoseLandmark.LEFT_KNEE].y)
                
                moving_heel = (lm[mp_pose.PoseLandmark.LEFT_HEEL].x, lm[mp_pose.PoseLandmark.LEFT_HEEL].y) if is_right_turn else (lm[mp_pose.PoseLandmark.RIGHT_HEEL].x, lm[mp_pose.PoseLandmark.RIGHT_HEEL].y)
                moving_toe = (lm[mp_pose.PoseLandmark.LEFT_FOOT_INDEX].x, lm[mp_pose.PoseLandmark.LEFT_FOOT_INDEX].y) if is_right_turn else (lm[mp_pose.PoseLandmark.RIGHT_FOOT_INDEX].x, lm[mp_pose.PoseLandmark.RIGHT_FOOT_INDEX].y)
                moving_hip = L_HIP if is_right_turn else R_HIP
                moving_knee = L_KNEE if is_right_turn else R_KNEE
                moving_ankle = L_ANKLE if is_right_turn else R_ANKLE
                stationary_hip = R_HIP if is_right_turn else L_HIP
                stationary_knee = R_KNEE if is_right_turn else L_KNEE
                stationary_ankle = R_ANKLE if is_right_turn else L_ANKLE

                # 1. HEEL DISENGAGEMENT CHECK 
                if moving_toe[1] - moving_heel[1] > HEEL_LIFT_MIN_DIFF:
                    heel_disengagement_detected = True 

                # 2. SNAP MOTION CHECK 
                moving_knee_angle = calculate_angle(moving_hip, moving_knee, moving_ankle)
                if moving_knee_angle < KNEE_BEND_SNAP_MIN:
                    snap_motion_detected = True 

                # 3. FINAL SNAP TO ATTENTION CHECK 
                stationary_straight = calculate_angle(stationary_hip, stationary_knee, stationary_ankle) > ATTENTION_KNEE_STRAIGHT
                moving_straight = calculate_angle(moving_hip, moving_knee, moving_ankle) > ATTENTION_KNEE_STRAIGHT
                legs_straight = stationary_straight and moving_straight
                ankles_together = abs(R_ANKLE[0] - L_ANKLE[0]) < ATTENTION_ANKLE_GAP
                
                if legs_straight and ankles_together:
                    final_snap_achieved = True
                
                # --- VISUAL FRAME CAPTURE LOGIC ---
                current_frame_fail_points = []
                if not heel_disengagement_detected: current_frame_fail_points.append('HEEL_DISENGAGE')
                # Only flag snap lift failure if motion was expected but didn't happen (angle > 150 implies a straight-leg pivot)
                if not snap_motion_detected and moving_knee_angle > 150: current_frame_fail_points.append('SNAP_LIFT')
                if not final_snap_achieved and (not legs_straight or not ankles_together): current_frame_fail_points.append('FINAL_POS')
                
                num_failures = len(current_frame_fail_points)
                if num_failures > 0 and (best_failure_frame_image is None or num_failures > min_failures):
                    min_failures = num_failures
                    best_failure_frame_image = image.copy()
    finally:
        cap.release()

    # --- IMAGE COMPILATION AND ENCODING ---
    image_b64_data = []
    overall_correct = (heel_disengagement_detected and snap_motion_detected and final_snap_achieved)
    final_fail_points = []
    if not heel_disengagement_detected: final_fail_points.append('HEEL_DISENGAGE')
    if not snap_motion_detected: final_fail_points.append('SNAP_LIFT')
    if not final_snap_achieved: final_fail_points.append('FINAL_POS')

    feedback_lines = []
    
    if last_known_landmarks is not None:
        frame_to_use = best_failure_frame_image if best_failure_frame_image is not None else image # Use the last processed frame if successful
        annotated_image = draw_and_annotate_turn(frame_to_use.copy(), last_known_landmarks, final_fail_points, drill_name)
        
        _, buffer = cv2.imencode('.jpg', annotated_image)
        image_b64_data.append(f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}")
    
    # --- FINAL TEXT REPORT GENERATION ---
    if overall_correct:
         feedback_lines.append(f"🌟 **Excellent Turn!** Your {drill_name} was performed with precision and a crisp snap.")
    else:
         failure_messages = [f"❌ {fail.replace('_', ' ')}" for fail in final_fail_points]
         feedback_lines.append(f"❌ **Action Required!** Areas: **{', '.join(failure_messages)}**.")
    
    feedback_lines.append("\n--- COMPONENT BREAKDOWN ---")
    feedback_lines.append(f"✅ Heel Disengagement: {'Cleanly achieved' if heel_disengagement_detected else 'You are sliding or dragging your foot.'}")
    feedback_lines.append(f"✅ Snap Motion: {'Required lift/snap detected' if snap_motion_detected else 'Moving foot was passive. Active knee bend is required.'}")
    feedback_lines.append(f"✅ Final Position: {'Snapped together correctly' if final_snap_achieved else 'Feet were not snapped together or legs were bent.'}")
    
    final_text_report = "\n".join(feedback_lines)

    return {"image_b64_array": image_b64_data, "feedback": final_text_report}

# --------------------------------------------------------------------------
# --- EXPORT 2: PUBLIC FUNCTIONS (Video Mode) - FIXES THE IMPORT ERROR ---
# --------------------------------------------------------------------------
def analyze_turn_right(video_path, analysis_dir):
    """Public function for Right Turn video analysis."""
    return analyze_turn_logic(video_path, analysis_dir, "Right Turn")

def analyze_turn_left(video_path, analysis_dir):
    """Public function for Left Turn video analysis."""
    return analyze_turn_logic(video_path, analysis_dir, "Left Turn")

# --------------------------------------------------------------------------
# --- EXPORT 3: DUMMY LIVE FRAME FUNCTIONS (For Live Mode) ---
# --------------------------------------------------------------------------
def analyze_turn_right_frame(frame_rgb, analysis_dir):
    """Public function for Right Turn live frame analysis (returns placeholder message)."""
    return {"image_b64_array": [], "feedback": "Turn analysis requires motion over time. Please use Video Upload mode for accurate assessment."}

def analyze_turn_left_frame(frame_rgb, analysis_dir):
    """Public function for Left Turn live frame analysis (returns placeholder message)."""
    return {"image_b64_array": [], "feedback": "Turn analysis requires motion over time. Please use Video Upload mode for accurate assessment."}

def analyze_turn_about(video_path, analysis_dir):
    return {"image_b64_array": [], "feedback": "\n--- NCC ABOUT TURN ANALYSIS ---\nAnalysis for About Turn is currently a placeholder."}
