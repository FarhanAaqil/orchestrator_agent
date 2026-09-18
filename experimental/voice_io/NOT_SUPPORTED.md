# NOT SUPPORTED: Voice I/O

## Status
- **Status**: Quarantined / Experimental
- **Supported in v2**: No
- **Covered by tests**: No
- **Included in Docker**: No

## Reason
Native text-to-speech (pyttsx3) and audio capture (SpeechRecognition, PyAudio) require system-level audio device drivers, C library bindings (PortAudio, espeak), and OS-specific dependencies incompatible with lean, headless containerized environments.

## Usage
Kept strictly as a reference implementation. Do not import in orchestrator_core/.
