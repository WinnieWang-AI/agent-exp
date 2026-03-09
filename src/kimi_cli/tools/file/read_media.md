Read media content from a file.

**Tips:**
- Make sure you follow the description of each tool parameter.
- A `<system>` tag will be given before the read file content.
- The system will notify you when there is anything wrong when reading the file.
- This tool is a tool that you typically want to use in parallel. Always read multiple files in one response when possible.
- This tool can read image, video, and audio files. To read other types of files, use the ReadFile tool. To list directories, use the Glob tool or `ls` command via the Shell tool.
- If the file doesn't exist or path is invalid, an error will be returned.
- The maximum size that can be read is ${MAX_MEDIA_MEGABYTES}MB. An error will be returned if the file is larger than this limit.
- The media content will be returned in a form that you can directly view and understand.

**Capabilities**
- Audio files (mp3, wav, flac, etc.) are always supported.
{% if "image_in" in capabilities and "video_in" in capabilities %}
- Image and video files are supported by the current model.
{% elif "image_in" in capabilities %}
- Image files are supported by the current model. Video files are not.
{% elif "video_in" in capabilities %}
- Video files are supported by the current model. Image files are not.
{% else %}
- The current model does not support image or video input.
{% endif %}
