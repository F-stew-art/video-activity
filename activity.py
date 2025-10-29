import os
import logging
import time
import json
import threading
from flask import (
    Flask,
    render_template_string,
    send_from_directory,
    abort,
    request,
)

# --- Configuration and Initialization ---
logging.basicConfig(level=logging.INFO)

VIDEO_FILENAME = "synced_video.mp4"
VIDEO_PATH = os.path.join(os.getcwd(), VIDEO_FILENAME)

app = Flask(__name__)
# Flask will handle routing and serving files.

# Global State Tracking (Protected by a lock for thread safety)
state_lock = threading.Lock()
video_state = {
    "action": "pause",  # 'play' or 'pause'
    "time_s": 0.0,  # Last known timestamp
    "last_updated": time.time(),  # Server Unix timestamp when state was last changed
}

# --- Server Utility Functions ---


def get_current_dynamic_state():
    with state_lock:
        current_server_time = time.time()
        estimated_time = video_state["time_s"]

        # If the video was playing, advance the time based on how long it's been playing
        if video_state["action"] == "play":
            time_elapsed = current_server_time - video_state["last_updated"]
            estimated_time += time_elapsed

        return {
            "action": video_state["action"],
            "time": estimated_time,  # Send the estimated time
            "serverTime": current_server_time,
        }


with open("template.html", "r") as f:
    HTML_TEMPLATE = f.read()


@app.route("/")
def index():
    if not os.path.exists(VIDEO_PATH):
        return (
            f"<h1>Error: Video file '{VIDEO_FILENAME}' not found.</h1>"
            "<p>Please DM purplephi with this issue.</p>",
            500,
        )
    return render_template_string(HTML_TEMPLATE)


@app.route("/video/stream")
def stream():
    dir_path = os.path.dirname(os.path.abspath(__file__))
    try:
        response = send_from_directory(dir_path, VIDEO_FILENAME, as_attachment=False)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except FileNotFoundError:
        abort(404)


@app.route("/state", methods=["GET"])
def get_state():
    state = get_current_dynamic_state()
    return state, 200


@app.route("/command", methods=["POST"])
def handle_client_command():
    if not request.is_json:
        return "Must be JSON", 400

    data = request.get_json()
    action = data.get("action")
    time_s = data.get("time", 0.0)

    if action not in ["play", "pause", "seek"]:
        logging.warning(f"Invalid action received: {action}")
        return "Invalid action", 400

    # 1. Update Server State (Protected by lock)
    with state_lock:
        if action == "seek":
            # Only update the time and timestamp. DO NOT overwrite the action state.
            video_state["time_s"] = time_s
            video_state["last_updated"] = time.time()
            logging.info(
                f"Client commanded SEEK to {time_s:.2f}s. Action remains {video_state['action']}."
            )
        else:  # 'play' or 'pause'
            # Update action, time, and timestamp
            video_state["action"] = action
            video_state["time_s"] = time_s
            video_state["last_updated"] = time.time()
            logging.info(f"Client commanded {action} @ {time_s:.2f}s.")

    # 2. Polling clients will automatically pick up this change on their next GET request.
    return "OK", 200


if __name__ == "__main__":
    app.run(port=5000, threaded=True)
