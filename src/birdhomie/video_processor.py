"""Video processing module for frame extraction and annotation."""

import logging
import subprocess
from pathlib import Path
from typing import Iterator, Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class VideoFrameExtractor:
    """Extracts frames from video files."""

    def __init__(self, frame_skip: int = 5):
        """Initialize the frame extractor.

        Args:
            frame_skip: Process every Nth frame
        """
        self.frame_skip = frame_skip

    def get_video_info(self, video_path: Path) -> dict:
        """Get video metadata.

        Args:
            video_path: Path to video file

        Returns:
            Dictionary with fps, width, height, total_frames
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        info = {
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        }
        cap.release()
        return info

    def extract_frames(self, video_path: Path) -> Iterator[Tuple[int, np.ndarray]]:
        """Extract frames from video.

        Args:
            video_path: Path to video file

        Yields:
            Tuple of (frame_index, frame_array)
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        frame_idx = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % self.frame_skip == 0:
                    yield frame_idx, frame

                frame_idx += 1
        finally:
            cap.release()


class VideoAnnotator:
    """Creates annotated videos with detection boxes."""

    def __init__(self):
        """Initialize the video annotator."""
        pass

    def create_annotated_video(
        self,
        video_path: Path,
        output_path: Path,
        frame_skip: int,
        detections_by_frame: dict,
    ) -> None:
        """Create an annotated video with detection boxes.

        Args:
            video_path: Input video path
            output_path: Output video path
            frame_skip: Frame skip interval used during processing
            detections_by_frame: Dict mapping frame_idx to list of detections
        """
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Create temporary output with codec that works
        temp_path = output_path.with_suffix(".temp.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(temp_path), fourcc, fps, (width, height))

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # If this frame was processed, annotate it
            if frame_idx in detections_by_frame:
                annotated_frame = frame.copy()
                for det in detections_by_frame[frame_idx]:
                    x1, y1, x2, y2 = det["bbox"]
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    conf_text = f"{det['confidence']:.2f}"
                    cv2.putText(
                        annotated_frame,
                        conf_text,
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        2,
                    )
                out.write(annotated_frame)
            else:
                out.write(frame)

            frame_idx += 1

        cap.release()
        out.release()

        # Convert to H.264 for browser compatibility
        self._convert_to_h264(temp_path, output_path)

    def _convert_to_h264(self, input_path: Path, output_path: Path):
        """Convert video to H.264 codec for browser compatibility.

        Args:
            input_path: Input video path
            output_path: Output video path
        """
        try:
            # Try hardware acceleration first (macOS)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(input_path),
                    "-c:v",
                    "h264_videotoolbox",
                    "-b:v",
                    "5M",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )
            input_path.unlink()
            logger.info("video_converted_h264", extra={"path": str(output_path)})
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            # Fallback to software encoding
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(input_path),
                        "-c:v",
                        "libx264",
                        "-preset",
                        "fast",
                        "-crf",
                        "23",
                        "-c:a",
                        "aac",
                        "-movflags",
                        "+faststart",
                        str(output_path),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=300,
                )
                input_path.unlink()
                logger.info(
                    "video_converted_h264_software", extra={"path": str(output_path)}
                )
            except Exception as e:
                input_path.rename(output_path)
                logger.warning("video_conversion_failed", extra={"error": str(e)})
