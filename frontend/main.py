"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    AgentInterface,
    Message,
    Part,
    Role,
    SendMessageRequest,
    TaskArtifactUpdateEvent,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google.protobuf.json_format import ParseDict

RESOURCE = os.environ["AGENT_ENGINE_RESOURCE_NAME"]
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = ParseDict(resp.json(), AgentCard(), ignore_unknown_fields=True)
        del card.supported_interfaces[:]
        card.supported_interfaces.append(AgentInterface(url=A2A_BASE, protocol_binding="JSONRPC"))
        card.supported_interfaces.append(AgentInterface(url=A2A_BASE, protocol_binding="HTTP_JSON"))
        _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)
        text = getattr(root, "text", None) or getattr(p, "text", None)
        if text:
            out.append({"kind": "text", "text": text})
        data = getattr(root, "data", None) or getattr(p, "data", None)
        if data is not None:
            meta = getattr(root, "metadata", None) or getattr(p, "metadata", None) or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else None
            if mime == _A2UI_MIME:
                out.append({"kind": "a2ui", "data": data})
        file_obj = getattr(root, "file", None) or getattr(p, "file", None)
        if file_obj is not None:
            uri = getattr(file_obj, "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(ClientConfig(httpx_client=client))
        a2a_client = factory.create(card)

        msg = SendMessageRequest(
            message=Message(
                message_id=str(uuid.uuid4()),
                role=Role.ROLE_USER,
                parts=[Part(text=message)],
                context_id=_contexts.get(user_id),
            )
        )

        last_task = None
        got_artifact_update = False
        async for event in a2a_client.send_message(msg):
            if hasattr(event, "HasField"):
                if event.HasField("task"):
                    last_task = event.task
                    if event.task.context_id:
                        _contexts[user_id] = event.task.context_id
                if event.HasField("artifact_update"):
                    got_artifact_update = True
                    parts.extend(_extract_parts(event.artifact_update.artifact.parts))
                if event.HasField("message"):
                    parts.extend(_extract_parts(event.message.parts))
                if event.HasField("status_update"):
                    if event.status_update.status.HasField("message"):
                        parts.extend(_extract_parts(event.status_update.status.message.parts))
            elif isinstance(event, Message):
                parts.extend(_extract_parts(event.parts))
            elif isinstance(event, tuple):
                task, update = event
                if task is not None:
                    last_task = task
                    if getattr(task, "context_id", None):
                        _contexts[user_id] = task.context_id
                if isinstance(update, TaskArtifactUpdateEvent):
                    got_artifact_update = True
                    parts.extend(_extract_parts(update.artifact.parts))
                elif isinstance(update, Message):
                    parts.extend(_extract_parts(update.parts))
                elif hasattr(update, "parts"):
                    parts.extend(_extract_parts(getattr(update, "parts")))
            elif hasattr(event, "parts"):
                parts.extend(_extract_parts(getattr(event, "parts")))

        # Non-streaming fallback: pull parts from the final task's artifacts.
        if not got_artifact_update and last_task is not None:
            for artifact in getattr(last_task, "artifacts", None) or []:
                parts.extend(_extract_parts(artifact.parts))

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


@app.get("/api/recordings")
async def list_recordings():
    rec_dir = "/config/Downloads/recordings"
    if not os.path.exists(rec_dir):
        return {"directory": rec_dir, "recordings": []}
    files = sorted([
        f for f in os.listdir(rec_dir)
        if f.lower().endswith(".mp3")
    ])
    return {"directory": rec_dir, "recordings": files}


# Serve the chat UI (keep this mount last so /chat wins).
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
