"""Tests for bird species classification module."""

from PIL import Image
from unittest.mock import MagicMock, patch
from pathlib import Path
from birdhomie.classifier import BirdSpeciesClassifier, DEFAULT_SPECIES_LIST


class TestBirdSpeciesClassifier:
    """Test BioCLIP species classifier."""

    @patch("birdhomie.classifier.open_clip")
    def test_initialization(self, mock_open_clip):
        """Test classifier initialization."""
        mock_open_clip.create_model_and_transforms.return_value = (
            MagicMock(),
            None,
            MagicMock(),
        )
        mock_open_clip.get_tokenizer.return_value = MagicMock()

        classifier = BirdSpeciesClassifier()

        assert classifier.species_list == DEFAULT_SPECIES_LIST
        assert len(classifier.species_list) > 0
        mock_open_clip.create_model_and_transforms.assert_called_once()
        mock_open_clip.get_tokenizer.assert_called_once()

    @patch("birdhomie.classifier.open_clip")
    def test_initialization_with_custom_species(self, mock_open_clip):
        """Test classifier with custom species list."""
        mock_open_clip.create_model_and_transforms.return_value = (
            MagicMock(),
            None,
            MagicMock(),
        )
        mock_open_clip.get_tokenizer.return_value = MagicMock()

        custom_species = ["Parus major", "Turdus merula"]
        classifier = BirdSpeciesClassifier(species_list=custom_species)

        assert classifier.species_list == custom_species
        assert len(classifier.species_list) == 2

    @patch("birdhomie.classifier.open_clip")
    @patch("birdhomie.classifier.torch")
    def test_classify_from_array_returns_species_and_confidence(
        self, mock_torch, mock_open_clip
    ):
        """Test classification returns species name and confidence."""
        # Setup mocks
        mock_model = MagicMock()
        mock_preprocess = MagicMock()
        mock_open_clip.create_model_and_transforms.return_value = (
            mock_model,
            None,
            mock_preprocess,
        )
        mock_open_clip.get_tokenizer.return_value = MagicMock()

        # Mock torch operations
        mock_tensor = MagicMock()
        mock_preprocess.return_value = mock_tensor
        mock_tensor.unsqueeze.return_value = mock_tensor

        # Mock model outputs
        mock_image_features = MagicMock()
        mock_image_features.norm.return_value = MagicMock()
        mock_image_features.__truediv__ = MagicMock(return_value=mock_image_features)
        mock_model.encode_image.return_value = mock_image_features

        # Mock softmax and max
        mock_probs = MagicMock()
        mock_torch.nn.functional.softmax.return_value = mock_probs
        mock_confidence = MagicMock()
        mock_confidence.item.return_value = 0.92
        mock_idx = MagicMock()
        mock_idx.item.return_value = 0  # First species in list
        mock_torch.max.return_value = (mock_confidence, mock_idx)

        classifier = BirdSpeciesClassifier()

        # Create test image
        test_image = Image.new("RGB", (224, 224), color="red")

        species, confidence = classifier.classify_from_array(test_image)

        assert species == DEFAULT_SPECIES_LIST[0]
        assert confidence == 0.92
        assert 0 <= confidence <= 1

    @patch("birdhomie.classifier.Image")
    @patch("birdhomie.classifier.open_clip")
    @patch("birdhomie.classifier.torch")
    def test_classify_handles_file_path(self, mock_torch, mock_open_clip, mock_pil):
        """Test classification from file path."""
        # Setup mocks
        mock_model = MagicMock()
        mock_preprocess = MagicMock()
        mock_open_clip.create_model_and_transforms.return_value = (
            mock_model,
            None,
            mock_preprocess,
        )
        mock_open_clip.get_tokenizer.return_value = MagicMock()

        # Mock Image loading
        mock_image = MagicMock()
        mock_pil.open.return_value = mock_image
        mock_image.convert.return_value = mock_image

        # Mock torch operations
        mock_tensor = MagicMock()
        mock_preprocess.return_value = mock_tensor
        mock_tensor.unsqueeze.return_value = mock_tensor

        # Mock model outputs
        mock_image_features = MagicMock()
        mock_image_features.norm.return_value = MagicMock()
        mock_image_features.__truediv__ = MagicMock(return_value=mock_image_features)
        mock_model.encode_image.return_value = mock_image_features

        # Mock softmax and max
        mock_probs = MagicMock()
        mock_torch.nn.functional.softmax.return_value = mock_probs
        mock_confidence = MagicMock()
        mock_confidence.item.return_value = 0.95
        mock_idx = MagicMock()
        mock_idx.item.return_value = 0  # First species in list
        mock_torch.max.return_value = (mock_confidence, mock_idx)

        classifier = BirdSpeciesClassifier()

        # Test with any path (won't actually open due to mocking)
        species, confidence = classifier.classify(Path("/fake/path.jpg"))
        assert species == DEFAULT_SPECIES_LIST[0]
        assert confidence == 0.95

    @patch("birdhomie.classifier.open_clip")
    def test_classify_from_array_error_handling(self, mock_open_clip):
        """Test that classification errors are handled gracefully."""
        # Setup mocks
        mock_model = MagicMock()
        mock_preprocess = MagicMock()
        mock_open_clip.create_model_and_transforms.return_value = (
            mock_model,
            None,
            mock_preprocess,
        )
        mock_open_clip.get_tokenizer.return_value = MagicMock()

        # Make preprocessing raise an exception
        mock_preprocess.side_effect = Exception("Processing error")

        classifier = BirdSpeciesClassifier()

        test_image = Image.new("RGB", (224, 224), color="red")
        species, confidence = classifier.classify_from_array(test_image)

        # Should return unknown with 0.0 confidence
        assert species == "unknown"
        assert confidence == 0.0

    @patch("birdhomie.classifier.open_clip")
    @patch("birdhomie.classifier.Image")
    def test_classify_file_not_found(self, mock_pil, mock_open_clip):
        """Test classification handles missing files."""
        mock_open_clip.create_model_and_transforms.return_value = (
            MagicMock(),
            None,
            MagicMock(),
        )
        mock_open_clip.get_tokenizer.return_value = MagicMock()

        # Mock image loading to raise FileNotFoundError
        mock_pil.open.side_effect = FileNotFoundError("File not found")

        classifier = BirdSpeciesClassifier()

        species, confidence = classifier.classify(Path("/nonexistent/path.jpg"))

        assert species == "unknown"
        assert confidence == 0.0


class TestDefaultSpeciesList:
    """Test the default species list."""

    def test_default_species_list_not_empty(self):
        """Test that default species list has entries."""
        assert len(DEFAULT_SPECIES_LIST) > 0

    def test_default_species_list_format(self):
        """Test that species names are properly formatted."""
        for species in DEFAULT_SPECIES_LIST:
            # Should be scientific name format: "Genus species"
            assert isinstance(species, str)
            assert len(species) > 0
            # Should have at least two words (genus and species)
            parts = species.split()
            assert len(parts) >= 2

    def test_default_species_list_includes_common_birds(self):
        """Test that common European birds are included."""
        common_species = [
            "Parus major",  # Great Tit
            "Turdus merula",  # Blackbird
            "Erithacus rubecula",  # Robin
        ]

        for species in common_species:
            assert species in DEFAULT_SPECIES_LIST, (
                f"{species} should be in default list"
            )
