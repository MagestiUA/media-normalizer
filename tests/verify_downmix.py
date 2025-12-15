import sys
import os
import logging
from unittest.mock import MagicMock

# Add parent dir to path so we can import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.video_info import VideoInfo, AudioStream
from converter import Converter
from analyzer import Action, Analyzer

# Setup mock logger to avoid clutter
logging.basicConfig(level=logging.INFO)

def test_stereo_downmix_command_generation():
    print("Testing Stereo Downmix Command Generation...")
    
    # 1. Create Mock Config
    config = {
        "video_bitrate": {"1080p": "4M", "2160p": "12M", "720p": "2M"},
        "audio_bitrate": "128k",
        "nvenc_preset": "p4",
        "allow_hevc": False,
        "keep_subtitles": False
    }

    # 2. Create Mock Converter
    # We mock shutil.which so it doesn't fail if ffmpeg is missing (though it likely exists)
    # But checking for mapped drives, better to rely on real one or mock the init check.
    # Let's just instantiate, assuming ffmpeg is in path (it is based on file listing)
    try:
        converter = Converter(config)
    except FileNotFoundError:
        print("SKIP: ffmpeg not found.")
        return

    # Mock _run_ffmpeg so we don't actually run it
    converter._run_ffmpeg = MagicMock(return_value=True)

    # 3. Create Mock VideoInfo with 5.1 Audio
    info = VideoInfo(
        path="C:\\Videos\\movie.mkv",
        codec_video="h264",
        codec_audio="ac3",
        resolution=(1920, 1080),
        bitrate=5000000,
        container_format="matroska",
        has_subtitles=False,
        duration_seconds=120,
        size_mb=100,
        audio_streams=[
            AudioStream(index=1, codec="ac3", channels=6, language="eng") # 5.1
        ]
    )
    info.needed_downmixes = [1]

    # 4. Run Process (EXTERNAL_AUDIO action)
    converter.process(info, Action.EXTERNAL_AUDIO)

    # 5. Inspect the called command
    args, _ = converter._run_ffmpeg.call_args
    if not args:
        print("[FAIL] No FFmpeg call made.")
        return
        
    cmd = args[0]
    
    # We expect:
    # - Video copy (since codec is h264)
    # - Audio stream 0 (original) converted to AAC (or copied if we change logic)
    # - Audio stream 0 (downmix) added as new stream
    
    cmd_str = " ".join(cmd)
    print(f"Generated Command: {cmd_str}")

    # Check for External Audio Extraction
    if "movie.eng.stereo.m4a" in cmd_str:
         print("[PASS] External Audio filename correct.")
    else:
         print(f"[FAIL] Filename check failed. Expected 'movie.eng.stereo.m4a' in {cmd_str}")

    if "-vn" in cmd_str and "-ac 2" in cmd_str:
         print("[PASS] External Audio flags (-vn, -ac 2) confirmed.")
    else:
         print("[FAIL] Flags check failed.")

def test_analyzer_logic():
    print("\nTesting Analyzer Logic...")
    config = {"allow_hevc": False}
    analyzer = Analyzer(config)
    
    # Mock Info: Valid MP4 (h264) + 5.1 -> Should trigger EXTERNAL_AUDIO
    info = VideoInfo(
        path="movie.mp4",
        codec_video="h264",
        codec_audio="aac",
        resolution=(1920, 1080),
        bitrate=10,
        container_format="mp4",
        has_subtitles=False,
        duration_seconds=100,
        size_mb=10,
        audio_streams=[
            AudioStream(index=0, codec="aac", channels=6, language="uk")
        ]
    )
    
    action = analyzer.analyze(info)
    print(f"Action returned: {action}")
    
    if action == Action.EXTERNAL_AUDIO:
        print("[PASS] Analyzer correctly returned EXTERNAL_AUDIO.")
    else:
        print(f"[FAIL] Analyzer returned {action} instead of EXTERNAL_AUDIO.")

    # Mock Info: MKV + 5.1 -> Should trigger TRANSCODE (Standardization)
    info_mkv = VideoInfo(
        path="movie.mkv",
        codec_video="h264",
        codec_audio="ac3",
        resolution=(1920, 1080),
        bitrate=10,
        container_format="matroska",
        has_subtitles=False,
        duration_seconds=100,
        size_mb=10,
        audio_streams=[
            AudioStream(index=0, codec="ac3", channels=6, language="uk")
        ]
    )
    action2 = analyzer.analyze(info_mkv)
    if action2 == Action.TRANSCODE:
         print("[PASS] MKV triggers TRANSCODE (Standard Pipeline).")
    else:
         print(f"[FAIL] MKV triggered {action2}.")

    # Mock Info: MP4 + 5.1 UKR + 2.0 UKR -> Should pass (already good)
    info_good = VideoInfo(
        path="good.mp4",
        codec_video="h264",
        codec_audio="aac",
        resolution=(1920, 1080),
        bitrate=10,
        container_format="mp4",
        has_subtitles=False,
        duration_seconds=100,
        size_mb=10,
        audio_streams=[
            AudioStream(index=0, codec="aac", channels=6, language="uk"),
            AudioStream(index=1, codec="aac", channels=2, language="uk")
        ]
    )
    action_pass = analyzer.analyze(info_good)
    if action_pass == Action.PASS:
        print("[PASS] Smart Logic: Skipped 5.1 because 2.0 exists (Same Language).")
    else:
        print(f"[FAIL] Smart Logic failed. Expected PASS, got {action_pass}")

    # Mock Info: MP4 + 5.1 ENG (No Stereo) + 5.1 UKR (Has Stereo)
    info_mixed = VideoInfo(
        path="mixed.mp4",
        codec_video="h264",
        codec_audio="aac",
        resolution=(1920, 1080),
        bitrate=10,
        container_format="mp4",
        has_subtitles=False,
        duration_seconds=100,
        size_mb=10,
        audio_streams=[
            AudioStream(index=0, codec="aac", channels=6, language="eng"), # Needs stereo
            AudioStream(index=1, codec="aac", channels=6, language="uk"),
            AudioStream(index=2, codec="aac", channels=2, language="uk")
        ]
    )
    action_mixed = analyzer.analyze(info_mixed)
    if action_mixed == Action.EXTERNAL_AUDIO:
        print(f"[PASS] Smart Logic: Triggered EXTERNAL_AUDIO for mixed case.")
        if 0 in info_mixed.needed_downmixes and 1 not in info_mixed.needed_downmixes:
             print("[PASS] Correctly identified only Stream #0 needs downmix.")
        else:
             print(f"[FAIL] Incorrect needed_downmixes: {info_mixed.needed_downmixes}")
    else:
        print(f"[FAIL] Mixed case failed. Got {action_mixed}")

if __name__ == "__main__":
    test_stereo_downmix_command_generation()
    test_analyzer_logic()
