Generate speech audio from text using a TTS (text-to-speech) provider (Minimax).

This is a synchronous call — it returns after the audio file is generated and downloaded.

**Voice options:**
- `voice_id`: Voice identifier (default: "male-qn-qingse"). Available voices depend on the provider.
- `speed`: Speech speed, range 0.5-2.0 (default: 1.0)
- `vol`: Volume, range 0.1-10.0 (default: 1.0)
- `pitch`: Pitch adjustment, range -12 to 12 (default: 0)
- `language`: Language code, "zh" for Chinese or "en" for English (default: "zh")

**Important:** This tool calls a paid external API. The user will be asked for approval before generation.
