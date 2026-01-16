"""Tests for bird detection module."""

import numpy as np
from unittest.mock import MagicMock, patch
from birdhomie.detector import BirdDetector


class TestBirdDetector:
    """Test YOLO bird detector."""

    @patch("birdhomie.detector.YOLO")
    def test_initialization(self, mock_yolo):
        """Test detector initialization."""
        detector = BirdDetector(confidence_threshold=0.75)
        assert detector.confidence_threshold == 0.75
        assert detector.model is None

    @patch("birdhomie.detector.YOLO")
    def test_load_model(self, mock_yolo):
        """Test model loading."""
        detector = BirdDetector()
        detector.load_model()

        # Model should be loaded
        assert detector.model is not None
        mock_yolo.assert_called_once()

    @patch("birdhomie.detector.YOLO")
    def test_detect_birds_filters_by_class(self, mock_yolo):
        """Test that only bird class (14) is detected."""
        detector = BirdDetector(confidence_threshold=0.5)

        # Mock YOLO result with bird and non-bird detections
        mock_result = MagicMock()
        mock_boxes = MagicMock()

        # Setup for iteration: len(boxes) should return 3
        mock_boxes.__len__ = MagicMock(return_value=3)

        # Setup indexing for cls, conf, and xyxy
        cls_values = [14, 0, 14]  # bird, person, bird
        conf_values = [0.9, 0.95, 0.8]

        def cls_getitem(self, index):
            return cls_values[index]

        def conf_getitem(self, index):
            return conf_values[index]

        def xyxy_getitem(self, index):
            coords = [
                np.array([10, 20, 100, 200]),
                np.array([50, 50, 150, 150]),
                np.array([200, 100, 300, 250]),
            ][index]
            mock_tensor = MagicMock()
            mock_tensor.cpu.return_value.numpy.return_value = coords
            return mock_tensor

        mock_boxes.cls.__getitem__ = cls_getitem
        mock_boxes.conf.__getitem__ = conf_getitem
        mock_boxes.xyxy.__getitem__ = xyxy_getitem

        mock_result.boxes = mock_boxes
        detector.model = MagicMock(return_value=[mock_result])

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = detector.detect_birds(frame)

        # Should only get the 2 bird detections
        assert len(detections) == 2
        assert all(d["class_id"] == 14 for d in detections)

    @patch("birdhomie.detector.YOLO")
    def test_detect_birds_filters_by_confidence(self, mock_yolo):
        """Test that low confidence detections are filtered out."""
        detector = BirdDetector(confidence_threshold=0.75)

        # Mock YOLO result with varying confidences
        mock_result = MagicMock()
        mock_boxes = MagicMock()

        mock_boxes.__len__ = MagicMock(return_value=3)

        cls_values = [14, 14, 14]
        conf_values = [0.9, 0.5, 0.8]  # Only first and third should pass

        def cls_getitem(self, index):
            return cls_values[index]

        def conf_getitem(self, index):
            return conf_values[index]

        def xyxy_getitem(self, index):
            coords = [
                np.array([10, 20, 100, 200]),
                np.array([50, 50, 150, 150]),
                np.array([200, 100, 300, 250]),
            ][index]
            mock_tensor = MagicMock()
            mock_tensor.cpu.return_value.numpy.return_value = coords
            return mock_tensor

        mock_boxes.cls.__getitem__ = cls_getitem
        mock_boxes.conf.__getitem__ = conf_getitem
        mock_boxes.xyxy.__getitem__ = xyxy_getitem

        mock_result.boxes = mock_boxes
        detector.model = MagicMock(return_value=[mock_result])

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = detector.detect_birds(frame)

        # Should only get the 2 high-confidence detections
        assert len(detections) == 2
        assert all(d["confidence"] >= 0.75 for d in detections)

    @patch("birdhomie.detector.YOLO")
    def test_detect_birds_returns_correct_format(self, mock_yolo):
        """Test that detections have correct format."""
        detector = BirdDetector(confidence_threshold=0.5)

        # Mock YOLO result
        mock_result = MagicMock()
        mock_boxes = MagicMock()

        mock_boxes.__len__ = MagicMock(return_value=1)

        def cls_getitem(self, index):
            return 14

        def conf_getitem(self, index):
            return 0.9

        def xyxy_getitem(self, index):
            mock_tensor = MagicMock()
            mock_tensor.cpu.return_value.numpy.return_value = np.array(
                [10.5, 20.3, 100.7, 200.9]
            )
            return mock_tensor

        mock_boxes.cls.__getitem__ = cls_getitem
        mock_boxes.conf.__getitem__ = conf_getitem
        mock_boxes.xyxy.__getitem__ = xyxy_getitem

        mock_result.boxes = mock_boxes
        detector.model = MagicMock(return_value=[mock_result])

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = detector.detect_birds(frame)

        assert len(detections) == 1
        det = detections[0]

        # Check format
        assert "bbox" in det
        assert "confidence" in det
        assert "class_id" in det

        # Check types
        assert isinstance(det["bbox"], tuple)
        assert len(det["bbox"]) == 4
        assert all(isinstance(x, int) for x in det["bbox"])
        assert isinstance(det["confidence"], float)
        assert isinstance(det["class_id"], int)

    def test_is_edge_detection_left_edge(self):
        """Test edge detection on left edge."""
        detector = BirdDetector()

        bbox = (5, 100, 50, 200)  # x1 = 5, close to left edge
        image_shape = (480, 640)

        assert detector.is_edge_detection(bbox, image_shape, margin=20) is True

    def test_is_edge_detection_right_edge(self):
        """Test edge detection on right edge."""
        detector = BirdDetector()

        bbox = (500, 100, 635, 200)  # x2 = 635, close to right edge (640)
        image_shape = (480, 640)

        assert detector.is_edge_detection(bbox, image_shape, margin=20) is True

    def test_is_edge_detection_top_edge(self):
        """Test edge detection on top edge."""
        detector = BirdDetector()

        bbox = (100, 10, 200, 100)  # y1 = 10, close to top edge
        image_shape = (480, 640)

        assert detector.is_edge_detection(bbox, image_shape, margin=20) is True

    def test_is_edge_detection_bottom_edge(self):
        """Test edge detection on bottom edge."""
        detector = BirdDetector()

        bbox = (100, 300, 200, 475)  # y2 = 475, close to bottom edge (480)
        image_shape = (480, 640)

        assert detector.is_edge_detection(bbox, image_shape, margin=20) is True

    def test_is_edge_detection_center(self):
        """Test that center detections are not marked as edge."""
        detector = BirdDetector()

        bbox = (200, 150, 400, 300)  # Well within the frame
        image_shape = (480, 640)

        assert detector.is_edge_detection(bbox, image_shape, margin=20) is False

    def test_is_edge_detection_custom_margin(self):
        """Test edge detection with custom margin."""
        detector = BirdDetector()

        bbox = (35, 100, 200, 300)  # x1 = 35
        image_shape = (480, 640)

        # Should be edge with margin=50
        assert detector.is_edge_detection(bbox, image_shape, margin=50) is True

        # Should NOT be edge with margin=20
        assert detector.is_edge_detection(bbox, image_shape, margin=20) is False
