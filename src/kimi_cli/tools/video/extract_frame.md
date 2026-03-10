Extract a single frame from a video file and save it as an image.

Use this tool to:
- Extract the last frame of a clip for continuity with the next shot (pass it as `reference_image_path` to GenerateVideo in `image_to_video` mode).
- Extract the first frame to verify the starting point of a generated clip.
- Extract a frame at a specific timestamp for reference or analysis.

Parameters:
- `video_path`: Path to the source video file.
- `output_path`: Path to save the extracted frame image (e.g. `assets/images/shot_01_lastframe.png`).
- `position`: Where to extract the frame — `"last"`, `"first"`, or a timestamp in seconds (e.g. `"2.5"`). Defaults to `"last"`.
