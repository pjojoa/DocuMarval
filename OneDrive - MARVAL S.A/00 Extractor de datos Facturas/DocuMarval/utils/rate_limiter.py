"""Rate limiter thread-safe para control de llamadas a API"""
import time
from collections import deque
import threading
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Controla la tasa de llamadas a la API para evitar saturación (thread-safe)"""
    def __init__(self, max_calls=40, time_window=60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()
        self.lock = threading.Lock()  # Lock para thread-safety
    
    def wait_if_needed(self):
        """Espera si es necesario para respetar el límite de tasa"""
        with self.lock:
            now = time.time()
            # Limpiar llamadas antiguas
            while self.calls and self.calls[0] < now - self.time_window:
                self.calls.popleft()
            
            # Si excedemos el límite, esperar
            if len(self.calls) >= self.max_calls:
                sleep_time = self.time_window - (now - self.calls[0])
                if sleep_time > 0:
                    logger.debug(f"Rate limit alcanzado, esperando {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    # Limpiar nuevamente después de esperar
                    now = time.time()
                    while self.calls and self.calls[0] < now - self.time_window:
                        self.calls.popleft()
            
            self.calls.append(time.time())

