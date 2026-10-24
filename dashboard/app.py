"""Web dashboard for the kitchen clock: bridges a browser to the MQTT broker.

Configuration uses the same names as the clock's settings.toml:
MQTT_BROKER, MQTT_BROKER_PORT, MQTT_BROKER_USER, MQTT_BROKER_PASS, TOPIC_PREFIX.
"""

import asyncio
import json
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
log = logging.getLogger("dashboard")

BROKER = os.getenv("MQTT_BROKER", "")
BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT") or 1883)
BROKER_USER = os.getenv("MQTT_BROKER_USER") or None
BROKER_PASS = os.getenv("MQTT_BROKER_PASS") or None
TOPIC_PREFIX = (os.getenv("TOPIC_PREFIX") or "/matrixportal").rstrip("/")

LOG_SIZE = 200
STATUS_MAX_AGE = 60  # seconds before a page load re-pings the clock
STATIC_DIR = Path(__file__).parent / "static"


class Hub:
    """Tracks the latest message per topic and fans events out to SSE clients."""

    def __init__(self):
        self.connected = False
        self.topics = {}
        self.log = deque(maxlen=LOG_SIZE)
        self.subscribers = set()
        self.loop = None

    def snapshot(self):
        return {"connected": self.connected, "topics": self.topics, "log": list(self.log)}

    def emit(self, event):
        """Must run on the event loop thread."""
        if event["type"] == "message":
            self.topics[event["topic"]] = event
            self.log.append(event)
        elif event["type"] == "connection":
            self.connected = event["connected"]
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow client: drop it; EventSource reconnects and gets a fresh snapshot
                self.subscribers.discard(queue)

    def emit_threadsafe(self, event):
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.emit, event)


hub = Hub()
client = None


def on_connect(cli, _userdata, _flags, reason_code, _properties):
    if reason_code.is_failure:
        log.error("MQTT connect failed: %s", reason_code)
        return
    log.info("Connected to MQTT broker %s:%s", BROKER, BROKER_PORT)
    cli.subscribe(f"{TOPIC_PREFIX}/#")
    cli.publish(f"{TOPIC_PREFIX}/ping", "")
    hub.emit_threadsafe({"type": "connection", "connected": True})


def on_disconnect(_cli, _userdata, _flags, reason_code, _properties):
    log.warning("Disconnected from MQTT broker: %s", reason_code)
    hub.emit_threadsafe({"type": "connection", "connected": False})


def on_message(_cli, _userdata, msg):
    hub.emit_threadsafe(
        {
            "type": "message",
            "topic": msg.topic,
            "payload": msg.payload.decode("utf-8", errors="replace"),
            "retain": bool(msg.retain),
            "ts": time.time(),
        }
    )


@asynccontextmanager
async def lifespan(_app):
    global client
    if not BROKER:
        raise RuntimeError("MQTT_BROKER is not set")
    hub.loop = asyncio.get_running_loop()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if BROKER_USER:
        client.username_pw_set(BROKER_USER, BROKER_PASS)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    # connect_async + loop_start keeps retrying if the broker is down at startup
    client.connect_async(BROKER, BROKER_PORT)
    client.loop_start()
    try:
        yield
    finally:
        client.loop_stop()
        client.disconnect()


app = FastAPI(title="Kitchen Clock Dashboard", lifespan=lifespan)


class PublishRequest(BaseModel):
    # Topic relative to TOPIC_PREFIX, e.g. "brightness" or "msg"
    topic: str
    payload: str = ""
    retain: bool = False


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
async def config():
    return {"broker": f"{BROKER}:{BROKER_PORT}", "prefix": TOPIC_PREFIX}


@app.post("/api/publish")
async def publish(req: PublishRequest):
    suffix = req.topic.strip("/")
    if not suffix or any(c in suffix for c in "+#\0") or ".." in suffix.split("/"):
        raise HTTPException(status_code=400, detail="invalid topic")
    if not hub.connected:
        raise HTTPException(status_code=503, detail="not connected to MQTT broker")
    topic = f"{TOPIC_PREFIX}/{suffix}"
    info = client.publish(topic, req.payload, retain=req.retain)
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        raise HTTPException(status_code=502, detail=mqtt.error_string(info.rc))
    return {"topic": topic}


def request_status_if_stale():
    """The clock only reports status every 10 minutes (not retained), so ask for it."""
    last = hub.topics.get(f"{TOPIC_PREFIX}/status")
    if hub.connected and (last is None or time.time() - last["ts"] > STATUS_MAX_AGE):
        client.publish(f"{TOPIC_PREFIX}/ping", "")


@app.get("/api/events")
async def events():
    queue = asyncio.Queue(maxsize=500)
    hub.subscribers.add(queue)
    request_status_if_stale()

    async def stream():
        try:
            yield f"event: snapshot\ndata: {json.dumps(hub.snapshot())}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        finally:
            hub.subscribers.discard(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
