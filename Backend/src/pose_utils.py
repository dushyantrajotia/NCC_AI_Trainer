import math

def calculate_angle(a, b, c):
    """
    Calculate angle in degrees between three points (a-b-c), with the angle centered at point b.
    Each point is expected to be a tuple (x, y).
    """
    # Calculate angle for vector BA and vector BC using atan2
    ang = math.degrees(
        math.atan2(c[1] - b[1], c[0] - b[0]) - 
        math.atan2(a[1] - b[1], a[0] - b[0])
    )
    
    # Take the absolute value
    ang = abs(ang)
    
    # Convert angle to always be between 0 and 180 degrees
    if ang > 180:
        ang = 360 - ang
    
    return ang