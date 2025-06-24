from flask import Flask, session, redirect, url_for, request, render_template, jsonify, Response, abort
import hmac
import hashlib
import time
import os
import logging
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Replace with strong secret key
app.logger.setLevel(logging.INFO)

def generate_signed_url(path, expiry_seconds=600):
    secret = app.secret_key.encode()
    expiry = int(time.time()) + expiry_seconds
    message = f"{path}?expiry={expiry}".encode()
    sig = hmac.new(secret, message, hashlib.sha256).hexdigest()
    signed_url = f"{path}?expiry={expiry}&sig={sig}"
    return signed_url


def validate_token(path, expiry, sig):
    secret = app.secret_key.encode()
    message = f"/hls/streamkey/index.m3u8?expiry={expiry}".encode()
    expected_sig = hmac.new(secret, message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, sig):
        return False
    if int(expiry) < int(time.time()):
        return False
    return True


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        # For demo: accept any username/password, implement real auth here
        if username and password:
            session["user"] = username
            return redirect(url_for("player"))
        return "Invalid credentials", 401

    return '''
    <form method="post">
      Username: <input name="username"><br>
      Password: <input name="password" type="password"><br>
      <input type="submit" value="Login">
    </form>
    '''


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def player():
    if "user" not in session:
        return redirect(url_for("login"))
    # Render the player page, which fetches the signed URL dynamically
    return render_template("player.html")

#fetched by javascript
@app.route("/api/get_signed_url")
def get_signed_url():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    stream_path = "/hls/streamkey/index.m3u8"
    signed_url = generate_signed_url(stream_path, expiry_seconds=600)
    return jsonify({"signed_url": signed_url})

@app.route("/validate_token")
def validate_token_endpoint():
    original_uri = request.headers.get('X-Original-URI')
    original_args = request.headers.get('X-Original-Args')

    # Parse from original_uri if present
    if original_uri:
        parsed_url = urlparse(original_uri)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

    # Also parse from original_args if present, and merge with query_params
    if original_args:
        args_params = parse_qs(original_args)
        # Merge args_params into query_params, overriding duplicates from original_args
        query_params.update(args_params)

    expiry = query_params.get('expiry', [None])[0]
    sig = query_params.get('sig', [None])[0]

    if not path or not expiry or not sig:
        return jsonify({"valid": False, "error": "Missing headers"}), 400

    if validate_token(path, expiry, sig):
        return jsonify({"valid": True})
    else:
        print("failed to authenticate .ts token")
        return jsonify({"valid": False}), 403


@app.route("/hls/streamkey/index.m3u8")
def serve_signed_playlist():
    if "user" not in session:
        return abort(401)

    expiry = request.args.get("expiry")
    sig = request.args.get("sig")

    playlist_path = f"/hls/streamkey/index.m3u8"
    if not expiry or not sig or not validate_token(playlist_path, expiry, sig):
        return "Invalid or expired signature", 403

    abs_path = os.path.join("/tmp", playlist_path.strip("/"))
    if not os.path.exists(abs_path):
        return "Playlist not found", 404

    with open(abs_path) as f:
        playlist = f.read()

    # Sign each .ts line
    def sign_line(line):
        line = line.strip()
        if line.endswith(".ts"):
            segment_path = f"/hls/streamkey/{line}"
            signed_url = f"{segment_path}?expiry={expiry}&sig={sig}"
            return signed_url
        return line

    signed_content = "\n".join(sign_line(l) for l in playlist.splitlines())
    response = Response(signed_content, mimetype="application/vnd.apple.mpegurl")
    return response

#if __name__ == "__main__":
#    app.run(debug=True)