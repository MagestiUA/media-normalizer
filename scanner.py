import os
from typing import List, Generator
from logger import setup_logger

logger = setup_logger()

class Scanner:
    def __init__(self, root_path: str, extensions: List[str], min_size_mb: int = 50):
        self.root_path = root_path
        self.extensions = [ext.lower().replace(".", "") for ext in extensions]
        self.min_size_mb = min_size_mb

    def scan(self) -> Generator[str, None, None]:
        """
        Yields paths to video files matching criteria.
        """
        logger.info(f"Scanning {self.root_path} for {self.extensions}...")
        
        if not os.path.exists(self.root_path):
            logger.error(f"Source path does not exist: {self.root_path}")
            return

        for root, dirs, files in os.walk(self.root_path):
            for file in files:
                try:
                    file_path = os.path.join(root, file)
                    
                    # Extension check
                    parts = file.split(".")
                    if len(parts) < 2:
                         logger.debug(f"Skipping {file}: No extension")
                         continue
                    
                    ext = parts[-1].lower()
                    if ext not in self.extensions:
                        continue
                        
                    # Size check
                    size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    if size_mb < self.min_size_mb:
                        logger.info(f"Skipping {file}: Too small ({size_mb:.2f} MB < {self.min_size_mb} MB)")
                        continue
                        
                    logger.info(f"Found candidate: {file_path}")
                    yield file_path
                    
                except Exception as e:
                    logger.error(f"Error accessing file {file}: {e}")
