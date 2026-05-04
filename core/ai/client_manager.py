import os
import random
from typing import Optional
from groq import Groq
from logger import get_logger

logger = get_logger("ai.client_manager")

class GroqClientManager:
    _instance = None
    _keys = []
    _current_index = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GroqClientManager, cls).__new__(cls)
            cls._instance._load_keys()
        return cls._instance

    def _load_keys(self):
        # Load keys from environment
        self._keys = []
        for i in range(1, 11):  # Support up to 10 keys
            key = os.getenv(f"GROQ_API_KEY_{i}") or os.getenv("GROQ_API_KEY") if i == 1 else None
            if key:
                self._keys.append(key)
            elif i > 1 and not os.getenv(f"GROQ_API_KEY_{i}"):
                break
        
        if not self._keys:
            # Fallback to single GROQ_API_KEY
            main_key = os.getenv("GROQ_API_KEY")
            if main_key:
                self._keys = [main_key]
        
        logger.info("Loaded %d Groq API keys for rotation", len(self._keys))

    def get_client(self, rotate: bool = True) -> Optional[Groq]:
        if not self._keys:
            return None
        
        if rotate:
            key = self._keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(self._keys)
        else:
            key = self._keys[0]
            
        return Groq(api_key=key)

    def get_all_keys(self):
        return self._keys

# Global manager instance
groq_manager = GroqClientManager()

def get_groq_client(rotate: bool = True) -> Optional[Groq]:
    return groq_manager.get_client(rotate)
