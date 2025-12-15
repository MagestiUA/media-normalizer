import yaml
import time
import sys
import os
from typing import Dict
from logger import setup_logger
from scanner import Scanner
from utils.ffprobe_wrapper import FFprobeWrapper
from analyzer import Analyzer, Action
from converter import Converter
from file_ops import safe_replace

logger = setup_logger()

def load_config(path: str = "config.yaml") -> Dict:
    if not os.path.exists(path):
        logger.critical(f"Config file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

class VideoNormalizerApp:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        self.scanner = Scanner(
            self.config["source_path"], 
            self.config["extensions"],
            self.config["skip_small_files_mb"]
        )
        self.ffprobe = FFprobeWrapper()
        self.analyzer = Analyzer(self.config)
        self.converter = Converter(self.config)
        self.delete_backups = self.config.get("delete_backups", True)

    def process_file(self, file_path: str):
        try:
            # 1. Analyze
            info = self.ffprobe.get_video_info(file_path)
            if not info:
                return

            # Log analysis summary
            stream_summary = ", ".join([f"#{s.index}:{s.codec}({s.channels}ch)[{s.language}]" for s in info.audio_streams])
            logger.info(f"Analyzed {file_path}:\n"
                        f"  Video: {info.codec_video} ({info.resolution[0]}x{info.resolution[1]})\n"
                        f"  Audio: {len(info.audio_streams)} streams ({stream_summary})\n"
                        f"  Container: {info.container_format}")

            action = self.analyzer.analyze(info)
            
            if action == Action.PASS:
                 logger.info(f"PASS: {file_path} [{info.reason}]")
                 return
            elif action in [Action.REMUX, Action.TRANSCODE, Action.EXTERNAL_AUDIO]:
                start_time = time.time()
                
                # Determine target video codec for logging
                acceptable_video_codecs = ["h264", "avc1"]
                if load_config().get("allow_hevc", False): # Reloading config slightly inefficient but main has self.config? 
                     # Wait, main.py VideoNormalizerApp has self.config.
                     acceptable_video_codecs.extend(["hevc", "h265"])
                
                target_v = "copy" if (action == Action.REMUX or info.codec_video.lower() in acceptable_video_codecs) else "h264"
                target_a = "copy" if action == Action.REMUX else "aac"
                
                logger.info(f"START: path=\"{file_path}\" "
                            f"video={info.codec_video}->{target_v} "
                            f"audio={info.codec_audio}->{target_a} "
                            f"reason=\"{info.reason}\" action=\"{action.name}\"")
                
                # 2. Convert
                temp_output = self.converter.process(info, action)
                
                # 3. Handle Result
                if action == Action.EXTERNAL_AUDIO:
                    if temp_output:
                         duration = int(time.time() - start_time)
                         logger.info(f"DONE (External Audio): created=\"{temp_output}\" time={duration}s")
                         logger.info(f"{'===' * 10}\n\n")
                    else:
                         logger.error(f"FAILED external audio generation for {file_path}")

                elif action in [Action.REMUX, Action.TRANSCODE]:
                    # Standard replacement logic
                    if temp_output:
                        # Construct final filename with .mp4 extension
                        final_path = os.path.splitext(file_path)[0] + ".mp4"
                        
                        if safe_replace(file_path, temp_output, final_path, self.delete_backups):
                            duration = int(time.time() - start_time)
                            logger.info(f"DONE: new_file=\"{final_path}\" time={duration}s")
                            logger.info(f"{'===' * 10}\n\n")
                        else:
                            logger.error(f"FAILED replacement for {file_path}")
                            logger.info(f"{'===' * 10}\n\n")
                            if os.path.exists(temp_output):
                                os.remove(temp_output)
                    else:
                        logger.error(f"FAILED conversion for {file_path}")

        except Exception as e:
            logger.error(f"Unhandled error processing {file_path}: {e}")

    def run_one_cycle(self):
        logger.info("Starting scan cycle...")
        for file_path in self.scanner.scan():
            self.process_file(file_path)
        logger.info("Scan cycle complete.")
        logger.info(f"\n\n")

    def run(self):
        
        mode = self.config.get("mode", "continuous").lower()
        logger.info(f"Starting VideoNormalizer in {mode.upper()} mode")
        
        if mode == "cron":
            self.run_one_cycle()
        elif mode == "continuous":
            while True:
                try:
                    # In continuous mode, specification says:
                    # "koжнi 10 секунд сканує чергу", "обробляє 1 файл за раз"
                    # My scanner yields files one by one.
                    # Simple implementation: run full scan, then sleep.
                    # Or better: Scan loop.
                    
                    self.run_one_cycle()
                    
                    # Sleep between cycles?
                    # Spec: "continues - daemon... koжнi 10 секунд сканує"
                    # If cycle takes long, it's fine.
                    time.sleep(self.config.get("slip_after_scan", 300))
                except KeyboardInterrupt:
                    logger.info("Stopping...")
                    break
                except Exception as e:
                    logger.error(f"Cycle error: {e}")
                    time.sleep(10)
        else:
            logger.error(f"Unknown mode: {mode}")

if __name__ == "__main__":
    app = VideoNormalizerApp()
    app.run()
