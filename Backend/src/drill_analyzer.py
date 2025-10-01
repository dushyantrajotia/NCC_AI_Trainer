from pose_utils import calculate_angle

def analyze_attention_pose(landmarks, image_shape, mp_pose):
    """
    Analyze Attention / Stand At Ease pose.
    Returns feedback list for a single frame.
    """
    h, w, _ = image_shape
    feedback = []

    # Left leg (hip-knee-ankle)
    hip = (int(landmarks[mp_pose.PoseLandmark.LEFT_HIP].x * w),
           int(landmarks[mp_pose.PoseLandmark.LEFT_HIP].y * h))
    knee = (int(landmarks[mp_pose.PoseLandmark.LEFT_KNEE].x * w),
            int(landmarks[mp_pose.PoseLandmark.LEFT_KNEE].y * h))
    ankle = (int(landmarks[mp_pose.PoseLandmark.LEFT_ANKLE].x * w),
             int(landmarks[mp_pose.PoseLandmark.LEFT_ANKLE].y * h))

    left_leg_angle = calculate_angle(hip, knee, ankle)
    if 80 <= left_leg_angle <= 100:
        feedback.append("✅ Left leg lifted ~90°")
    else:
        feedback.append(f"❌ Left leg angle off: {int(left_leg_angle)}°")

    # Right leg
    hip = (int(landmarks[mp_pose.PoseLandmark.RIGHT_HIP].x * w),
           int(landmarks[mp_pose.PoseLandmark.RIGHT_HIP].y * h))
    knee = (int(landmarks[mp_pose.PoseLandmark.RIGHT_KNEE].x * w),
            int(landmarks[mp_pose.PoseLandmark.RIGHT_KNEE].y * h))
    ankle = (int(landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE].x * w),
             int(landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE].y * h))

    right_leg_angle = calculate_angle(hip, knee, ankle)
    if 80 <= right_leg_angle <= 100:
        feedback.append("✅ Right leg lifted ~90°")
    else:
        feedback.append(f"❌ Right leg angle off: {int(right_leg_angle)}°")

    # Shoulders check
    left_shoulder = (int(landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER].x * w),
                     int(landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER].y * h))
    right_shoulder = (int(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER].x * w),
                      int(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER].y * h))

    shoulder_diff = abs(left_shoulder[1] - right_shoulder[1])
    if shoulder_diff < 20:
        feedback.append("✅ Shoulders level")
    else:
        feedback.append("❌ Shoulders not level")

    return feedback
