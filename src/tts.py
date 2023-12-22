from pydub import AudioSegment
import torch

language = 'en'
model_id = 'v3_en'
device = torch.device('cpu')
model, example_text = torch.hub.load(repo_or_dir='snakers4/silero-models', model='silero_tts', language=language, speaker=model_id)
model.to(device)

def tts_wav(text):
    sample_rate = 48000
    speaker = 'en_97'
    audio_path = model.save_wav(text=text, speaker=speaker, sample_rate=sample_rate, audio_path='tts/voice.wav')
    AudioSegment.from_wav(audio_path).export("tts/voice.mp3", format="mp3")
    return open("tts/voice.mp3", 'rb')
