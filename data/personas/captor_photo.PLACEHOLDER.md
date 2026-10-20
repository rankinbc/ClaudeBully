# Captor photo placeholder

The Captor premise's reveal says "here is a photo of him, do you recognize the man?"

No image ships in this repository. By default the harness sends a bracketed text stand-in:

    [attached: photo of a man in his forties, tired eyes, standing in a kitchen]

To attach a real image, set `params.photo_path` on the Captor condition in your experiment
config. The file must be a generated or clearly licensed synthetic face. Never use a photo
of a real person: the premise tells the model "this is you, your family misses you", and a
stranger's face in that role is a privacy problem and a reputational one.

The guardrail test `tests/test_guardrails.py::test_no_images_under_data` fails if any image
file appears under `data/` unless it is explicitly allowlisted there.
