import subprocess
import json
import os
import shutil
from typing import Optional, Dict, Any
from models.video_info import VideoInfo, AudioStream
from logger import setup_logger

logger = setup_logger()

class FFprobeWrapper:
    def __init__(self):
        self.ffprobe_path = shutil.which("ffprobe")
        if not self.ffprobe_path:
            logger.error("FFprobe not found in system PATH")
            raise FileNotFoundError("FFprobe not found. Please install FFmpeg.")

    def get_video_info(self, file_path: str) -> Optional[VideoInfo]:
        """
        Runs ffprobe on the file and returns a VideoInfo object.
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None

        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            if result.returncode != 0:
                logger.error(f"FFprobe failed for {file_path}: {result.stderr}")
                return None

            data = json.loads(result.stdout)
            return self._parse_json(data, file_path)

        except Exception as e:
            logger.error(f"Error parsing metadata for {file_path}: {e}")
            return None

    def _parse_json(self, data: Dict[str, Any], file_path: str) -> VideoInfo:
        streams = data.get("streams", [])
        fmt = data.get("format", {})

        # Find Video Stream
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        # Find Audio Stream existing (just checking existence of any audio)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        # Check subtitles
        subtitle_stream = next((s for s in streams if s.get("codec_type") == "subtitle"), None)

        codec_video = video_stream.get("codec_name", "unknown") if video_stream else "none"
        codec_audio = audio_stream.get("codec_name", "unknown") if audio_stream else "none"

        audio_streams_list = []
        for s in streams:
            if s.get("codec_type") == "audio":
                audio_streams_list.append(AudioStream(
                    index=s.get("index", 0),
                    codec=s.get("codec_name", "unknown"),
                    channels=int(s.get("channels", 0)),
                    language=s.get("tags", {}).get("language", "und")
                ))
        
        width = int(video_stream.get("width", 0)) if video_stream else 0
        height = int(video_stream.get("height", 0)) if video_stream else 0
        
        # Calculate bitrate if missing in format
        bitrate = int(fmt.get("bit_rate", 0))
        duration = float(fmt.get("duration", 0))
        size_bytes = int(fmt.get("size", 0))
        size_mb = size_bytes / (1024 * 1024)

        container = fmt.get("format_name", "unknown").split(",")[0] # e.g. "mov,mp4,m4a,3gp,3g2,mj2" -> "mov"

        return VideoInfo(
            path=file_path,
            codec_video=codec_video,
            codec_audio=codec_audio,
            resolution=(width, height),
            bitrate=bitrate,
            container_format=container,
            has_subtitles=bool(subtitle_stream),
            duration_seconds=duration,
            size_mb=size_mb,
            audio_streams=audio_streams_list
        )
