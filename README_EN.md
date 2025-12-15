media-normalizer

media-normalizer is a background service that automatically normalizes video files
in a media library.

It scans directories recursively, analyzes media streams using ffprobe, and converts
files into a unified, Direct-Play-friendly format optimized for Jellyfin / Plex / browsers.

Designed to run as a daemon or in cron mode.
Works well in Docker and on low-power systems (NAS, Raspberry Pi, VPS).



CORE IDEA

Do not re-encode everything blindly.

Instead:
    - inspect actual media streams
    - keep video untouched if it is already H.264 / H.265
    - re-encode audio only when it is incompatible (AC3, DTS, etc.)
    - remux everything into a clean MP4 container suitable for Direct Play



FEATURES

    - Recursive directory scanning
    - Media analysis via ffprobe
    - H.264 / H.265 support (CPU or NVENC)
    - Automatic audio normalization to AAC
    - Decision-based processing (skip / repack / transcode)
    - Atomic replacement of original files after success
    - Thread limiting (NAS / Raspberry friendly)
    - Continuous (daemon) mode
    - Cron / one-shot mode
    - Docker-ready architecture



HOW IT WORKS

1. Scanner
       - Recursively scans the source directory
       - Filters files by extension and minimum size
       - Produces a list of valid candidates

2. Analyzer
       - Runs ffprobe
       - Detects:
             * video codec
             * audio codec
             * resolution
             * container format

3. Decision Engine
       - Decides one of:
             * SKIP       — already compliant
             * REPACK     — container or audio fix only
             * TRANSCODE  — full conversion

4. Converter
       - Executes ffmpeg
       - Uses NVENC or CPU encoding
       - Writes to a temporary file
       - Atomically replaces the original on success



SUPPORTED FORMATS

Input:
       - mkv
       - mp4
       - avi

Output:
       - mp4 (H.264 / H.265 + AAC)



CONFIGURATION (YAML)

Example:

    source_path: "\\\\192.168.72.23\\Video"

    mode: continuous        # continuous | cron
    threads: 1

    skip_small_files_mb: 50

    video_codec: h264       # h264 | h265
    nvenc: true

    audio_codec: aac
    audio_bitrate: 192k

    extensions:
        - mkv
        - mp4
        - avi



TYPICAL USE CASES

Jellyfin / Plex:
       - Reliable Direct Play
       - No “video plays but no audio”
       - Reduced server transcoding load

NAS / Raspberry Pi:
       - Runs in 1–2 threads
       - Background daemon
       - No CPU spikes

Large media libraries:
       - Processes only new or non-compliant files
       - Leaves already normalized files untouched



DOCKER (PLANNED FOR v2.0)

       - One container = one daemon
       - Bind-mounted media library
       - Minimal permissions
       - Runs on any Docker-capable host



PROJECT STATUS

Pet project, but:
       - used on a real media library
       - solves real Direct Play issues
       - not tied to Jellyfin / Plex APIs



WHO IS THIS FOR

       - NAS owners
       - Jellyfin / Plex users
       - Anyone who does not want to manually re-encode terabytes
       - People who value stability over theoretical max quality
