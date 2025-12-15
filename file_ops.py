import os
import shutil
import time
from typing import Optional
from logger import setup_logger

logger = setup_logger()

def safe_replace(original_path: str, new_path: str, output_path: Optional[str] = None, delete_backup: bool = True) -> bool:
    """
    Atomically replaces original_path with new_path using a backup file.
    If output_path is provided, the new file is moved to output_path and original_path is removed/backed up.
    If output_path is None, defaults to original_path (in-place replacement).
    """
    if not os.path.exists(new_path):
        logger.error(f"New file not found: {new_path}")
        return False
    
    if not os.path.exists(original_path):
        logger.error(f"Original file not found: {original_path}")
        return False

    target_path = output_path if output_path else original_path
    backup_path = original_path + ".bak"
    
    try:
        # 1. Rename original to backup
        if os.path.exists(backup_path):
             try:
                 os.remove(backup_path)
             except OSError:
                 # Sometimes backup is locked or permission issue
                 pass
            
        os.rename(original_path, backup_path)
        
        # 2. Move new file to TARGET path
        # If target path exists (e.g. we are overwriting an existing output), we need to handle it.
        # But wait, if target_path != original_path (e.g. mkv vs mp4), target_path might already exist.
        # shutil.move will overwrite if semantic is correct, but let's be safe.
        if os.path.exists(target_path):
            os.remove(target_path)
            
        shutil.move(new_path, target_path)
        
        # 3. Cleanup
        if delete_backup:
            try:
                os.remove(backup_path)
                logger.info(f"Replaced {original_path} -> {target_path}. Backup deleted.")
            except Exception as e:
                logger.warning(f"Could not delete backup {backup_path}: {e}")
        else:
            logger.info(f"Replaced {original_path} -> {target_path}. Backup preserved.")
            
        return True

    except Exception as e:
        logger.error(f"Failed to replace/convert file {original_path}: {e}")
        # Rollback logic
        # If we failed, we should try to restore original_path from backup
        if os.path.exists(backup_path) and not os.path.exists(original_path):
            try:
                os.rename(backup_path, original_path)
                logger.info("Rolled back original file.")
            except Exception as rb_e:
                logger.critical(f"CRITICAL: Failed to rollback {original_path}: {rb_e}")
        return False
