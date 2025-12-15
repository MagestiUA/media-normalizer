from pydantic import BaseModel
from typing import Tuple, Optional

class AudioStream(BaseModel):
    index: int
    codec: str
    channels: int
    language: str = "und"

class VideoInfo(BaseModel):
    path: str
    codec_video: str
    codec_audio: str # Main audio codec (compatibility)
    audio_streams: list[AudioStream] = []
    resolution: Tuple[int, int]
    bitrate: int
    container_format: str
    has_subtitles: bool
    duration_seconds: float
    size_mb: float
    reason: str = "" # To store analysis reason
    needed_downmixes: list[int] = [] # Indices of streams that need stereo version
