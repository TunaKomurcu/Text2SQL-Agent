"""
Utils Package - Infrastructure Layer
Provides low-level utilities for GPU, DB, Qdrant, and ML models.
"""

from .gpu import detect_gpu_availability, get_device_info, GPU_INFO, DEVICE
from .db import get_connection
from .qdrant import get_qdrant_client, normalize_qdrant_hit
from .models import ModelManager

__all__ = [
    'detect_gpu_availability',
    'get_device_info',
    'GPU_INFO',
    'DEVICE',
    'get_connection',
    'get_qdrant_client',
    'normalize_qdrant_hit',
    'ModelManager',
]
