import cv2
import mediapipe as mp
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
        # Falls back to direct import (Used when running 'python turns_analysis.py' directly)
        from src.pose_utils import calculate_angle 
    except ImportError:
        print("FATAL ERROR: Could not import calculate_angle from pose_utils.py. Ensure pose_utils.py is in the 'src/drills' directory.")
        sys.exit(1)

# Initialize MediaPipe Pose Drawing Utilities and Model
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)

# --- DEFINED CONSTANTS (Tolerances for Drill Accuracy) ---
ATTENTION_ANKLE_GAP = 0.03 # Max normalized X-diff for heels to be considered touching
ATTENTION_KNEE_STRAIGHT = 170 # Min angle for straight knee (Hip-Knee-Ankle)
KNEE_BEND_SNAP_MIN = 80      # Min knee bend detected during the snap lift (active lift)

# Max normalized Y-difference (Toe Y - Heel Y) required to confirm the heel initiated the pivot/lift.
HEEL_LIFT_MIN_DIFF = 0.015 

# --- DRAWING UTILITY FUNCTION (Shared) ---
def draw_and_annotate_turn(image, landmarks, fail_points, drill_name):
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
    
    # --- Annotation Logic ---
    
    # Highlight the relevant moving foot based on the drill name
    if drill_name == "Right Turn":
        L_HEEL = mp_pose.PoseLandmark.LEFT_HEEL.value
        L_TOE = mp_pose.PoseLandmark.LEFT_FOOT_INDEX.value
        moving_ankle = mp_pose.PoseLandmark.LEFT_ANKLE.value
        fail_message = "Dahine Mur "
    else: # Left Turn
        R_HEEL = mp_pose.PoseLandmark.RIGHT_HEEL.value
        R_TOE = mp_pose.PoseLandmark.RIGHT_FOOT_INDEX.value
        moving_ankle = mp_pose.PoseLandmark.RIGHT_ANKLE.value
        fail_message = "Baen Mur "

    # 1. Heel Disengagement Failure (Initial phase)
    if 'HEEL_DISENGAGE' in fail_points:
        # Highlight the lifting foot's heel and toe segment in RED
        heel_lm = landmarks.landmark[L_HEEL if drill_name == "Right Turn" else R_HEEL]
        toe_lm = landmarks.landmark[L_TOE if drill_name == "Right Turn" else R_TOE]
        
        cv2.line(annotated_image, (int(heel_lm.x * w), int(heel_lm.y * h)), (int(toe_lm.x * w), int(toe_lm.y * h)), RED, 5)
        fail_message += "Pivot Dragged "
        
    # 2. Snap Motion Failure (Mid phase)
    if 'SNAP_LIFT' in fail_points:
        # Highlight the moving knee joint in RED
        moving_knee = mp_pose.PoseLandmark.LEFT_KNEE.value if drill_name == "Right Turn" else mp_pose.PoseLandmark.RIGHT_KNEE.value
        cv2.circle(annotated_image, (int(landmarks.landmark[moving_knee].x * w), int(landmarks.landmark[moving_knee].y * h)), 10, RED, -1)
        fail_message += "No Lift "
        
    # 3. Final Position Failure (End phase)
    if 'FINAL_POS' in fail_points:
        # Highlight both ankles in RED
        L_ANKLE = mp_pose.PoseLandmark.LEFT_ANKLE.value
        R_ANKLE = mp_pose.PoseLandmark.RIGHT_ANKLE.value
        
        cv2.circle(annotated_image, (int(landmarks.landmark[L_ANKLE].x * w), int(landmarks.landmark[L_ANKLE].y * h)), 10, RED, -1) 
        cv2.circle(annotated_image, (int(landmarks.landmark[R_ANKLE].x * w), int(landmarks.landmark[R_ANKLE].y * h)), 10, RED, -1)
        fail_message += "Unsnapped Feet"
        
    # Put text report on top of the video
    cv2.putText(annotated_image, f"{drill_name}: {fail_message}", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    
    return annotated_image

# --- UTILITY FUNCTION TO ANALYZE TURN LOGIC ---
def analyze_turn_logic(video_path, analysis_dir, drill_name):
    # Determine which foot is the moving foot for the analysis
    is_right_turn = (drill_name == "Right Turn")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"image_b64_array": [], "feedback": f"Error: Could not open video file for {drill_name} analysis."}

    # --- TRACKING FLAGS ---
    final_snap_achieved = False 
    snap_motion_detected = False     
    heel_disengagement_detected = False

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
                R_HIP = (lm[mp_pose.PoseLandmark.RIGHT_HIP].x, lm[mp_pose.PoseLandmark.RIGHT_HIP].y)
                L_HIP = (lm[mp_pose.PoseLandmark.LEFT_HIP].x, lm[mp_pose.PoseLandmark.LEFT_HIP].y)
                R_ANKLE = (lm[mp_pose.PoseLandmark.RIGHT_ANKLE].x, lm[mp_pose.PoseLandmark.RIGHT_ANKLE].y)
                L_ANKLE = (lm[mp_pose.PoseLandmark.LEFT_ANKLE].x, lm[mp_pose.PoseLandmark.LEFT_ANKLE].y)
                R_KNEE = (lm[mp_pose.PoseLandmark.RIGHT_KNEE].x, lm[mp_pose.PoseLandmark.RIGHT_KNEE].y)
                L_KNEE = (lm[mp_pose.PoseLandmark.LEFT_KNEE].x, lm[mp_pose.PoseLandmark.LEFT_KNEE].y)
                
                # Moving foot landmarks
                moving_heel = (lm[mp_pose.PoseLandmark.LEFT_HEEL].x, lm[mp_pose.PoseLandmark.LEFT_HEEL].y) if is_right_turn else (lm[mp_pose.PoseLandmark.RIGHT_HEEL].x, lm[mp_pose.PoseLandmark.RIGHT_HEEL].y)
                moving_toe = (lm[mp_pose.PoseLandmark.LEFT_FOOT_INDEX].x, lm[mp_pose.PoseLandmark.LEFT_FOOT_INDEX].y) if is_right_turn else (lm[mp_pose.PoseLandmark.RIGHT_FOOT_INDEX].x, lm[mp_pose.PoseLandmark.RIGHT_FOOT_INDEX].y)
                moving_hip = L_HIP if is_right_turn else R_HIP
                moving_knee = L_KNEE if is_right_turn else R_KNEE
                moving_ankle = L_ANKLE if is_right_turn else R_ANKLE
                
                # Stationary foot landmarks (Pivot)
                stationary_hip = R_HIP if is_right_turn else L_HIP
                stationary_knee = R_KNEE if is_right_turn else L_KNEE
                stationary_ankle = R_ANKLE if is_right_turn else L_ANKLE


                # --- 1. HEEL DISENGAGEMENT CHECK (Initial Pivot) ---
                # Check if the heel lifts before the active snap (toe Y > heel Y)
                if moving_toe[1] - moving_heel[1] > HEEL_LIFT_MIN_DIFF:
                    heel_disengagement_detected = True 

                # --- 2. SNAP MOTION CHECK (Active Knee Bend) ---
                moving_knee_angle = calculate_angle(moving_hip, moving_knee, moving_ankle)
                if moving_knee_angle < KNEE_BEND_SNAP_MIN:
                    snap_motion_detected = True 

                # --- 3. FINAL SNAP TO ATTENTION CHECK ---
                
                # Leg straightness check
                stationary_straight = calculate_angle(stationary_hip, stationary_knee, stationary_ankle) > ATTENTION_KNEE_STRAIGHT
                moving_straight = calculate_angle(moving_hip, moving_knee, moving_ankle) > ATTENTION_KNEE_STRAIGHT
                legs_straight = stationary_straight and moving_straight

                # Heels together check
                ankles_together = abs(R_ANKLE[0] - L_ANKLE[0]) < ATTENTION_ANKLE_GAP
                
                if legs_straight and ankles_together:
                    final_snap_achieved = True

                # --- VISUAL FRAME CAPTURE LOGIC ---
                
                if not heel_disengagement_detected: current_frame_fail_points.append('HEEL_DISENGAGE')
                if not snap_motion_detected and moving_knee_angle > 150: current_frame_fail_points.append('SNAP_LIFT')
                if not final_snap_achieved and (not legs_straight or not ankles_together): current_frame_fail_points.append('FINAL_POS')
                
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
    if heel_disengagement_detected and snap_motion_detected and final_snap_achieved:
        frame_to_use = best_success_frame
        final_fail_points = [] 
    else:
        frame_to_use = best_failure_frame 
        final_fail_points = []
        if not heel_disengagement_detected: final_fail_points.append('HEEL_DISENGAGE')
        if not snap_motion_detected: final_fail_points.append('SNAP_LIFT')
        if not final_snap_achieved: final_fail_points.append('FINAL_POS')


    if frame_to_use is not None and last_known_landmarks is not None:
        # Annotate the single saved frame
        annotated_image = draw_and_annotate_turn(frame_to_use, last_known_landmarks, final_fail_points, drill_name)
        
        # Encode image to Base64
        _, buffer = cv2.imencode('.jpg', annotated_image)
        image_b64_data.append(f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}")
    
    # --- FINAL TEXT REPORT GENERATION ---
    feedback_lines = [f"\n"]
    
    overall_correct = (heel_disengagement_detected and snap_motion_detected and final_snap_achieved)
    
    if overall_correct:
        feedback_lines.append("✅ OVERALL: TURN EXECUTED CORRECTLY.")
    else:
        feedback_lines.append("❌ OVERALL: TURN EXECUTION FAILED.")

    feedback_lines.append("\n--- COMPONENT BREAKDOWN ---")

    if heel_disengagement_detected:
        feedback_lines.append(f"✅ Heel Disengagement: Moving Heel lifted before active snap (correct pivot initiation).")
    else:
        feedback_lines.append(f"❌ Heel Disengagement: Moving Heel did not lift cleanly, suggesting the foot was dragged or slid.")

    if snap_motion_detected:
        feedback_lines.append(f"✅ Snap Motion: Moving foot executed the required lift/snap motion (Active knee bend detected).")
    else:
        feedback_lines.append(f"❌ Snap Motion: Moving foot was passive (no clear active lift detected).")

    if final_snap_achieved:
        feedback_lines.append("✅ Final Position: Feet snapped together correctly into the Attention stance.")
    else:
        feedback_lines.append("❌ Final Position: Failed to snap into the correct Attention stance (feet separated or legs bent).")
    
    
    return {"image_b64_array": image_b64_data, "feedback": "\n".join(feedback_lines)}


# --- EXPORT FUNCTIONS ---

def analyze_turn_right(video_path, analysis_dir):
    return analyze_turn_logic(video_path, analysis_dir, "Right Turn")

def analyze_turn_left(video_path, analysis_dir):
    return analyze_turn_logic(video_path, analysis_dir, "Left Turn")

def analyze_turn_about(video_path, analysis_dir):
    # Placeholder for About Turn logic
    return {"image_b64_array": [], "feedback": "\n--- NCC ABOUT TURN ANALYSIS ---\nAnalysis for About Turn is currently a placeholder."}
