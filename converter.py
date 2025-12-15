import subprocess
import os
import shutil
from typing import Optional, Dict
from models.video_info import VideoInfo
from analyzer import Action
from logger import setup_logger

logger = setup_logger()

class Converter:
    def __init__(self, config: Dict):
        self.config = config
        self.ffmpeg_path = shutil.which("ffmpeg")
        if not self.ffmpeg_path:
             raise FileNotFoundError("FFmpeg not found")

    def process(self, info: VideoInfo, action: Action) -> Optional[str]:
        """
        Executes the conversion/remuxing and returns the path to the temporary output file.
        Returns None on failure.
        """
        output_temp = os.path.join(os.path.dirname(info.path), f"temp_{os.path.basename(info.path)}")
        # change extension to mp4
        output_temp = os.path.splitext(output_temp)[0] + ".mp4"
        
        try:
            if action == Action.REMUX:
                success = self._remux(info.path, output_temp)
            elif action == Action.TRANSCODE:
                success = self._transcode(info, output_temp)
            elif action == Action.EXTERNAL_AUDIO:
                return self._extract_audio(info)
            else:
                return None
                
            if success:
                return output_temp
            return None
            
        except Exception as e:
            logger.error(f"Processing failed for {info.path}: {e}")
            if os.path.exists(output_temp):
                os.remove(output_temp)
            return None

    def _remux(self, input_path: str, output_path: str) -> bool:
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-c", "copy",
            "-strict", "experimental", # Sometimes needed
            output_path
        ]
        logger.info(f"Starting REMUX: {input_path} -> {output_path}")
        return self._run_ffmpeg(cmd)

    def _transcode(self, info: VideoInfo, output_path: str) -> bool:
        # Determine bitrate based on resolution
        width, height = info.resolution
        pixels = width * height
        
        video_bitrate = self.config["video_bitrate"]["1080p"] # Default
        if pixels > 3000 * 1500: # 4Kish
            video_bitrate = self.config["video_bitrate"]["2160p"]
        elif pixels < 1500 * 900: # 720pish
            video_bitrate = self.config["video_bitrate"]["720p"]
            
        audio_bitrate = self.config["audio_bitrate"]
        preset = self.config["nvenc_preset"]

        # Build command
        cmd = [self.ffmpeg_path, "-y"]
        
        # Check acceleration
        hw_accel = self.config.get("hw_accel", "cuda")
        if hw_accel == "cuda":
            cmd.extend(["-hwaccel", "cuda"])
        
        cmd.extend(["-i", info.path])
        
        # 1. Video Processing
        cmd.extend(["-map", "0:v:0"]) # Map first video stream always
        
        acceptable_video_codecs = ["h264", "avc1"]
        if self.config.get("allow_hevc", False):
             acceptable_video_codecs.extend(["hevc", "h265"])

        if info.codec_video.lower() in acceptable_video_codecs:
             # Smart Transcode (Video Copy)
             cmd.extend(["-c:v", "copy"])
             video_status = "copy"
        else:
             # Full Transcode
             cmd.append("-pix_fmt")
             cmd.append("yuv420p")
             
             if hw_accel == "cuda":
                 cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-preset", preset,
                 ])
                 video_status = "h264_nvenc"
             else:
                 # CPU Mode
                 cpu_preset = self.config.get("cpu_preset", "veryfast")
                 cmd.extend([
                    "-c:v", "libx264",
                    "-preset", cpu_preset,
                    "-threads", str(self.config.get("threads", 4))
                 ])
                 video_status = "libx264"

             cmd.extend(["-b:v", video_bitrate])

        # 2. Audio Processing with Downmix Logic
        audio_log_info = []
        output_audio_idx = 0
        
        # If no streams found via strict parsing (fallback to old single stream if needed, 
        # but we updated ffprobe wrapper so it should be fine. If empty check primary codec)
        if not info.audio_streams and info.codec_audio != "none":
            # Fallback for old VideoInfo or error in parsing
             cmd.extend(["-map", "0:a", "-c:a", "aac", "-b:a", audio_bitrate])
        
        for i, stream in enumerate(info.audio_streams):
            # A. Process Original Stream
            cmd.extend(["-map", f"0:{stream.index}"])
            
            # If already AAC, copy it? 
            # Ideally yes to avoid quality loss, but user wants "standardization". 
            # Existing logic was forceful conversion. Let's stick to AAC conversion mostly 
            # unless it IS aac and channels match?
            # Let's simple: Copy if AAC, Convert if not.
            if stream.codec.lower() == "aac":
                cmd.extend([f"-c:a:{output_audio_idx}", "copy"])
                audio_log_info.append(f"Stream #{i}({stream.channels}ch)->Copy")
            else:
                cmd.extend([f"-c:a:{output_audio_idx}", "aac", f"-b:a:{output_audio_idx}", audio_bitrate])
                audio_log_info.append(f"Stream #{i}({stream.codec})->AAC")
            
            output_audio_idx += 1

            # B. Check for Downmix
            # Only downmix if this stream acts as a source for a NEEDED downmix
            if stream.index in info.needed_downmixes:
                # Add Stereo Downmix Track
                cmd.extend(["-map", f"0:{stream.index}"])
                cmd.extend([
                    f"-c:a:{output_audio_idx}", "aac",
                    f"-b:a:{output_audio_idx}", "192k", # Standard stereo bitrate
                    f"-ac:{output_audio_idx}", "2",
                    f"-metadata:s:a:{output_audio_idx}", f"title=Stereo (Downmix from {stream.channels}ch)"
                ])
                audio_log_info.append(f"Stream #{i}({stream.channels}ch)->Stereo Mix")
                output_audio_idx += 1

        # Handle subtitles
        if self.config.get("keep_subtitles", False):
            cmd.extend(["-c:s", "mov_text"])
        else:
            cmd.append("-sn")

        cmd.append(output_path)
            
        logger.info(f"Starting TRANSCODE: {info.path} -> {output_path} "
                    f"[{info.codec_video}->{video_status}] "
                    f"[Audio Ops: {', '.join(audio_log_info)}] "
                    f"[Video Bitrate: {video_bitrate if video_status != 'copy' else 'N/A'}]")
        return self._run_ffmpeg(cmd)

    def _extract_audio(self, info: VideoInfo) -> Optional[str]:
        """
        Extracts stereo audio from multi-channel source(s) to external file(s).
        Returns the path to the LAST generated audio file (or None if all failed).
        """
        generated_any = False
        last_output = None

        if not info.needed_downmixes:
             logger.warning("No downmixes needed despite EXTERNAL_AUDIO action.")
             return None

        # Resolve stream objects for indices
        target_streams = [s for s in info.audio_streams if s.index in info.needed_downmixes]
        
        for stream in target_streams:
            # Construct filename: [filename].[lang].stereo.m4a
            lang = stream.language if stream.language != "und" else "uk" 
            
            base_name = os.path.splitext(info.path)[0]
            # Handle potential collision if multiple streams have same language? 
            # E.g. 5.1 Eng (ac3) and 5.1 Eng (dts).
            # Analyzer usually checks if pair exists. But if we have 2 sources, we might just need 1 stereo?
            # Or make distinctive name: movie.eng.stereo.m4a. 
            # If exists, we skip in Analyzer. So here we assume we can write.
            
            output_audio = f"{base_name}.{lang}.stereo.m4a"
            
            if os.path.exists(output_audio):
                 logger.info(f"External audio already exists: {output_audio}")
                 continue

            cmd = [
                self.ffmpeg_path, "-y",
                "-i", info.path,
                "-map", f"0:{stream.index}",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ac", "2",
                "-vn", 
                "-sn", 
                output_audio
            ]
            
            logger.info(f"Generating EXTERNAL AUDIO: {output_audio} (from stream #{stream.index})")
            if self._run_ffmpeg(cmd):
                generated_any = True
                last_output = output_audio
        
        return last_output if generated_any else None

    def _run_ffmpeg(self, cmd: list) -> bool:
        try:
            # Using Popen to capture realtime output if needed, or run for blocking
            # For this simple implementation, blocking run is fine.
            # Added errors='replace' to handle potential non-UTF-8 characters in ffmpeg output (e.g. windows console encoding)
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"FFmpeg execution error: {e}")
            return False
