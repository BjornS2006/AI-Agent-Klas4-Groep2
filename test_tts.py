import os
from agent.tts_engine import PiperTTS

def test_piper():
    # Configuration - using the Dutch model you specified earlier
    model_path = "TTSModel/nl_NL-pim-medium.onnx"
    output_dir = "test_output"
    sample_text = "Hallo, dit is een test van de Piper tekst naar spraak engine."

    print(f"Testing Piper with model: {model_path}")
    
    try:
        # Initialize the engine
        tts = PiperTTS(model_path=model_path, output_dir=output_dir)
        
        # Generate speech
        print(f"Generating audio for: '{sample_text}'")
        result_path = tts.speak(sample_text)
        
        if result_path and os.path.exists(result_path):
            print(f"Success! Audio saved to: {result_path}")
        else:
            print("Failed to generate audio file.")
            
    except Exception as e:
        print(f"An error occurred during testing: {e}")

if __name__ == "__main__":
    test_piper()
