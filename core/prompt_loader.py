import json
import os
from pathlib import Path

# Assuming brain directory is aligned with core directory
BASE_DIR = Path(__file__).parent.parent
BRAIN_PROMPTS_DIR = BASE_DIR / "brain" / "system_prompts"

class PromptLoader:
    """
    Loads dynamically the active master system prompt using the active_prompt.json configuration.
    """
    def __init__(self, prompt_dir=BRAIN_PROMPTS_DIR):
        self.prompt_dir = Path(prompt_dir)

    def load_master_prompt(self):
        """
        Dynamically load the current active master system prompt text.
        """
        active_prompt_path = self.prompt_dir / "active_prompt.json"
        
        if not active_prompt_path.exists():
            raise FileNotFoundError(f"Active prompt config missing: {active_prompt_path}")
            
        with open(active_prompt_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        active_version = config.get("active_version")
        if not active_version:
            raise ValueError("active_prompt.json is missing 'active_version' key.")
            
        prompt_file_path = self.prompt_dir / active_version
        
        if not prompt_file_path.exists():
            raise FileNotFoundError(f"Prompt file missing: {prompt_file_path}")
            
        with open(prompt_file_path, "r", encoding="utf-8") as f:
            prompt_text = f.read()
            
        return prompt_text
