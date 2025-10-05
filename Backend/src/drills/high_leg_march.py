import cv2
import mediapipe as mp
import sys
import math
import os
import uuid
import base64 # <-- ENSURING THIS IS EXPLICITLY HERE

# --- IMPORT FIX ---
try:
    from .src.pose_utils import calculate_angle 
except ImportError:
    try:
        from src.pose_utils import calculate_angle 
    except ImportError:
        print("FATAL ERROR: Could not import calculate_angle from pose_utils.py. Ensure pose_utils.py is in the 'src/drills' directory.")
        sys.exit(1)

# Initialize MediaPipe Pose Drawing Utilities and Model
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)

# --- DEFINED CONSTANTS ---
HIGH_LEG_Y_TOLERANCE = 0.04        
HIP_FLEXION_ANGLE_RANGE = (80, 105) 
KNEE_BEND_ANGLE_RANGE = (80, 105)   
STATIONARY_LEG_STRAIGHT = 170       

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
    if 'KNEE_HEIGHT' in fail_points:
        L_KNEE = mp_pose.PoseLandmark.LEFT_KNEE.value
        L_HIP = mp_pose.PoseLandmark.LEFT_HIP.value
        R_KNEE = mp_pose.PoseLandmark.RIGHT_KNEE.value
        R_HIP = mp_pose.PoseLandmark.RIGHT_HIP.value
        
        # Determine which leg is lifted to highlight error
        if landmarks.landmark[L_KNEE].y < landmarks.landmark[R_KNEE].y:
            active_hip_y_px = int(landmarks.landmark[L_HIP].y * h)
            active_knee_x_px = int(landmarks.landmark[L_KNEE].x * w)
            
            # 1. Highlight the erroneous hip-knee connection in RED
            cv2.line(annotated_image, (int(landmarks.landmark[L_HIP].x * w), active_hip_y_px), (int(landmarks.landmark[L_KNEE].x * w), int(landmarks.landmark[L_KNEE].y * h)), RED, 5)
            
            # 2. Draw a horizontal GREEN line at the target hip level
            cv2.line(annotated_image, (active_knee_x_px - 30, active_hip_y_px), (active_knee_x_px + 30, active_hip_y_px), GREEN, 3)
            cv2.putText(annotated_image, "TARGET HEIGHT", (active_knee_x_px + 40, active_hip_y_px), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 2, cv2.LINE_AA)

        else:
            active_hip_y_px = int(landmarks.landmark[R_HIP].y * h)
            active_knee_x_px = int(landmarks.landmark[R_KNEE].x * w)
            
            cv2.line(annotated_image, (int(landmarks.landmark[R_HIP].x * w), active_hip_y_px), (int(landmarks.landmark[R_KNEE].x * w), int(landmarks.landmark[R_KNEE].y * h)), RED, 5)
            
            cv2.line(annotated_image, (active_knee_x_px - 30, active_hip_y_px), (active_knee_x_px + 30, active_hip_y_px), GREEN, 3)
            cv2.putText(annotated_image, "TARGET HEIGHT", (active_knee_x_px + 40, active_hip_y_px), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 2, cv2.LINE_AA)
            
        fail_message += "Height Fail "
        
    if 'KNEE_ANGLE' in fail_points:
        L_KNEE = mp_pose.PoseLandmark.LEFT_KNEE.value
        R_KNEE = mp_pose.PoseLandmark.RIGHT_KNEE.value
        if landmarks.landmark[L_KNEE].y < landmarks.landmark[R_KNEE].y:
            cv2.circle(annotated_image, (int(landmarks.landmark[L_KNEE].x * w), int(landmarks.landmark[L_KNEE].y * h)), 10, RED, -1)
        else:
            cv2.circle(annotated_image, (int(landmarks.landmark[R_KNEE].x * w), int(landmarks.landmark[R_KNEE].y * h)), 10, RED, -1)
        fail_message += "Knee Angle Fail "

    if 'STATIONARY_LEG' in fail_points:
        L_KNEE = mp_pose.PoseLandmark.LEFT_KNEE.value
        R_KNEE = mp_pose.PoseLandmark.RIGHT_KNEE.value
        if landmarks.landmark[L_KNEE].y < landmarks.landmark[R_KNEE].y:
            S_HIP = mp_pose.PoseLandmark.RIGHT_HIP.value
            S_ANKLE = mp_pose.PoseLandmark.RIGHT_ANKLE.value
            # Highlight stationary leg in RED
            cv2.line(annotated_image, (int(landmarks.landmark[S_HIP].x * w), int(landmarks.landmark[S_HIP].y * h)), (int(landmarks.landmark[S_ANKLE].x * w), int(landmarks.landmark[S_ANKLE].y * h)), RED, 5)
        else:
            S_HIP = mp_pose.PoseLandmark.LEFT_HIP.value
            S_ANKLE = mp_pose.PoseLandmark.LEFT_ANKLE.value
            cv2.line(annotated_image, (int(landmarks.landmark[S_HIP].x * w), int(landmarks.landmark[S_HIP].y * h)), (int(landmarks.landmark[S_ANKLE].x * w), int(landmarks.landmark[S_ANKLE].y * h)), RED, 5)
        fail_message += "Stationary Leg Fail"
        
    cv2.putText(annotated_image, f"{drill_name}: {fail_message}", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    
    return annotated_image


# --- CORE ANALYSIS FUNCTION ---
def analyze_high_leg_march(video_path, analysis_dir):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": "Video file not found or corrupted.", "feedback": "Error: Video file not found or corrupted."}

    # --- TRACKING FLAGS (Cumulative Success) ---
    knee_height_succeeded = False
    knee_angle_succeeded = False
    stationary_leg_succeeded = False

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
                
                # --- Landmark Extraction (Normalized) ---
                r_shldr = (lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].x, lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].y)
                l_shldr = (lm[mp_pose.PoseLandmark.LEFT_SHOULDER].x, lm[mp_pose.PoseLandmark.LEFT_SHOULDER].y)
                
                r_hip = (lm[mp_pose.PoseLandmark.RIGHT_HIP].x, lm[mp_pose.PoseLandmark.RIGHT_HIP].y)
                l_hip = (lm[mp_pose.PoseLandmark.LEFT_HIP].x, lm[mp_pose.PoseLandmark.LEFT_HIP].y)
                
                r_knee = (lm[mp_pose.PoseLandmark.RIGHT_KNEE].x, lm[mp_pose.PoseLandmark.RIGHT_KNEE].y)
                l_knee = (lm[mp_pose.PoseLandmark.LEFT_KNEE].x, lm[mp_pose.PoseLandmark.LEFT_KNEE].y)
                
                r_ankle = (lm[mp_pose.PoseLandmark.RIGHT_ANKLE].x, lm[mp_pose.PoseLandmark.RIGHT_ANKLE].y)
                l_ankle = (lm[mp_pose.PoseLandmark.LEFT_ANKLE].x, lm[mp_pose.PoseLandmark.LEFT_ANKLE].y)
                
                # Determine which leg is lifted 
                is_left_lifted = l_knee[1] < r_knee[1] - 0.05
                is_right_lifted = r_knee[1] < l_knee[1] - 0.05
                
                if is_left_lifted:
                    active_hip, active_knee, active_ankle = l_hip, l_knee, l_ankle
                    support_hip, support_knee, support_ankle = r_hip, r_knee, r_ankle
                elif is_right_lifted:
                    active_hip, active_knee, active_ankle = r_hip, r_knee, r_ankle
                    support_hip, support_knee, support_ankle = l_hip, l_knee, l_ankle
                else:
                    # No significant lift detected, skip frame logic
                    continue

                # --- 1. KNEE HEIGHT CHECK (Active Leg) ---
                knee_height_ok = active_knee[1] <= active_hip[1] + HIGH_LEG_Y_TOLERANCE 

                # --- 2. KNEE ANGLE CHECK (Active Leg) ---
                # Note: We must ensure we pass the correct shoulder for angle calculation (L_SHLDR for L leg, R_SHLDR for R leg)
                shldr_for_active_leg = l_shldr if is_left_lifted else r_shldr
                
                hip_flexion_angle = calculate_angle(shldr_for_active_leg, active_hip, active_knee) 
                knee_bend_angle = calculate_angle(active_hip, active_knee, active_ankle)
                
                knee_angle_ok = (
                    HIP_FLEXION_ANGLE_RANGE[0] <= hip_flexion_angle <= HIP_FLEXION_ANGLE_RANGE[1] and
                    KNEE_BEND_ANGLE_RANGE[0] <= knee_bend_angle <= KNEE_BEND_ANGLE_RANGE[1]
                )

                # --- 3. STATIONARY LEG CHECK (Support Leg) ---
                support_knee_angle = calculate_angle(support_hip, support_knee, support_ankle)
                stationary_leg_ok = support_knee_angle > STATIONARY_LEG_STRAIGHT
                
                # --- UPDATE SUCCESS TRACKERS ---
                if knee_height_ok: knee_height_succeeded = True
                if knee_angle_ok: knee_angle_succeeded = True
                if stationary_leg_ok: stationary_leg_succeeded = True

                # --- VISUAL FRAME CAPTURE LOGIC ---
                
                if not knee_height_ok: current_frame_fail_points.append('KNEE_HEIGHT')
                if not knee_angle_ok: current_frame_fail_points.append('KNEE_ANGLE')
                if not stationary_leg_ok: current_frame_fail_points.append('STATIONARY_LEG')
                
                num_failures = len(current_frame_fail_points)
                
                # Capture BEST SUCCESS FRAME (0 failures)
                if num_failures == 0:
                    best_success_frame = image.copy()
                    
                # Capture WORST FAILURE FRAME (most errors, or the first frame with fewer errors)
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
    if knee_height_succeeded and knee_angle_succeeded and stationary_leg_succeeded:
        frame_to_use = best_success_frame
        final_fail_points = [] 
    else:
        frame_to_use = best_failure_frame 
        final_fail_points = []
        if not knee_height_succeeded: final_fail_points.append('KNEE_HEIGHT')
        if not knee_angle_succeeded: final_fail_points.append('KNEE_ANGLE')
        if not stationary_leg_succeeded: final_fail_points.append('STATIONARY_LEG')


    if frame_to_use is not None and last_known_landmarks is not None:
        # Annotate the single saved frame
        annotated_image = draw_and_annotate(frame_to_use, last_known_landmarks, final_fail_points, "HIGH LEG MARCH")
        
        # Encode image to Base64
        _, buffer = cv2.imencode('.jpg', annotated_image)
        image_b64_data.append(f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}")
    
    # --- FINAL TEXT REPORT GENERATION ---
    feedback_lines = [f"\n"]
    
    overall_correct = (knee_height_succeeded and knee_angle_succeeded and stationary_leg_succeeded)
    
    if overall_correct:
        feedback_lines.append("✅ OVERALL: PERFECT HIGH LEG MARCH POSTURE ACHIEVED.")
    else:
        feedback_lines.append("❌ OVERALL: PERFECT HIGH LEG MARCH POSTURE NOT DETECTED.")
    feedback_lines.append("\n- COMPONENT BREAKDOWN -")

    if knee_height_succeeded:
        feedback_lines.append(f"✅ Knee Height: Knee was lifted to the required hip/waist level.")
    else:
        feedback_lines.append(f"❌ Knee Height: Knee was not lifted high enough (highlighted in red). Target height shown in green.")

    if knee_angle_succeeded:
        feedback_lines.append(f"✅ Active Leg Angle: Thigh was parallel to the ground and knee bent ~90°.")
    else:
        feedback_lines.append(f"❌ Active Leg Angle: Knee angle was incorrect (not close to 90° or thigh not horizontal).")

    if stationary_leg_succeeded:
        feedback_lines.append("✅ Stationary Leg: Support leg remained straight and locked.")
    else:
        feedback_lines.append("❌ Stationary Leg: Support leg was bent or unstable.")
        
    final_text_report = "\n".join(feedback_lines)

    # Return dictionary with Base64 image data and text feedback
    return {"image_b64_array": image_b64_data, "feedback": final_text_report}
