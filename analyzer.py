from enum import Enum, auto
import os
from typing import Dict
from models.video_info import VideoInfo
from logger import setup_logger

logger = setup_logger()

class Action(Enum):
    PASS = auto()
    REMUX = auto()
    TRANSCODE = auto()
    EXTERNAL_AUDIO = auto()

class Analyzer:
    def __init__(self, config: Dict):
        self.config = config

    def analyze(self, info: VideoInfo) -> Action:
        """
        Determines the required action for a video file based on its properties.
        """
        ext = os.path.splitext(info.path)[1].lower()
        
        # Define acceptable video codecs
        acceptable_video_codecs = ["h264", "avc1"]
        if self.config.get("allow_hevc", False):
            acceptable_video_codecs.extend(["hevc", "h265"])

        is_valid_video = info.codec_video.lower() in acceptable_video_codecs
        is_h264_video = info.codec_video.lower() in ["h264", "avc1"]
        is_aac_audio = info.codec_audio.lower() in ["aac", "none"]

        # Check for multi-channel audio (needs downmix)
        # Smart Logic: For every stream > 2 channels, check if there is a <=2 ch stream with SAME language
        needed_indices = []
        for s in info.audio_streams:
            if s.channels > 2:
                # Look for a stereo pair
                has_stereo_pair = False
                for other in info.audio_streams:
                    if other.index == s.index: continue
                    if other.channels <= 2 and other.language == s.language:
                        has_stereo_pair = True
                        pair_index = other.index
                        break
                
                # Check if external file exists
                # Construct expected filename to check
                base_name = os.path.splitext(info.path)[0]
                lang_code = s.language if s.language != "und" else "uk" # heuristic
                external_check = f"{base_name}.{lang_code}.stereo.m4a"
                
                if has_stereo_pair:
                    logger.info(f"  [Analyzer] Stream #{s.index} ({s.channels}ch, {s.language}): Found internal stereo pair #{pair_index}. Skipping.")
                    continue # Valid
                elif os.path.exists(external_check):
                     logger.info(f"  [Analyzer] Stream #{s.index} ({s.channels}ch, {s.language}): Found external stereo file. Skipping.")
                     continue # Valid because external file exists
                else:
                    logger.info(f"  [Analyzer] Stream #{s.index} ({s.channels}ch, {s.language}): No stereo pair found. Queueing downmix.")
                    needed_indices.append(s.index)

        info.needed_downmixes = needed_indices
        has_multichannel_work = len(needed_indices) > 0

        # 1. MP4 Logic
        if ext == ".mp4":
            if is_valid_video and is_aac_audio and not has_multichannel_work:
                info.reason = f"Already standardized (MP4/{info.codec_video}/{info.codec_audio})"
                return Action.PASS
            elif has_multichannel_work:
                 info.reason = f"Multi-channel audio detected ({len(needed_indices)} streams missing stereo). Generating external stereo track(s)."
                 return Action.EXTERNAL_AUDIO
            else:
                 info.reason = f"MP4 with non-standard codecs (Video: {info.codec_video}, Audio: {info.codec_audio})"
                 return Action.TRANSCODE

        # 2. Non-MP4 Logic
        # Check if we can just REMUX (Fast copy)
        # Use is_valid_video (which includes HEVC if config allows)
        if is_valid_video and is_aac_audio and not has_multichannel_work:
             info.reason = f"Remux needed (Container: {info.container_format} -> MP4)"
             return Action.REMUX

        # 3. Everything else -> TRANSCODE
        reasons = []
        if not is_valid_video:
            reasons.append(f"Video {info.codec_video}")
        if not is_aac_audio:
            reasons.append(f"Audio {info.codec_audio}")
        info.reason = f"Transcode needed ({', '.join(reasons)})"
        return Action.TRANSCODE
