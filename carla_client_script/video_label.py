"""Annotate the traffic demo using manually selected action time intervals.

The overlay is an illustration, not telemetry extracted from dispatcher logs.
"""

import cv2


def draw_hud(frame, action):
    # Action colors in OpenCV BGR order.
    COLORS = {
        "FOLLOW_LANE": (60, 180, 75),  # Green
        "SLOW_DOWN": (30, 165, 245),  # Orange
        "STOP": (50, 50, 220),  # Red
    }
    status_color = COLORS.get(action, (200, 200, 200))

    # Copy the frame for alpha blending.
    overlay = frame.copy()

    # Text font and hierarchy.
    font = cv2.FONT_HERSHEY_SIMPLEX
    header = "CURRENT ACTION"

    # Text sizes.
    h_scale, h_thick = 0.4, 1
    a_scale, a_thick = 0.7, 2

    # Measure the text dimensions in pixels.
    (hw, hh), _ = cv2.getTextSize(header, font, h_scale, h_thick)
    (aw, ah), _ = cv2.getTextSize(action, font, a_scale, a_thick)

    # Overlay box dimensions.
    pad_x, pad_y = 15, 12
    box_w = max(hw, aw) + (pad_x * 2) + 10
    box_h = hh + ah + (pad_y * 2) + 8
    x, y = 35, 35  # Top-left corner

    # 1. Draw the dark overlay background.
    cv2.rectangle(overlay, (x, y), (x + box_w, y + box_h), (15, 15, 15), -1)

    # 2. Blend the overlay with the original frame (alpha = 0.65).
    alpha = 0.65
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    # 3. Draw the vertical status indicator on the left.
    cv2.rectangle(frame, (x, y), (x + 4, y + box_h), status_color, -1)

    # 4. Draw the secondary heading in light gray.
    cv2.putText(
        frame,
        header,
        (x + pad_x + 4, y + pad_y + hh),
        font,
        h_scale,
        (170, 170, 170),
        h_thick,
        cv2.LINE_AA,
    )

    # 5. Draw the framework action in white.
    cv2.putText(
        frame,
        action,
        (x + pad_x + 4, y + pad_y + hh + ah + 8),
        font,
        a_scale,
        (255, 255, 255),
        a_thick,
        cv2.LINE_AA,
    )


def annotate_video(input_path, output_path):
    # Open the input video.
    cap = cv2.VideoCapture(input_path)

    if not cap.isOpened():
        print(f"Error: Could not open file {input_path}")
        return

    # Read the source video properties.
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Configure the MP4 codec and video writer.
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_count = 0

    print(f"Processing video... ({total_frames} frames at {fps:.2f} FPS)")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Calculate elapsed time in seconds.
        current_time = frame_count / fps
        action_text = ""

        # Select the manually assigned action for this time interval.
        if 2 <= current_time < 6:
            action_text = "FOLLOW_LANE"
        elif 6 <= current_time < 19:
            action_text = "SLOW_DOWN"
        elif 19 <= current_time < 24:
            action_text = "STOP"
        elif 24 <= current_time <= 31:
            action_text = "SLOW_DOWN"

        # Draw the overlay when this interval has an assigned action.
        if action_text:
            draw_hud(frame, action_text)

        # Write the annotated frame.
        out.write(frame)
        frame_count += 1

        # Report progress approximately every five seconds of video.
        if frame_count % int(fps * 5) == 0:
            print(f"Progress: {frame_count}/{total_frames} frames...")

    # Release video resources.
    cap.release()
    out.release()
    print(f"Processing complete. Video saved to: {output_path}")


if __name__ == "__main__":
    # Input and output filenames.
    input_video = "traf.mp4"
    output_video = "traf_annotated.mp4"

    annotate_video(input_video, output_video)
