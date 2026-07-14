"""
voice_loop.py — eComBot Voice Pipeline
========================================
End-to-end pipeline:
    microphone → STT (OpenRouter) → eComBot Orchestrator → TTS (OpenRouter) → speaker

Features:
  - Turn-based voice loop for order status and product queries
  - Multi-language support (English + Hindi)
  - Barge-in: speak over eComBot to interrupt playback
  - Graceful fallback to text mode when microphone is unavailable

Run:
    python src/voice/voice_loop.py              # English (default)
    python src/voice/voice_loop.py -l hi        # Hindi
    python src/voice/voice_loop.py --text       # type instead of speaking
    python src/voice/voice_loop.py --no-barge-in

Prereqs:
    pip install pyaudio webrtcvad sounddevice numpy httpx
    OPENROUTER_API_KEY set in .env
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

# Ensure src/ is importable when run directly
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dotenv import load_dotenv
load_dotenv()

from google.genai import types

from agents.orchestrator import orchestrator
from session import make_runner
from voice.languages import LANGUAGES, get_language
from voice.stt_openrouter import OpenRouterSTT
from voice.tts_openrouter import OpenRouterTTS

_C = {
    "b": "\033[1m", "cyan": "\033[36m", "green": "\033[32m",
    "yellow": "\033[33m", "dim": "\033[90m", "x": "\033[0m",
}

# VOICE_STYLE rules injected into agent per-turn prompt
# These augment the existing orchestrator instruction for voice output.
_VOICE_STYLE_SUFFIX = """

[VOICE OUTPUT MODE]
This response will be spoken aloud by a text-to-speech engine.
- Reply in the SAME language the customer used.
- Output plain spoken sentences only. No markdown, no bullet points, no
  numbered lists, no headings, no bold, no emoji, no tables.
- Keep answers to 2 or 3 short sentences.
- For order IDs, say digits separately: "ORD zero zero one" not "ORD-001".
- If the customer gave an order ID, repeat it back before acting:
  "I heard ORD zero zero two — is that correct?" Then wait for confirmation.
"""

# Agent
async def ask_agent(runner, uid: str, sid: str, text: str) -> tuple[str, str, int]:
    """Send one turn to the eComBot Orchestrator. Returns (reply, author, elapsed_ms)."""
    # Append voice style to the text so the orchestrator adapts its output
    voice_text = text + _VOICE_STYLE_SUFFIX
    t0 = time.perf_counter()
    reply = ""
    author = ""
    async for event in runner.run_async(
        user_id=uid,
        session_id=sid,
        new_message=types.Content(role="user", parts=[types.Part(text=voice_text)]),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    args = ", ".join(f"{k}={v!r}" for k, v in (fc.args or {}).items())
                    route_tag = (
                        f"→ {dict(fc.args or {}).get('request', '')[:40]}"
                        if fc.name.startswith("delegate_to") else ""
                    )
                    print(f"  {_C['dim']}[tool]  {fc.name}({args}) {route_tag}{_C['x']}")
        if event.is_final_response() and event.content and event.content.parts:
            t = event.content.parts[0].text
            if t:
                reply, author = t.strip(), event.author
    return reply, author, int((time.perf_counter() - t0) * 1000)

# Voice loop
async def run_voice_loop(lang_key: str, allow_barge_in: bool, text_mode: bool) -> None:
    lang = get_language(lang_key)
    stt = OpenRouterSTT()
    tts = OpenRouterTTS()

    # audio_io is optional — gracefully degrade if pyaudio/webrtcvad not installed
    audio = None
    if not text_mode:
        try:
            from voice.audio_io import AudioIO
            audio = AudioIO()
        except ImportError:
            print(
                f"{_C['yellow']}[voice] pyaudio/webrtcvad not installed — "
                f"falling back to text mode.{_C['x']}"
            )
            text_mode = True

    print(f"\n{'=' * 65}")
    print(f"{_C['b']}{_C['cyan']}eComBot Voice Pipeline  [{lang.name}]{_C['x']}")
    print(f"{_C['dim']}mic → OpenRouter STT → ADK Orchestrator → OpenRouter TTS → speaker{_C['x']}")
    if text_mode:
        print(f"{_C['yellow']}Text mode active (type your messages){_C['x']}")
    print(f"{'=' * 65}")

    runner, uid, sid = await make_runner(orchestrator)

    # Greeting
    print(f"\n  {_C['dim']}[eComBot greeting]{_C['x']}")
    greeting = lang.greeting
    if text_mode:
        print(f"  eComBot: {greeting}\n")
    else:
        try:
            tts.synth_to_wav(greeting, "/tmp/ecombot_greeting.wav")
            audio_module = __import__("sounddevice", fromlist=["play", "wait"])
            import numpy as np
            arr = np.frombuffer(open("/tmp/ecombot_greeting.wav", "rb").read()[44:], dtype=np.int16)
            audio_module.play(arr, samplerate=tts.sample_rate)
            audio_module.wait()
        except Exception:
            print(f"  eComBot: {greeting}\n")

    # Show sample prompts
    print(f"\n  {_C['dim']}Sample prompts:{_C['x']}")
    for p in lang.sample_prompts[:3]:
        print(f"    • {p}")
    print()

    # Main loop
    turn = 0
    while True:
        print(f"  {_C['dim']}Turn {turn + 1} — {'speak now' if not text_mode else 'type your message'} (Ctrl+C to quit){_C['x']}")

        # Capture input
        if text_mode:
            try:
                user_input = input("  You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Goodbye.\n")
                break
            if user_input.lower() in ("q", "quit", "exit"):
                print("\n  Goodbye.\n")
                break
            if not user_input:
                continue
        else:
            try:
                utterance = audio.listen_utterance()
                transcript = stt.transcribe(utterance.audio, language=lang.lang_code)
                user_input = transcript.text.strip()
                if not user_input:
                    print(f"  {_C['dim']}[nothing heard — try again]{_C['x']}\n")
                    continue
                print(f"  {_C['green']}You ({transcript.latency_ms}ms STT): {user_input}{_C['x']}")
            except KeyboardInterrupt:
                print("\n  Goodbye.\n")
                break
            except Exception as exc:
                print(f"  {_C['yellow']}[STT error: {exc}]{_C['x']}")
                continue

        # Agent
        reply, author, agent_ms = await ask_agent(runner, uid, sid, user_input)
        if not reply:
            reply = "Sorry, I didn't get a response. Please try again."

        print(f"\n  {_C['b']}[eComBot/{author}]{_C['x']} ({agent_ms}ms)")
        print(f"  {reply}\n")

        # TTS output
        if not text_mode and audio is not None:
            try:
                t_tts0 = time.perf_counter()
                # Barge-in: speak() with simultaneous mic monitoring
                interrupted_audio = audio.speak(
                    pcm_iter=tts.iter_pcm(reply),
                    sample_rate=tts.sample_rate,
                    allow_barge_in=allow_barge_in,
                )
                tts_ms = int((time.perf_counter() - t_tts0) * 1000)
                print(f"  {_C['dim']}[TTS: {tts_ms}ms]{_C['x']}\n")

                # If user barged in, process the interrupting utterance
                if interrupted_audio is not None:
                    barge_transcript = stt.transcribe(interrupted_audio, language=lang.lang_code)
                    if barge_transcript.text.strip():
                        print(f"  {_C['yellow']}[barge-in] {barge_transcript.text}{_C['x']}")
                        user_input = barge_transcript.text.strip()
                        reply, author, agent_ms = await ask_agent(runner, uid, sid, user_input)
                        print(f"\n  {_C['b']}[eComBot/{author}]{_C['x']} ({agent_ms}ms)")
                        print(f"  {reply}\n")
                        # Play the barge-in response too
                        audio.speak(
                            pcm_iter=tts.iter_pcm(reply),
                            sample_rate=tts.sample_rate,
                            allow_barge_in=allow_barge_in,
                        )
            except Exception as exc:
                print(f"  {_C['yellow']}[TTS error: {exc} — text reply above]{_C['x']}\n")
        elif text_mode:
            pass  # already printed above

        turn += 1

# Entry point
def main() -> None:
    parser = argparse.ArgumentParser(description="eComBot Voice Pipeline")
    parser.add_argument("-l", "--language", default="en",
                        choices=list(LANGUAGES), help="Language key (default: en)")
    parser.add_argument("--no-barge-in", action="store_true",
                        help="Disable barge-in (play TTS to completion before listening)")
    parser.add_argument("--text", action="store_true",
                        help="Text mode: type instead of speaking (no mic required)")
    args = parser.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print(
            "\n[ERROR] OPENROUTER_API_KEY is not set.\n"
            "Add it to a .env file:  OPENROUTER_API_KEY=your-key-here\n"
        )
        sys.exit(1)

    asyncio.run(run_voice_loop(
        lang_key=args.language,
        allow_barge_in=not args.no_barge_in,
        text_mode=args.text,
    ))

if __name__ == "__main__":
    main()
