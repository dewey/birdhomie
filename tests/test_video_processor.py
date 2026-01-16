"""Tests for video processing components."""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from pathlib import Path
from birdhomie.video_processor import VideoFrameExtractor, VideoAnnotator


class TestVideoFrameExtractor:
    """Test video frame extraction."""

    def test_initialization(self):
        """Test extractor initialization."""
        extractor = VideoFrameExtractor(frame_skip=10)
        assert extractor.frame_skip == 10

    @patch("birdhomie.video_processor.cv2.VideoCapture")
    def test_get_video_info(self, mock_cv2_cap):
        """Test getting video metadata."""
        # Mock video capture
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [30.0, 1920, 1080, 900]  # fps, width, height, frames
        mock_cv2_cap.return_value = mock_cap

        extractor = VideoFrameExtractor()
        info = extractor.get_video_info(Path("/test/video.mp4"))

        assert info["fps"] == 30.0
        assert info["width"] == 1920
        assert info["height"] == 1080
        assert info["total_frames"] == 900

    @patch("birdhomie.video_processor.cv2.VideoCapture")
    def test_get_video_info_unopenable_file(self, mock_cv2_cap):
        """Test handling of files that cannot be opened."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cv2_cap.return_value = mock_cap

        extractor = VideoFrameExtractor()

        with pytest.raises(ValueError, match="Could not open video"):
            extractor.get_video_info(Path("/test/bad_video.mp4"))

    @patch("birdhomie.video_processor.cv2.VideoCapture")
    def test_extract_frames_with_skip(self, mock_cv2_cap):
        """Test frame extraction with frame skipping."""
        # Mock video capture
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        # Simulate 20 frames total
        frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(20)]
        mock_cap.read.side_effect = [(True, frames[i]) for i in range(20)] + [
            (False, None)
        ]

        mock_cv2_cap.return_value = mock_cap

        extractor = VideoFrameExtractor(frame_skip=5)
        extracted = list(extractor.extract_frames(Path("/test/video.mp4")))

        # Should extract frames 0, 5, 10, 15 (every 5th frame)
        assert len(extracted) == 4
        frame_indices = [idx for idx, _ in extracted]
        assert frame_indices == [0, 5, 10, 15]

    @patch("birdhomie.video_processor.cv2.VideoCapture")
    def test_extract_frames_releases_capture(self, mock_cv2_cap):
        """Test that video capture is properly released."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.side_effect = [(False, None)]  # No frames
        mock_cv2_cap.return_value = mock_cap

        extractor = VideoFrameExtractor()
        list(extractor.extract_frames(Path("/test/video.mp4")))

        # Verify release was called
        mock_cap.release.assert_called_once()


class TestVideoAnnotator:
    """Test video annotation."""

    def test_initialization(self):
        """Test annotator initialization."""
        annotator = VideoAnnotator()
        assert annotator is not None

    @patch("birdhomie.video_processor.cv2.VideoCapture")
    @patch("birdhomie.video_processor.cv2.VideoWriter")
    @patch("birdhomie.video_processor.subprocess.run")
    @patch("birdhomie.video_processor.Path.unlink")
    def test_create_annotated_video_basic(
        self, mock_unlink, mock_subprocess, mock_writer, mock_capture
    ):
        """Test creating annotated video."""
        # Mock video capture
        mock_cap = MagicMock()
        mock_cap.get.side_effect = [30.0, 1920, 1080]
        mock_capture.return_value = mock_cap

        # Mock frame reading (3 frames)
        frames = [np.zeros((1080, 1920, 3), dtype=np.uint8) for _ in range(3)]
        mock_cap.read.side_effect = [(True, frames[i]) for i in range(3)] + [
            (False, None)
        ]

        # Mock video writer
        mock_out = MagicMock()
        mock_writer.return_value = mock_out

        # Mock ffmpeg success
        mock_subprocess.return_value = MagicMock(returncode=0)

        annotator = VideoAnnotator()

        detections_by_frame = {
            0: [{"bbox": (100, 100, 200, 200), "confidence": 0.95}],
            2: [{"bbox": (300, 300, 400, 400), "confidence": 0.88}],
        }

        output_path = Path("/tmp/output.mp4")
        annotator.create_annotated_video(
            Path("/test/input.mp4"),
            output_path,
            frame_skip=1,
            detections_by_frame=detections_by_frame,
        )

        # Verify video writer was called for each frame
        assert mock_out.write.call_count == 3

    @patch("birdhomie.video_processor.cv2.rectangle")
    @patch("birdhomie.video_processor.cv2.putText")
    @patch("birdhomie.video_processor.cv2.VideoCapture")
    @patch("birdhomie.video_processor.cv2.VideoWriter")
    @patch("birdhomie.video_processor.subprocess.run")
    @patch("birdhomie.video_processor.Path.unlink")
    def test_create_annotated_video_draws_boxes(
        self,
        mock_unlink,
        mock_subprocess,
        mock_writer,
        mock_capture,
        mock_puttext,
        mock_rectangle,
    ):
        """Test that detection boxes are drawn."""
        # Mock video capture
        mock_cap = MagicMock()
        mock_cap.get.side_effect = [30.0, 640, 480]
        mock_capture.return_value = mock_cap

        # Mock frame reading (1 frame with detection)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.side_effect = [(True, frame), (False, None)]

        # Mock video writer
        mock_out = MagicMock()
        mock_writer.return_value = mock_out

        # Mock ffmpeg success
        mock_subprocess.return_value = MagicMock(returncode=0)

        annotator = VideoAnnotator()

        detections_by_frame = {0: [{"bbox": (100, 100, 200, 200), "confidence": 0.95}]}

        annotator.create_annotated_video(
            Path("/test/input.mp4"),
            Path("/tmp/output.mp4"),
            frame_skip=1,
            detections_by_frame=detections_by_frame,
        )

        # Verify rectangle and text were drawn
        assert mock_rectangle.call_count >= 1
        assert mock_puttext.call_count >= 1

    @patch("birdhomie.video_processor.cv2.VideoCapture")
    @patch("birdhomie.video_processor.cv2.VideoWriter")
    @patch("birdhomie.video_processor.subprocess.run")
    @patch("birdhomie.video_processor.Path.unlink")
    @patch("birdhomie.video_processor.Path.rename")
    def test_create_annotated_video_ffmpeg_fallback(
        self, mock_rename, mock_unlink, mock_subprocess, mock_writer, mock_capture
    ):
        """Test ffmpeg fallback when hardware encoding fails."""
        import subprocess

        # Mock video capture
        mock_cap = MagicMock()
        mock_cap.get.side_effect = [30.0, 640, 480]
        mock_capture.return_value = mock_cap
        mock_cap.read.side_effect = [(False, None)]

        # Mock video writer
        mock_out = MagicMock()
        mock_writer.return_value = mock_out

        # Mock ffmpeg: first call fails with CalledProcessError (hardware), second succeeds (software)
        mock_subprocess.side_effect = [
            subprocess.CalledProcessError(1, "ffmpeg"),
            MagicMock(returncode=0),
        ]

        annotator = VideoAnnotator()

        annotator.create_annotated_video(
            Path("/test/input.mp4"),
            Path("/tmp/output.mp4"),
            frame_skip=1,
            detections_by_frame={},
        )

        # Verify ffmpeg was called twice (hardware, then software)
        assert mock_subprocess.call_count == 2
