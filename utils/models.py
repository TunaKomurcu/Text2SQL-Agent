"""
ML Model Management - Singleton Pattern
Manages loading and access to ML models (Embedding, LLM, Lexical)
"""

import os
from sentence_transformers import SentenceTransformer
from llama_cpp import Llama
from gensim.models import FastText

from config import settings
from .gpu import GPU_INFO, DEVICE


class ModelManager:
    """
    Singleton class to manage all ML models.
    Ensures models are loaded only once and accessible globally.
    """
    _instance = None
    
    def __init__(self):
        if ModelManager._instance is not None:
            raise Exception("ModelManager is a singleton! Use get_instance()")
        
        self._embedding_model = None
        self._semantic_model = None
        self._lexical_model = None
        self._llm = None
        
        ModelManager._instance = self
    
    @classmethod
    def get_instance(cls):
        """Get or create ModelManager singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_embedding_model(self):
        """Get or load embedding model (lazy loading)."""
        if self._embedding_model is None:
            print(f"⏳ Loading embedding model on {DEVICE.upper()}...")
            self._embedding_model = SentenceTransformer(
                settings.EMBEDDING_MODEL_NAME, 
                device=DEVICE
            )
            print(f"✅ Embedding model ready on {DEVICE.upper()}!")
        return self._embedding_model
    
    def get_semantic_model(self):
        """Get or load semantic model (lazy loading)."""
        if self._semantic_model is None:
            print(f"⏳ Loading semantic model on {DEVICE.upper()}...")
            model_name = settings.SEMANTIC_MODEL_NAME or settings.EMBEDDING_MODEL_NAME
            self._semantic_model = SentenceTransformer(model_name, device=DEVICE)
            print(f"✅ Semantic model ready on {DEVICE.upper()}!")
        return self._semantic_model
    
    def get_lexical_model(self):
        """Get or load FastText lexical model (lazy loading)."""
        if self._lexical_model is None and not (os.environ.get('SKIP_LEXICAL') == '1'):
            try:
                lexical_path = settings.LEXICAL_FASTTEXT_PATH or "fasttext_lexical_model.model"
                
                if os.path.exists(lexical_path):
                    self._lexical_model = FastText.load(lexical_path)
                    print(f"✅ FastText lexical model loaded from {lexical_path}")
                elif os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'models', os.path.basename(lexical_path))):
                    alt_path = os.path.join(os.path.dirname(__file__), '..', 'models', os.path.basename(lexical_path))
                    self._lexical_model = FastText.load(alt_path)
                    print(f"✅ FastText lexical model loaded from {alt_path}")
                else:
                    print(f"⚠️ FastText lexical model not found at {lexical_path}; lexical features disabled.")
                    self._lexical_model = None
            except Exception as e:
                print(f"⚠️ Error loading FastText lexical model: {e}. Lexical features disabled.")
                self._lexical_model = None
        
        return self._lexical_model
    
    def get_llm(self):
        """Get or load LLM model (lazy loading)."""
        if self._llm is None and not getattr(settings, "SKIP_LLM", False):
            try:
                print("⏳ Loading LLM model...")
                
                # GPU layer ayarı
                n_gpu_layers = 0  # Varsayılan CPU
                if GPU_INFO['available'] and (settings.USE_GPU is None or settings.USE_GPU):
                    n_gpu_layers = settings.LLM_N_GPU_LAYERS
                    print(f"🎮 LLM için {n_gpu_layers if n_gpu_layers > 0 else 'tüm'} katmanlar GPU'da çalışacak")
                
                self._llm = Llama(
                    model_path=settings.LLM_MODEL_PATH,
                    n_ctx=settings.LLM_N_CTX,
                    n_threads=settings.LLM_N_THREADS,
                    n_batch=settings.LLM_N_BATCH,
                    n_gpu_layers=n_gpu_layers,  # GPU desteği
                    low_vram=settings.LLM_LOW_VRAM,
                    verbose=settings.LLM_VERBOSE,
                )
                print("✅ LLM ready!")
            except Exception as e:
                print(f"⚠️ Could not load LLM: {e}. Continuing with SKIP_LLM=True")
                self._llm = None
                # If loading failed, set env flag so other code paths skip LLM usage
                os.environ["SKIP_LLM"] = "1"
        elif getattr(settings, "SKIP_LLM", False):
            print("⚠️ SKIP_LLM enabled; skipping LLM load")
        
        return self._llm


# Backwards compatibility - global accessors (will be loaded on first access)
def get_embedding_model():
    """Get embedding model from singleton."""
    return ModelManager.get_instance().get_embedding_model()


def get_semantic_model():
    """Get semantic model from singleton."""
    return ModelManager.get_instance().get_semantic_model()


def get_lexical_model():
    """Get lexical model from singleton."""
    return ModelManager.get_instance().get_lexical_model()


def get_llm():
    """Get LLM from singleton."""
    return ModelManager.get_instance().get_llm()
