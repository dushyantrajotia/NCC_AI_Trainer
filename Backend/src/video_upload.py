import cv2
import mediapipe as mp
import sys

# Ensure pose_utils.py is accessible in the Python path
try:
    # Assuming pose_utils.py is in the same directory and contains calculate_angle
    from .pose_utils import calculate_angle 
except ImportError:
    print("FATAL ERROR: Could not import calculate_angle from pose_utils.py. Please create the file.")
    # Exit gracefully if the core dependency is missing
    sys.exit(1)

# Initialize MediaPipe Pose Model
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)

# --- Define Normalized Thresholds ---
# Based on normalized screen coordinates (0.0 to 1.0)
HIGH_LEG_Y_TOLERANCE = 0.04        # Max Y-diff for Knee Y to Hip Y (Knee must be near hip level)
HIP_FLEXION_ANGLE_RANGE = (80, 105) # Angle: Shoulder-Hip-Knee (Thigh horizontal, approx 90 degrees)
KNEE_BEND_ANGLE_RANGE = (80, 105)   # Angle: Hip-Knee-Ankle (Lower leg vertical, approx 90 degrees)

def analyze_high_leg_march(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return "Error: Could not open video file. Check path or format."

    # --- TRACKING FLAGS ---
    correct_knee_height_achieved = False
    correct_knee_angle_achieved = False
    correct_high_leg_pose_achieved = False

    # Initialize variables to prevent NameError outside the detection block
    l_knee_Y, l_hip_Y = 0.0, 0.0
    r_knee_Y, r_hip_Y = 0.0, 0.0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(image)

        if results.pose_landmarks:
            lm = results.pose_landmarks.landmark

            # --- Extract Key Normalized Landmarks ---
            l_shldr = (lm[mp_pose.PoseLandmark.LEFT_SHOULDER].x, lm[mp_pose.PoseLandmark.LEFT_SHOULDER].y)
            l_hip = (lm[mp_pose.PoseLandmark.LEFT_HIP].x, lm[mp_pose.PoseLandmark.LEFT_HIP].y)
            l_knee = (lm[mp_pose.PoseLandmark.LEFT_KNEE].x, lm[mp_pose.PoseLandmark.LEFT_KNEE].y)
            l_ankle = (lm[mp_pose.PoseLandmark.LEFT_ANKLE].x, lm[mp_pose.PoseLandmark.LEFT_ANKLE].y)
            
            r_shldr = (lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].x, lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].y)
            r_hip = (lm[mp_pose.PoseLandmark.RIGHT_HIP].x, lm[mp_pose.PoseLandmark.RIGHT_HIP].y)
            r_knee = (lm[mp_pose.PoseLandmark.RIGHT_KNEE].x, lm[mp_pose.PoseLandmark.RIGHT_KNEE].y)
            r_ankle = (lm[mp_pose.PoseLandmark.RIGHT_ANKLE].x, lm[mp_pose.PoseLandmark.RIGHT_ANKLE].y)
            
            # Extract Y-coordinates (normalized)
            l_knee_Y = l_knee[1]
            l_hip_Y = l_hip[1]
            r_knee_Y = r_knee[1]
            r_hip_Y = r_hip[1]

            # --- Left Leg Analysis ---
            l_knee_level_ok = l_knee_Y <= l_hip_Y + HIGH_LEG_Y_TOLERANCE 
            l_hip_flex_angle = calculate_angle(l_shldr, l_hip, l_knee)
            l_hip_flex_ok = HIP_FLEXION_ANGLE_RANGE[0] <= l_hip_flex_angle <= HIP_FLEXION_ANGLE_RANGE[1]
            l_knee_bend_angle = calculate_angle(l_hip, l_knee, l_ankle)
            l_knee_bend_ok = KNEE_BEND_ANGLE_RANGE[0] <= l_knee_bend_angle <= KNEE_BEND_ANGLE_RANGE[1]
            left_correct_frame = l_knee_level_ok and l_hip_flex_ok and l_knee_bend_ok

            # --- Right Leg Analysis ---
            r_knee_level_ok = r_knee_Y <= r_hip_Y + HIGH_LEG_Y_TOLERANCE 
            r_hip_flex_angle = calculate_angle(r_shldr, r_hip, r_knee)
            r_hip_flex_ok = HIP_FLEXION_ANGLE_RANGE[0] <= r_hip_flex_angle <= HIP_FLEXION_ANGLE_RANGE[1]
            r_knee_bend_angle = calculate_angle(r_hip, r_knee, r_ankle)
            r_knee_bend_ok = KNEE_BEND_ANGLE_RANGE[0] <= r_knee_bend_angle <= KNEE_BEND_ANGLE_RANGE[1]
            right_correct_frame = r_knee_level_ok and r_hip_flex_ok and r_knee_bend_ok
            
            
            # --- UPDATE TRACKING FLAGS (SUCCESS TRACKING) ---
            if left_correct_frame or right_correct_frame:
                correct_high_leg_pose_achieved = True
                correct_knee_height_achieved = True
                correct_knee_angle_achieved = True
            
            # --- UPDATE TRACKING FLAGS (FAILURE TRACKING) ---
            if (l_knee_Y < l_hip_Y) or (r_knee_Y < r_hip_Y):
                if not l_knee_level_ok and not r_knee_level_ok:
                    correct_knee_height_achieved = False 
                if not l_knee_bend_ok and not r_knee_bend_ok:
                    correct_knee_angle_achieved = False


    cap.release()

    # --- FINAL DRILL FEEDBACK REPORT (Prepared for Web Return) ---
    feedback_lines = []
    feedback_lines.append("===========================================================")
    feedback_lines.append("           NCC High Leg March Analysis Report")
    feedback_lines.append("===========================================================")
    feedback_lines.append("\n--- HIGH LEG MARCH STEP ---")
    
    correct_points = []
    incorrect_points = []
    
    if correct_high_leg_pose_achieved:
        correct_points.append("Full High Leg Posture Achieved")
        correct_points.append("Knee Raised to Hip Level")
        correct_points.append("Knee Bent at 90° Angle")
    else:
        incorrect_points.append("Full High Leg Posture Was Never Detected")
        
        if not correct_knee_height_achieved:
            incorrect_points.append("Knee Was Not Lifted to Required Hip/Waist Level")
        
        if not correct_knee_angle_achieved:
            incorrect_points.append("Knee Angle Incorrect (Lower leg was not perpendicular to thigh)")
        
    
    feedback_lines.append(f"  ✅ Correctness: {', '.join(correct_points) if correct_points else 'None'}")
    feedback_lines.append(f"  ❌ Incorrectness: {', '.join(incorrect_points) if incorrect_points else 'None'}")
    
    feedback_lines.append("\n===========================================================")
    
    # Return the results as a single string for the Flask/React frontend
    return '\n'.join(feedback_lines)

if __name__ == "__main__":
    # Local testing (does not run when called by Flask)
    # The file path is handled by Flask when run via the web
    LOCAL_TEST_VIDEO_PATH = r"data/example/local_test_video.mp4" 
    
    print(f"--- Running Local Test on: {LOCAL_TEST_VIDEO_PATH} ---")