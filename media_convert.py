import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

VNOTE_MAX_SECONDS = 59
VNOTE_SIZE = 640

VOICE_MAX_SECONDS = 9 * 60 + 55


class FFmpegNotFoundError(RuntimeError):
    pass


class MediaConvertError(RuntimeError):
    pass


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError(
            "ffmpeg не найден в PATH. Установите ffmpeg для отправки кружков и голосовых."
        )
    return ffmpeg


def _run_ffmpeg(cmd: list[str]) -> None:
    _require_ffmpeg()
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stderr:
            logger.debug("ffmpeg: %s", result.stderr[-500:])
    except subprocess.CalledProcessError as exc:
        logger.error("ffmpeg failed: %s", exc.stderr[-1000:] if exc.stderr else exc)
        raise MediaConvertError("Ошибка конвертации медиафайла") from exc


def convert_to_video_note(input_path: str) -> str:
    """
    Квадрат 640×640, H.264 + AAC, MP4 — формат Telegram Video Note.
    """
    output_fd, output_path = tempfile.mkstemp(suffix=".mp4", prefix="vnote_")
    os.close(output_fd)

    vf = (
        "crop=min(iw\\,ih):min(iw\\,ih):(iw-min(iw\\,ih))/2:(ih-min(iw\\,ih))/2,"
        f"scale={VNOTE_SIZE}:{VNOTE_SIZE}"
    )

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        input_path,
        "-t",
        str(VNOTE_MAX_SECONDS),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        "-ac",
        "1",
        "-movflags",
        "+faststart",
        "-y",
        output_path,
    ]

    try:
        _run_ffmpeg(cmd)
        return output_path
    except Exception:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise


def convert_to_voice(input_path: str, max_duration: int = VOICE_MAX_SECONDS) -> str:
    """
    OGG Opus (mono, voip) — нативный формат голосовых сообщений Telegram.
    """
    output_fd, output_path = tempfile.mkstemp(suffix=".ogg", prefix="voice_")
    os.close(output_fd)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        input_path,
        "-t",
        str(max_duration),
        "-vn",
        "-ac",
        "1",
        "-c:a",
        "libopus",
        "-b:a",
        "64k",
        "-vbr",
        "on",
        "-application",
        "voip",
        "-compression_level",
        "10",
        "-y",
        output_path,
    ]

    try:
        _run_ffmpeg(cmd)
        return output_path
    except Exception:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise


def safe_remove(path: str | None) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            logger.warning("Failed to remove temp file: %s", path)
