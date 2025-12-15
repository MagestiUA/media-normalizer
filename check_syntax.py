import sys
import os

# Add local path to sys.path
sys.path.append(os.getcwd())

try:
    from models.video_info import VideoInfo, AudioStream
    from utils.ffprobe_wrapper import FFprobeWrapper
    from analyzer import Analyzer, Action
    from converter import Converter
    print("Imports successful. Syntax looks OK.")
except Exception as e:
    print(f"Syntax/Import Error: {e}")
    sys.exit(1)
