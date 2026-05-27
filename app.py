import os
import uuid
import json
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, abort
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from lut_engine import (
    extract_frames,
    image_to_bgr,
    compute_lab_stats,
    compute_histogram_stats,
    parse_style,
    build_lut,
    save_cube,
)

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mxf"}
ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    # --- Validate inputs ---
    if "video" not in request.files:
        return jsonify({"error": "Vidéo manquante"}), 400

    video_file = request.files["video"]
    ref_file   = request.files.get("reference")
    description = request.form.get("description", "").strip()
    lut_name    = request.form.get("lut_name", "My LUT").strip() or "My LUT"

    if not video_file.filename:
        return jsonify({"error": "Aucun fichier vidéo sélectionné"}), 400

    if _ext(video_file.filename) not in ALLOWED_VIDEO:
        return jsonify({"error": "Format vidéo non supporté"}), 400

    # --- Save uploads ---
    job_id     = uuid.uuid4().hex[:10]
    video_path = UPLOAD_DIR / f"{job_id}_video{_ext(video_file.filename)}"
    video_file.save(str(video_path))

    ref_bgr = None
    if ref_file and ref_file.filename and _ext(ref_file.filename) in ALLOWED_IMAGE:
        ref_bgr = image_to_bgr(ref_file.read())

    # --- Analyze source video ---
    frames = extract_frames(str(video_path), n_frames=20)
    if not frames:
        video_path.unlink(missing_ok=True)
        return jsonify({"error": "Impossible d'extraire des frames de la vidéo"}), 400

    src_stats = compute_lab_stats(frames)
    src_hist   = compute_histogram_stats(frames)

    ref_stats = None
    if ref_bgr is not None:
        ref_stats = compute_lab_stats([ref_bgr])

    # --- Parse style via Claude ---
    style_params = parse_style(description, src_stats, ref_stats)

    # --- Build & save LUT ---
    lut_array  = build_lut(src_stats, ref_stats, style_params, lut_name=lut_name)
    safe_name  = secure_filename(lut_name.replace(" ", "_"))
    cube_path  = OUTPUT_DIR / f"{job_id}_{safe_name}.cube"
    save_cube(lut_array, str(cube_path), lut_name=lut_name)

    # --- Cleanup upload ---
    video_path.unlink(missing_ok=True)

    # Build response info
    response = {
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
    }
    return jsonify(response)


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
