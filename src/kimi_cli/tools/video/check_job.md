Check the status of a video generation job submitted via GenerateVideo.

Returns the current state (pending, processing, completed, or failed) and progress percentage.

When the job is completed and a `download_path` is provided, the generated video is automatically downloaded to that path.

Typical usage pattern:
1. Call GenerateVideo to submit a job and get a job_id
2. Wait a few seconds
3. Call CheckVideoJob with the job_id and provider
4. If still processing, wait and check again
5. Once completed, the video is ready at the download_path
