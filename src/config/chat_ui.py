"""Shared chat UI helpers for response hints and command parsing."""

NEW_SESSION_COMMAND = "/start"
NEW_SESSION_HINT = "Type /start to create a new session."


def _build_agent_intro_message(model_name: str | None) -> str:
    model_line = f"\n MODEL AKTIF: {model_name}\n" if model_name else ""
    return (
        "Halo, saya adalah Site Reliability Egineering (SRE) Agent.\n"
        "Saya bisa membantu anda untuk:\n"
        "- Monitoring Kubernetes (kesehatan deployment, status pod, sumber daya cluster)\n"
        "- Analisis log Elasticsearch (pencarian, pola error, investigasi insiden)\n"
        "Batasan cakupan:\n"
        "- Saya tidak dapat mengeksekusi perubahan infrastruktur atau operasi tulis lainnya.\n"
        "- Saya tidak dapat menjawab pertanyaan di luar topik SRE.\n"
        
        "Perintah:\n"
        "/start - Show this welcome message\n"
        "/help - Get help and command list\n"
        "/status - Check bot status\n"
        "/clear_context - Clear your conversation history\n"
        "/conversation_info - View your conversation details\n"

        f"{model_line}\n"
    )


def get_agent_intro_message() -> str:
    """Build the intro message with the currently active model."""
    from src.config.settings import get_active_deployment

    return _build_agent_intro_message(get_active_deployment())


AGENT_INTRO_MESSAGE = get_agent_intro_message()


def is_new_session_command(message: str) -> bool:
    """Return True when the user requested a new session via command text."""
    return message.strip().lower() == NEW_SESSION_COMMAND


def with_new_session_hint(message: str) -> str:
    """Append session-reset hint once at the bottom of a response."""
    stripped = message.rstrip()
    if NEW_SESSION_HINT in stripped:
        return stripped
    return f"{stripped}\n\n{NEW_SESSION_HINT}"
