import os
from pydub import AudioSegment

#may break things
os.chdir(os.path.dirname(os.path.abspath(__file__)))

input_folder = "sfx"
output_folder = "sfx_wave"

os.makedirs(output_folder, exist_ok=True)

for filename in os.listdir(input_folder):
    if filename.lower().endswith(".mp3"):
        mp3_path = os.path.join(input_folder, filename)
        wav_filename = os.path.splitext(filename)[0] + ".wav"
        wav_path = os.path.join(output_folder, wav_filename)
        audio = AudioSegment.from_mp3(mp3_path)
        clean = (audio
            .set_frame_rate(44100)
            .set_channels(2)
            # longer fades to cover the offset fully
            .fade_in(20)      
            .fade_out(20)
            # knock out DC & sub-bass rumble
            .high_pass_filter(20)
            # give headroom & re-normalize
            .normalize(headroom=3.0)
        )
        clean.export(wav_path, format="wav")
