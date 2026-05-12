import asyncio
import tempfile
import os
import re

import streamlit as st
from openai import OpenAI
import edge_tts

# --------------------------------------------------
# Streamlit UI
# --------------------------------------------------
st.set_page_config(
    page_title="🧪 Production Incident → Podcast Generator (Tester's perspective)",
    page_icon="🧪 Production Incident → Podcast Generator (Tester's perspective",
    layout="wide"
)

st.title("🧪 Production Incident → Podcast Generator (Tester's perspective")
st.caption("Local Llama3-powered incident podcast assistant")

# --------------------------------------------------
# Sidebar Settings
# --------------------------------------------------
with st.sidebar:
    st.header("⚙️ Settings")

    model_name = st.selectbox(
        "Model",
        ["llama3", "llama3:70b", "mistral", "qwen2.5"],
        index=0
    )

    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=0.2,
        step=0.1
    )

    voice = st.selectbox(
        "Voice",
        [
            "en-US-AriaNeural",       # Female, natural/conversational
            "en-US-GuyNeural",        # Male, clear
            "en-GB-SoniaNeural",      # Female, British
            "en-GB-RyanNeural",       # Male, British
            "en-AU-NatashaNeural",    # Female, Australian
        ],
        index=0
    )

# --------------------------------------------------
# Input
# --------------------------------------------------
incident = st.text_area(
    "Describe incident / paste logs / test failure:",
    height=250,
    placeholder="Paste logs, failures, alerts, or incident details..."
)

# --------------------------------------------------
# Ollama Client
# --------------------------------------------------
ollama_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

# --------------------------------------------------
# Prompt Builder
# --------------------------------------------------
def build_prompt(incident_text: str) -> str:
    return f"""
You are a senior Test Engineer leading a production incident postmortem.

Turn the input into a structured engineering conversation.

Rules:
- Two engineers discussing the incident
- Focus on debugging steps, investigation, and root cause analysis
- Mention what tests or signals should have caught this earlier
- Include assumptions, mistakes, and validation steps
- Be technical and realistic
- Keep conversation natural like an engineering meeting

- YOU MUST identify a single most likely root cause
- If multiple causes exist, rank them and pick the primary one
- Include at least one concrete technical failure
- Avoid filler phrases

You MUST end your response with this section using exactly this heading:
# Voice Summary
Write 150-200 words summarising the incident, root cause, and prevention steps in a natural, conversational tone with no markdown.

Structure:
# Incident Summary
# Investigation Discussion
# Root Cause
# Prevention Plan
# Recommended Tests
# Voice Summary

Incident:
{incident_text}
"""

# --------------------------------------------------
# Voice Summary Extraction — handles heading variants
# --------------------------------------------------
def extract_voice_summary(text: str) -> str:
    # Match ## Voice Summary, # Voice Summary, **Voice Summary**, etc.
    match = re.search(
        r"#{1,3}\s*\*{0,2}Voice Summary\*{0,2}\s*\n+(.*?)(\n#{1,3}\s|\Z)",
        text,
        re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    return ""

# --------------------------------------------------
# Fallback: ask the model to summarise if section missing
# --------------------------------------------------
def get_voice_summary(output: str, model: str, temp: float) -> str:
    summary = extract_voice_summary(output)
    if summary:
        return summary

    st.info("Voice Summary section not found — running fallback summarisation...")

    fallback = ollama_client.chat.completions.create(
        model=model,
        temperature=temp,
        messages=[
            {
                "role": "user",
                "content": (
                    "Summarise this incident report in 150-200 words. "
                    "Use a conversational tone as if explaining to a colleague. "
                    "No markdown, no bullet points, plain prose only:\n\n"
                    + output
                )
            }
        ]
    )
    return fallback.choices[0].message.content.strip()

# --------------------------------------------------
# edge-tts Audio — free, no API key, neural quality
# --------------------------------------------------
def generate_audio(text: str, voice_name: str) -> bytes:
    async def _run() -> bytes:
        communicate = edge_tts.Communicate(text, voice=voice_name)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name
        try:
            await communicate.save(tmp_path)
            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            os.unlink(tmp_path)

    return asyncio.run(_run())

# --------------------------------------------------
# Generate Button
# --------------------------------------------------
if st.button("🎙️ Generate Podcast", use_container_width=True):

    if not incident.strip():
        st.warning("Please enter an incident or logs.")

    else:
        try:
            with st.spinner("Analyzing incident with LLaMA 3..."):
                prompt = build_prompt(incident)

                response = ollama_client.chat.completions.create(
                    model=model_name,
                    temperature=temperature,
                    messages=[
                        {
                            "role": "system",
                            "content": ("You are an expert Test Engineer, production incident investigator, "
                                        "performance bottleneck analyst, and distributed systems debugging assistant. "
                                        "You specialize in root cause analysis, scalability failures, observability gaps, "
                                        "resource exhaustion, race conditions, retry storms, caching failures, "
                                        "database bottlenecks, thread starvation, concurrency bugs, "
                                        "Kubernetes incidents, and CI/CD failures. "
                                        "Prioritize evidence-based reasoning, rank possible causes, "
                                        "identify the single most likely root cause, "
                                        "and prefer concrete technical explanations over vague summaries.")
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )

                output = response.choices[0].message.content

            # ----------------------------------------
            # Get voice summary (with fallback)
            # ----------------------------------------
            with st.spinner("Extracting voice summary..."):
                voice_summary = get_voice_summary(output, model_name, temperature)

            if not voice_summary:
                st.error("Could not generate a voice summary even with fallback. Check model output below.")
            else:
                with st.spinner("Generating audio with edge-tts..."):
                    audio_bytes = generate_audio(voice_summary, voice)

                if not audio_bytes:
                    st.error("Audio generation failed — empty output from edge-tts.")
                else:
                    st.success("Podcast generated successfully 🎧")
                    st.subheader("🎙️ Voice Playback")
                    st.audio(audio_bytes, format="audio/mp3")

            # ----------------------------------------
            # Always show the full report
            st.markdown("---")
            st.markdown(output)

            st.download_button(
                label="⬇️ Download Report",
                data=output,
                file_name="incident_podcast_report.md",
                mime="text/markdown"
            )

        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)