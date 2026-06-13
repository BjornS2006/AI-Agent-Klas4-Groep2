import subprocess
import os
from typing import Optional

class PiperTTS:
    def __init__(self, model_path: str = None, output_dir: str = "output"):
        """
        Initialize the Piper TTS engine.
        
        :param model_path: Path to the .onnx model file for Piper. Defaults to environment variable PIPER_MODEL_PATH.
        :param output_dir: Directory where generated audio files will be saved.
        """
        self.model_path = model_path or os.getenv("PIPER_MODEL_PATH", "TTSModel/nl_NL-pim-medium.onnx")
        self.output_dir = output_dir
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def speak(self, text: str) -> Optional[str]:
        """
        Convert text to speech using Piper and return the path to the generated audio file.
        
        :param text: The text to convert to speech.
        :return: Path to the .wav file or None if failed.
        """
        if not text:
            return None
            
        output_file = os.path.join(self.output_dir, "latest_output.wav")
        
        # Construct the command for Piper
        # Note: This assumes 'piper' is in the system PATH or available as a script.
        command = [
            "piper",
            "--model", self.model_path,
            "--output_file", output_file
        ]
        
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True
            )
            process.communicate(input=text)
            
            if process.returncode == 0:
                return output_file
            else:
                print(f"Error: Piper failed with return code {process.returncode}")
                return None
        except Exception as e:
            print(f"Exception occurred while running Piper: {e}")
            return None
