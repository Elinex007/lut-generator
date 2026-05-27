import os
import uuid
import base64
from pathlib import Path

import numpy as np
import cv2
from flask import Flask, render_template, request, jsonify, send_file, abort
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from lut_engine import (
    image_to_bgr,
    compute_lab_stats,
    compute_histogram_stats,
    parse_style,
    build_lut,
    save_cube,
)

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB — frames can be large on 4K videos


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "Payload trop grand. Réduis le nombre de frames ou la qualité."}), 413


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": f"Erreur serveur : {e}"}), 500

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}


def decode_base64_frame(data_url: str) -> np.ndarray:
    """Convert a base64 data URL (JPEG/PNG) to a BGR numpy array."""
    header, encoded = data_url.split(",", 1)
    img_bytes = base64.b64decode(encoded)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    # Frames extracted client-side and sent as JSON base64 data URLs
    frames_b64 = request.form.getlist("frames[]")
    ref_file    = request.files.get("reference")
    description = request.form.get("description", "").strip()
    lut_name    = request.form.get("lut_name", "My LUT").strip() or "My LUT"

    if not frames_b64:
        return jsonify({"error": "Aucune frame reçue — sélectionne une vidéo."}), 400

    # Decode frames
    frames = []
    for f in frames_b64:
        try:
            bgr = decode_base64_frame(f)
            if bgr is not None:
                frames.append(bgr)
        except Exception:
            continue

    if not frames:
        return jsonify({"error": "Impossible de décoder les frames vidéo."}), 400

    # Reference image
    ref_bgr = None
    if ref_file and ref_file.filename and _ext(ref_file.filename) in ALLOWED_IMAGE:
        ref_bgr = image_to_bgr(ref_file.read())

    # Analyse
    src_stats = compute_lab_stats(frames)
    src_hist  = compute_histogram_stats(frames)
    ref_stats = compute_lab_stats([ref_bgr]) if ref_bgr is not None else None

    # Style via Claude
    style_params = parse_style(description, src_stats, ref_stats)

    # Build LUT
    job_id    = uuid.uuid4().hex[:10]
    lut_array = build_lut(src_stats, ref_stats, style_params, lut_name=lut_name)
    safe_name = secure_filename(lut_name.replace(" ", "_"))
    cube_path = OUTPUT_DIR / f"{job_id}_{safe_name}.cube"
    save_cube(lut_array, str(cube_path), lut_name=lut_name)

    return jsonify({
        "job_id": job_id,
        "lut_name": lut_name,
        "filename": cube_path.name,
        "download_url": f"/download/{cube_path.name}",
        "style_params": style_params,
        "source_analysis": {
            "frames_analyzed": len(frames),
            "lab_mean": src_stats["mean"].tolist(),
            "histogram": src_hist,
        },
        "has_reference": ref_stats is not None,
    })


@app.route("/download/<filename>")
def download(filename):
    safe = secure_filename(filename)
    path = OUTPUT_DIR / safe
    if not path.exists():
        abort(404)
    return send_file(str(path), as_attachment=True, download_name=safe)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug, host="0.0.0.0", port=port)
