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

# Initialize MediaPipe components (but NOT the heavy model yet)
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose
pose = None # 🚨 CRITICAL FIX: Lazy Initialization Placeholder

# --- DEFINED CONSTANTS (Tolerances for Drill Accuracy) ---
HIGH_LEG_Y_TOLERANCE = 0.04
# 🚨 MODIFIED: Widened the upper bound for hip flexion tolerance as requested
HIP_FLEXION_ANGLE_RANGE = (80, 120) # Changed from (80, 115)
# Confirmed upper bound for knee bend tolerance is 110
KNEE_BEND_ANGLE_RANGE = (80, 110)
STATIONARY_LEG_STRAIGHT = 170
# Foot Angle Range (Ankle-Heel-Toe angle for downward point)
FOOT_ANGLE_RANGE = (70, 110)

# --- LAZY INITIALIZATION HELPER FUNCTION ---
def _get_pose_model():
    """Initializes and returns the MediaPipe Pose model instance."""
    global pose
    if pose is None:
        print("INFO: Lazily initializing MediaPipe Pose model for High Leg March analysis...")
        pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
    return pose

# --- DRAWING UTILITY FUNCTION (Shared) ---
def draw_and_annotate(image, landmarks, fail_points, drill_name, angles=None):
    """Draws landmarks, highlights failures, and optionally displays angles."""
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
    WHITE = (255, 255, 255)
    BLUE = (255, 0, 0) # Color for angle text

    # --- Start of failure highlight logic ---
    L_KNEE_ENUM = mp_pose.PoseLandmark.LEFT_KNEE
    R_KNEE_ENUM = mp_pose.PoseLandmark.RIGHT_KNEE
    L_HIP_ENUM = mp_pose.PoseLandmark.LEFT_HIP
    R_HIP_ENUM = mp_pose.PoseLandmark.RIGHT_HIP
    L_ANKLE_ENUM = mp_pose.PoseLandmark.LEFT_ANKLE
    R_ANKLE_ENUM = mp_pose.PoseLandmark.RIGHT_ANKLE
    L_HEEL_ENUM = mp_pose.PoseLandmark.LEFT_HEEL
    R_HEEL_ENUM = mp_pose.PoseLandmark.RIGHT_HEEL
    L_FOOT_INDEX_ENUM = mp_pose.PoseLandmark.LEFT_FOOT_INDEX
    R_FOOT_INDEX_ENUM = mp_pose.PoseLandmark.RIGHT_FOOT_INDEX


    # Check visibility before accessing landmarks
    if not landmarks.landmark:
         return annotated_image # Return early if no landmarks

    # Determine which leg is lifted (handle potential low visibility)
    left_knee_visible = landmarks.landmark[L_KNEE_ENUM.value].visibility > 0.5
    right_knee_visible = landmarks.landmark[R_KNEE_ENUM.value].visibility > 0.5

    is_left_lifted = False
    if left_knee_visible and right_knee_visible:
        is_left_lifted = landmarks.landmark[L_KNEE_ENUM.value].y < landmarks.landmark[R_KNEE_ENUM.value].y
    elif left_knee_visible: # Assume left is lifted if right isn't visible
        is_left_lifted = True

    # Check visibility for required landmarks before drawing/calculating
    active_knee_lm = landmarks.landmark[L_KNEE_ENUM.value] if is_left_lifted else landmarks.landmark[R_KNEE_ENUM.value]
    active_hip_lm = landmarks.landmark[L_HIP_ENUM.value] if is_left_lifted else landmarks.landmark[R_HIP_ENUM.value]
    support_hip_lm = landmarks.landmark[R_HIP_ENUM.value] if is_left_lifted else landmarks.landmark[L_HIP_ENUM.value]
    support_ankle_lm = landmarks.landmark[R_ANKLE_ENUM.value] if is_left_lifted else landmarks.landmark[L_ANKLE_ENUM.value]
    active_ankle_lm = landmarks.landmark[L_ANKLE_ENUM.value] if is_left_lifted else landmarks.landmark[R_ANKLE_ENUM.value]
    active_heel_lm = landmarks.landmark[L_HEEL_ENUM.value] if is_left_lifted else landmarks.landmark[R_HEEL_ENUM.value]
    active_foot_index_lm = landmarks.landmark[L_FOOT_INDEX_ENUM.value] if is_left_lifted else landmarks.landmark[R_FOOT_INDEX_ENUM.value]


    active_knee_visible = active_knee_lm.visibility > 0.5
    active_hip_visible = active_hip_lm.visibility > 0.5
    support_hip_visible = support_hip_lm.visibility > 0.5
    support_ankle_visible = support_ankle_lm.visibility > 0.5
    active_ankle_visible = active_ankle_lm.visibility > 0.5
    active_heel_visible = active_heel_lm.visibility > 0.5
    active_foot_index_visible = active_foot_index_lm.visibility > 0.5


    if 'KNEE_HEIGHT' in fail_points and active_hip_visible and active_knee_visible:
        active_hip_y_px = int(active_hip_lm.y * h)
        active_knee_x_px = int(active_knee_lm.x * w)
        cv2.line(annotated_image, (int(active_hip_lm.x * w), active_hip_y_px), (int(active_knee_lm.x * w), int(active_knee_lm.y * h)), RED, 5)
        cv2.line(annotated_image, (active_knee_x_px - 30, active_hip_y_px), (active_knee_x_px + 30, active_hip_y_px), GREEN, 3)
        cv2.putText(annotated_image, "TARGET", (active_knee_x_px + 40, active_hip_y_px + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 2, cv2.LINE_AA)
        fail_message += "Height Fail "

    if 'KNEE_ANGLE' in fail_points and active_knee_visible:
        cv2.circle(annotated_image, (int(active_knee_lm.x * w), int(active_knee_lm.y * h)), 10, RED, -1)
        fail_message += "Angle Fail "

    if 'STATIONARY_LEG' in fail_points and support_hip_visible and support_ankle_visible:
        cv2.line(annotated_image, (int(support_hip_lm.x * w), int(support_hip_lm.y * h)),
                 (int(support_ankle_lm.x * w), int(support_ankle_lm.y * h)), RED, 5)
        fail_message += "Support Fail "

    if 'FOOT_ANGLE' in fail_points and active_ankle_visible and active_heel_visible and active_foot_index_visible:
        ankle_pos = (int(active_ankle_lm.x * w), int(active_ankle_lm.y * h))
        heel_pos = (int(active_heel_lm.x * w), int(active_heel_lm.y * h))
        toe_pos = (int(active_foot_index_lm.x * w), int(active_foot_index_lm.y * h))
        cv2.line(annotated_image, ankle_pos, heel_pos, RED, 3)
        cv2.line(annotated_image, ankle_pos, toe_pos, RED, 3)
        fail_message += "Foot Angle Fail "

    # --- Display Angles ---
    if angles:
        if active_hip_visible and active_knee_visible:
            hip_text_pos = (int(active_hip_lm.x * w) - 60, int(active_hip_lm.y * h) - 15)
            cv2.putText(annotated_image, f"Hip:{angles.get('hip_flexion', 0):.0f}", hip_text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.6, BLUE, 2, cv2.LINE_AA)
            knee_text_pos = (int(active_knee_lm.x * w) + 15, int(active_knee_lm.y * h))
            cv2.putText(annotated_image, f"Knee:{angles.get('knee_bend', 0):.0f}", knee_text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.6, BLUE, 2, cv2.LINE_AA)
        if active_ankle_visible and active_heel_visible and active_foot_index_visible:
            foot_text_pos = (int(active_ankle_lm.x * w) + 10, int(active_ankle_lm.y * h) + 25)
            cv2.putText(annotated_image, f"Foot:{angles.get('foot_angle', 0):.0f}", foot_text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.6, BLUE, 2, cv2.LINE_AA)


    cv2.putText(annotated_image, f"{drill_name}: {fail_message}", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, WHITE, 2, cv2.LINE_AA)
    # --- End of failure highlight logic ---

    return annotated_image

# --------------------------------------------------------------------------
# --- CORE LOGIC: SINGLE FRAME ANALYSIS (ABSTRACTED) ---
# --------------------------------------------------------------------------
def _get_posture_feedback(landmarks, mp_pose_module):
    """Abstracted core logic. Returns success_flags, fail_points, and calculated angles."""
    if not landmarks or not landmarks.landmark:
        return None, None, None

    lm = landmarks.landmark

    # Landmark Visibility Checks & Extraction
    required_landmarks = [
        mp_pose_module.PoseLandmark.RIGHT_SHOULDER, mp_pose_module.PoseLandmark.LEFT_SHOULDER,
        mp_pose_module.PoseLandmark.RIGHT_HIP, mp_pose_module.PoseLandmark.LEFT_HIP,
        mp_pose_module.PoseLandmark.RIGHT_KNEE, mp_pose_module.PoseLandmark.LEFT_KNEE,
        mp_pose_module.PoseLandmark.RIGHT_ANKLE, mp_pose_module.PoseLandmark.LEFT_ANKLE,
        mp_pose_module.PoseLandmark.RIGHT_HEEL, mp_pose_module.PoseLandmark.LEFT_HEEL,
        mp_pose_module.PoseLandmark.RIGHT_FOOT_INDEX, mp_pose_module.PoseLandmark.LEFT_FOOT_INDEX,
    ]
    for lmk_enum in required_landmarks:
        if lmk_enum.value >= len(lm) or lm[lmk_enum.value].visibility < 0.5:
            return None, ["Low Visibility"], None

    # Extraction
    r_shldr = (lm[mp_pose_module.PoseLandmark.RIGHT_SHOULDER].x, lm[mp_pose_module.PoseLandmark.RIGHT_SHOULDER].y)
    l_shldr = (lm[mp_pose_module.PoseLandmark.LEFT_SHOULDER].x, lm[mp_pose_module.PoseLandmark.LEFT_SHOULDER].y)
    r_hip = (lm[mp_pose_module.PoseLandmark.RIGHT_HIP].x, lm[mp_pose_module.PoseLandmark.RIGHT_HIP].y)
    l_hip = (lm[mp_pose_module.PoseLandmark.LEFT_HIP].x, lm[mp_pose_module.PoseLandmark.LEFT_HIP].y)
    r_knee = (lm[mp_pose_module.PoseLandmark.RIGHT_KNEE].x, lm[mp_pose_module.PoseLandmark.RIGHT_KNEE].y)
    l_knee = (lm[mp_pose_module.PoseLandmark.LEFT_KNEE].x, lm[mp_pose_module.PoseLandmark.LEFT_KNEE].y)
    r_ankle = (lm[mp_pose_module.PoseLandmark.RIGHT_ANKLE].x, lm[mp_pose_module.PoseLandmark.RIGHT_ANKLE].y)
    l_ankle = (lm[mp_pose_module.PoseLandmark.LEFT_ANKLE].x, lm[mp_pose_module.PoseLandmark.LEFT_ANKLE].y)
    r_heel = (lm[mp_pose_module.PoseLandmark.RIGHT_HEEL].x, lm[mp_pose_module.PoseLandmark.RIGHT_HEEL].y)
    l_heel = (lm[mp_pose_module.PoseLandmark.LEFT_HEEL].x, lm[mp_pose_module.PoseLandmark.LEFT_HEEL].y)
    r_foot_index = (lm[mp_pose_module.PoseLandmark.RIGHT_FOOT_INDEX].x, lm[mp_pose_module.PoseLandmark.RIGHT_FOOT_INDEX].y)
    l_foot_index = (lm[mp_pose_module.PoseLandmark.LEFT_FOOT_INDEX].x, lm[mp_pose_module.PoseLandmark.LEFT_FOOT_INDEX].y)

    # Determine lifted leg
    is_left_lifted = l_knee[1] < r_knee[1] - HIGH_LEG_Y_TOLERANCE
    is_right_lifted = r_knee[1] < l_knee[1] - HIGH_LEG_Y_TOLERANCE

    angles = {'hip_flexion': 0, 'knee_bend': 0, 'support_knee': 0, 'foot_angle': 0}

    if not (is_left_lifted or is_right_lifted):
        return None, ["No Lift"], None

    active_hip, active_knee, active_ankle = (l_hip, l_knee, l_ankle) if is_left_lifted else (r_hip, r_knee, r_ankle)
    support_hip, support_knee, support_ankle = (r_hip, r_knee, r_ankle) if is_left_lifted else (l_hip, l_knee, l_ankle)
    shldr_for_active_leg = l_shldr if is_left_lifted else r_shldr
    active_heel = l_heel if is_left_lifted else r_heel
    active_foot_index = l_foot_index if is_left_lifted else r_foot_index

    fail_points = []

    # 1. KNEE HEIGHT CHECK
    knee_height_ok = active_knee[1] <= active_hip[1] + HIGH_LEG_Y_TOLERANCE
    if not knee_height_ok: fail_points.append('KNEE_HEIGHT')

    # 2. KNEE ANGLE CHECK (Uses the updated ranges)
    hip_flexion_angle = calculate_angle(shldr_for_active_leg, active_hip, active_knee)
    knee_bend_angle = calculate_angle(active_hip, active_knee, active_ankle)
    angles['hip_flexion'] = hip_flexion_angle
    angles['knee_bend'] = knee_bend_angle

    knee_angle_ok = (HIP_FLEXION_ANGLE_RANGE[0] <= hip_flexion_angle <= HIP_FLEXION_ANGLE_RANGE[1] and
                     KNEE_BEND_ANGLE_RANGE[0] <= knee_bend_angle <= KNEE_BEND_ANGLE_RANGE[1])
    if not knee_angle_ok: fail_points.append('KNEE_ANGLE')

    # 3. STATIONARY LEG CHECK
    support_knee_angle = calculate_angle(support_hip, support_knee, support_ankle)
    angles['support_knee'] = support_knee_angle
    stationary_leg_ok = support_knee_angle > STATIONARY_LEG_STRAIGHT
    if not stationary_leg_ok: fail_points.append('STATIONARY_LEG')

    # 4. FOOT ANGLE CHECK
    foot_angle = calculate_angle(active_heel, active_ankle, active_foot_index)
    angles['foot_angle'] = foot_angle
    foot_angle_ok = FOOT_ANGLE_RANGE[0] <= foot_angle <= FOOT_ANGLE_RANGE[1]
    if not foot_angle_ok: fail_points.append('FOOT_ANGLE')

    success_flags = {
        'knee_height': knee_height_ok,
        'knee_angle': knee_angle_ok,
        'stationary_leg': stationary_leg_ok,
        'foot_angle': foot_angle_ok,
    }

    return success_flags, fail_points, angles

# --------------------------------------------------------------------------
# --- EXPORT 1: LIVE FRAME ANALYSIS (Fast) ---
# --------------------------------------------------------------------------
def analyze_high_leg_frame(frame_rgb, analysis_dir):
    """Analyzes a single RGB frame from the webcam (Live Mode)."""
    model = _get_pose_model()
    results = model.process(frame_rgb)

    if results.pose_landmarks:
        success_flags, fail_points, angles = _get_posture_feedback(results.pose_landmarks, mp_pose)

        if success_flags is None:
            feedback_text = f"Posture: **{'Low Visibility' if fail_points and 'Low Visibility' in fail_points else ('Standby/Relax' if fail_points and 'No Lift' in fail_points else 'Unknown Issue')}**. Adjust position or perform the drill lift."
            annotated_image = draw_and_annotate(frame_rgb.copy(), results.pose_landmarks, fail_points or [], "HIGH LEG MARCH (LIVE)")
            _, buffer = cv2.imencode('.jpg', annotated_image)
            image_b64_data = [f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"]
            return {"image_b64_array": image_b64_data, "feedback": feedback_text}

        annotated_image = draw_and_annotate(frame_rgb.copy(), results.pose_landmarks, fail_points, "HIGH LEG MARCH (LIVE)", angles=angles)
        _, buffer = cv2.imencode('.jpg', annotated_image)
        image_b64_data = [f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"]

        if not fail_points:
            feedback_text = f"🌟 **Perfect Posture!** (Hip: {angles['hip_flexion']:.0f}°, Knee: {angles['knee_bend']:.0f}°, Foot: {angles['foot_angle']:.0f}°)"
        else:
            feedback_text = f"❌ **Error!** Check highlights. (Hip: {angles['hip_flexion']:.0f}°, Knee: {angles['knee_bend']:.0f}°, Foot: {angles['foot_angle']:.0f}°). {', '.join(fail_points).replace('_', ' ')}."

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

    # --- TRACKING FLAGS & BEST VALUES---
    knee_height_succeeded = False
    knee_angle_succeeded = False
    stationary_leg_succeeded = False
    foot_angle_succeeded = False
    best_hip_flexion_overall = 0
    best_knee_bend_overall = 0
    best_foot_angle_overall = 0
    found_valid_pose = False

    best_failure_frame_image = None
    best_success_frame_image = None
    last_known_landmarks = None
    min_failures_in_frame = float('inf')
    best_failure_points_for_frame = []
    angles_for_annotation = None

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = model.process(image)

            if results.pose_landmarks:
                last_known_landmarks = results.pose_landmarks
                success_flags, current_frame_fail_points, current_angles = _get_posture_feedback(results.pose_landmarks, mp_pose)

                if success_flags is None:
                    continue

                found_valid_pose = True

                # Update cumulative success tracking
                if success_flags['knee_height']: knee_height_succeeded = True
                if success_flags['knee_angle']: knee_angle_succeeded = True
                if success_flags['stationary_leg']: stationary_leg_succeeded = True
                if success_flags['foot_angle']: foot_angle_succeeded = True

                num_failures = len(current_frame_fail_points)

                if num_failures == 0 and best_success_frame_image is None:
                    best_success_frame_image = image.copy()
                    angles_for_annotation = current_angles

                # Update best angles based on proximity to 90
                if best_hip_flexion_overall == 0 or abs(current_angles['hip_flexion'] - 90) < abs(best_hip_flexion_overall - 90):
                     best_hip_flexion_overall = current_angles['hip_flexion']
                if best_knee_bend_overall == 0 or abs(current_angles['knee_bend'] - 90) < abs(best_knee_bend_overall - 90):
                     best_knee_bend_overall = current_angles['knee_bend']
                if best_foot_angle_overall == 0 or abs(current_angles['foot_angle'] - 90) < abs(best_foot_angle_overall - 90):
                     best_foot_angle_overall = current_angles['foot_angle']

                if num_failures > 0 and num_failures <= min_failures_in_frame:
                     min_failures_in_frame = num_failures
                     best_failure_frame_image = image.copy()
                     best_failure_points_for_frame = current_frame_fail_points
                     angles_for_annotation = current_angles

    finally:
        cap.release()

    # --- Compile Final Report ---
    if not found_valid_pose:
        return {"image_b64_array": [], "feedback": "❌ Analysis Failed: No valid High Leg March posture detected."}

    final_fail_points_overall = []
    if not knee_height_succeeded: final_fail_points_overall.append('KNEE_HEIGHT')
    if not knee_angle_succeeded: final_fail_points_overall.append('KNEE_ANGLE')
    if not stationary_leg_succeeded: final_fail_points_overall.append('STATIONARY_LEG')
    if not foot_angle_succeeded: final_fail_points_overall.append('FOOT_ANGLE')

    overall_correct = not final_fail_points_overall

    # Determine which frame to show
    frame_to_use_for_annotation = None
    fail_points_for_annotation = []
    angles_to_display = None

    if overall_correct and best_success_frame_image is not None:
        frame_to_use_for_annotation = best_success_frame_image
        fail_points_for_annotation = []
        angles_to_display = angles_for_annotation
    elif not overall_correct and best_failure_frame_image is not None:
        frame_to_use_for_annotation = best_failure_frame_image
        fail_points_for_annotation = best_failure_points_for_frame
        angles_to_display = angles_for_annotation
    elif last_known_landmarks is not None and 'image' in locals():
        frame_to_use_for_annotation = image
        fail_points_for_annotation = final_fail_points_overall
        angles_to_display = angles_for_annotation

    # Generate detailed coaching feedback
    feedback_lines = []
    best_hip_angle_str = f"{best_hip_flexion_overall:.0f}°"
    best_knee_angle_str = f"{best_knee_bend_overall:.0f}°"
    best_foot_angle_str = f"{best_foot_angle_overall:.0f}°"

    if overall_correct:
         feedback_lines.append("🌟 **Excellent Drill!** Your High Leg March posture was consistently correct.")
         feedback_lines.append(f"   Best Angles -> Hip: {best_hip_angle_str}, Knee: {best_knee_angle_str}, Foot: {best_foot_angle_str} (Target: 90°)")
         feedback_lines.append("✅ OVERALL: PERFECT HIGH LEG MARCH POSTURE ACHIEVED.")
    else:
         failure_messages = []
         if not knee_height_succeeded: failure_messages.append("Knee Height (needs more lift).")
         if not knee_angle_succeeded: failure_messages.append(f"Active Leg Angle (Best: Hip {best_hip_angle_str}, Knee {best_knee_angle_str}). Check 90° bend.")
         if not stationary_leg_succeeded: failure_messages.append("Stationary Leg (keep it locked straight).")
         if not foot_angle_succeeded: failure_messages.append(f"Foot Angle (Best: {best_foot_angle_str}). Point toes down.")

         feedback_lines.append(f"❌ **Action Required!** Your High Leg March posture needs correction.")
         feedback_lines.append(f"The primary areas needing attention are: **{', '.join(failure_messages)}**.")
         feedback_lines.append("Please look at the annotated image for guidance.")

    feedback_lines.append("\n--- COMPONENT BREAKDOWN ---")
    feedback_lines.append(f"✅ Knee Height: {'Achieved' if knee_height_succeeded else '❌ FAIL - Lift higher!'}")
    feedback_lines.append(f"✅ Active Leg Angle: {'Correct range' if knee_angle_succeeded else f'❌ FAIL - Best angles: Hip {best_hip_angle_str}, Knee {best_knee_angle_str}'}")
    feedback_lines.append(f"✅ Stationary Leg: {'Locked' if stationary_leg_succeeded else '❌ FAIL - Brace that knee!'}")
    feedback_lines.append(f"✅ Foot Angle: {'Correct' if foot_angle_succeeded else f'❌ FAIL - Point toes down! Best angle: {best_foot_angle_str}'}")

    final_text_report = "\n".join(feedback_lines)

    # Annotate and Encode the chosen frame
    image_b64_data = []
    if frame_to_use_for_annotation is not None and last_known_landmarks is not None:
        visual_image = draw_and_annotate(
            frame_to_use_for_annotation.copy(),
            last_known_landmarks,
            fail_points_for_annotation,
            "HIGH LEG MARCH (VIDEO)",
            angles=angles_to_display
        )
        _, buffer = cv2.imencode('.jpg', visual_image)
        image_b64_data = [f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"]

    return {"image_b64_array": image_b64_data, "feedback": final_text_report}

