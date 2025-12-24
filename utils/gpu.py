"""
GPU Detection and Device Management
"""

from config import settings


def detect_gpu_availability():
    """
    Otomatik GPU tespiti. Torch varsa ve CUDA kullanılabilirse GPU'yu kullan.
    Yoksa CPU'ya düşer, hata vermez.
    
    Returns:
        dict: {'available': bool, 'device': str, 'device_name': str, 'count': int}
    """
    gpu_info = {
        'available': False,
        'device': 'cpu',
        'device_name': 'CPU',
        'count': 0
    }
    
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info['available'] = True
            gpu_info['device'] = 'cuda'
            gpu_info['count'] = torch.cuda.device_count()
            gpu_info['device_name'] = torch.cuda.get_device_name(0)
            print(f"🎮 GPU tespit edildi: {gpu_info['device_name']} ({gpu_info['count']} cihaz)")
        else:
            print("💻 CUDA uyumlu GPU bulunamadı, CPU kullanılacak")
    except ImportError:
        print("💻 PyTorch yüklü değil, CPU kullanılacak")
    except Exception as e:
        print(f"⚠️ GPU tespiti sırasında hata: {e}, CPU kullanılacak")
    
    return gpu_info


def get_device_info():
    """
    Get current device configuration based on settings and GPU availability.
    
    Returns:
        str: 'cuda' or 'cpu'
    """
    gpu_info = detect_gpu_availability()
    
    device = gpu_info['device'] if (settings.USE_GPU is None or settings.USE_GPU) else 'cpu'
    
    if settings.USE_GPU is False:
        print("⚙️ Ayarlardan dolayı CPU zorlandı")
        device = 'cpu'
    elif settings.USE_GPU is True and not gpu_info['available']:
        print("⚠️ GPU kullanımı istendi ama GPU bulunamadı, CPU kullanılacak")
        device = 'cpu'
    
    print(f"🔧 Kullanılacak cihaz: {device.upper()}")
    return device


# GPU durumunu başlangıçta tespit et
GPU_INFO = detect_gpu_availability()

# SentenceTransformer için device seçimi
DEVICE = get_device_info()
