Generate a detailed caption for a video using a VLM (vision-language model). Describes the scene, characters, actions, camera work, visual style, and progression of events. Also returns objective metadata (duration, resolution, fps) via ffprobe.

Parameters:
- `video_path`: Path to the video file.

Returns video metadata and a detailed text description of the video content.