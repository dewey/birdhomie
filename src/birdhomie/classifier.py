"""BioCLIP species classification module."""

import logging
from pathlib import Path
from typing import Tuple, List
import torch
from PIL import Image
import open_clip
from .constants import BIOCLIP_MODEL_NAME

logger = logging.getLogger(__name__)


# European bird species likely to appear at a German bird feeder
DEFAULT_SPECIES_LIST = [
    "Erithacus rubecula",      # European Robin (Rotkehlchen)
    "Parus major",             # Great Tit (Kohlmeise)
    "Cyanistes caeruleus",     # Blue Tit (Blaumeise)
    "Passer domesticus",       # House Sparrow (Haussperling)
    "Turdus merula",           # Common Blackbird (Amsel)
    "Fringilla coelebs",       # Common Chaffinch (Buchfink)
    "Carduelis carduelis",     # European Goldfinch (Stieglitz)
    "Sitta europaea",          # Eurasian Nuthatch (Kleiber)
    "Pyrrhula pyrrhula",       # Eurasian Bullfinch (Gimpel)
    "Chloris chloris",         # European Greenfinch (Grünfink)
    "Aegithalos caudatus",     # Long-tailed Tit (Schwanzmeise)
    "Dendrocopos major",       # Great Spotted Woodpecker (Buntspecht)
    "Garrulus glandarius",     # Eurasian Jay (Eichelhäher)
    "Pica pica",               # Eurasian Magpie (Elster)
    "Corvus corone",           # Carrion Crow (Rabenkrähe)
    "Sturnus vulgaris",        # Common Starling (Star)
    "Columba palumbus",        # Common Wood Pigeon (Ringeltaube)
    "Streptopelia decaocto",   # Eurasian Collared Dove (Türkentaube)
    "Prunella modularis",      # Dunnock (Heckenbraunelle)
    "Emberiza citrinella",     # Yellowhammer (Goldammer)
    "Spinus spinus",           # Eurasian Siskin (Erlenzeisig)
    "Coccothraustes coccothraustes",  # Hawfinch (Kernbeißer)
    "Periparus ater",          # Coal Tit (Tannenmeise)
    "Poecile palustris",       # Marsh Tit (Sumpfmeise)
    "Lophophanes cristatus",   # European Crested Tit (Haubenmeise)
    "Certhia brachydactyla",   # Short-toed Treecreeper (Gartenbaumläufer)
    "Regulus regulus",         # Goldcrest (Wintergoldhähnchen)
    "Troglodytes troglodytes", # Eurasian Wren (Zaunkönig)
    "Motacilla alba",          # White Wagtail (Bachstelze)
    "Phoenicurus ochruros",    # Black Redstart (Hausrotschwanz)
]


class BirdSpeciesClassifier:
    """Bird species classifier using BioCLIP 2 zero-shot classification."""

    def __init__(self, species_list: List[str] = None):
        """Initialize the BioCLIP classifier.

        Args:
            species_list: List of species scientific names to classify
        """
        logger.info("loading_bioclip_model", extra={"model": BIOCLIP_MODEL_NAME})

        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            'hf-hub:imageomics/bioclip-2'
        )
        self.tokenizer = open_clip.get_tokenizer('hf-hub:imageomics/bioclip-2')
        self.model.eval()

        self.species_list = species_list or DEFAULT_SPECIES_LIST
        self.text_features = self._encode_species(self.species_list)

        logger.info("bioclip_model_loaded", extra={
            "model": BIOCLIP_MODEL_NAME,
            "species_count": len(self.species_list)
        })

    def _encode_species(self, species_list: List[str]) -> torch.Tensor:
        """Pre-encode species names for efficient classification.

        Args:
            species_list: List of species scientific names

        Returns:
            Normalized text features tensor
        """
        text = self.tokenizer(species_list)
        with torch.no_grad():
            text_features = self.model.encode_text(text)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
        return text_features

    def classify(self, image_path: Path) -> Tuple[str, float]:
        """Classify a bird image and return species name and confidence.

        Args:
            image_path: Path to bird crop image

        Returns:
            Tuple of (species_scientific_name, confidence)
        """
        try:
            image = Image.open(image_path).convert("RGB")
            image_tensor = self.preprocess(image).unsqueeze(0)

            with torch.no_grad():
                image_features = self.model.encode_image(image_tensor)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)

                logits = (image_features @ self.text_features.T).squeeze(0)
                probs = torch.nn.functional.softmax(logits * 100, dim=-1)
                confidence, idx = torch.max(probs, dim=0)

            species = self.species_list[idx.item()]
            conf = confidence.item()

            logger.debug("species_classified", extra={
                "species": species,
                "confidence": conf
            })

            return species, conf
        except Exception as e:
            logger.error("classification_failed", extra={
                "image_path": str(image_path),
                "error": str(e)
            })
            return "unknown", 0.0

    def classify_from_array(self, image: Image.Image) -> Tuple[str, float]:
        """Classify a bird image from PIL Image.

        Args:
            image: PIL Image object

        Returns:
            Tuple of (species_scientific_name, confidence)
        """
        try:
            image_tensor = self.preprocess(image).unsqueeze(0)

            with torch.no_grad():
                image_features = self.model.encode_image(image_tensor)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)

                logits = (image_features @ self.text_features.T).squeeze(0)
                probs = torch.nn.functional.softmax(logits * 100, dim=-1)
                confidence, idx = torch.max(probs, dim=0)

            species = self.species_list[idx.item()]
            conf = confidence.item()

            return species, conf
        except Exception as e:
            logger.error("classification_failed", extra={"error": str(e)})
            return "unknown", 0.0
