"""Generate website background images with the configured image model.

This script is tailored for the current Flask sales-forecasting website. It uses
the existing AICodeWith image API/model to create dark, premium, mint-accented
background artwork for each main page.

Outputs are written to ``static/img/generated/``:
  - page-import-bg.png
  - page-analysis-bg.png
  - page-prediction-bg.png
  - page-report-bg.png
  - site-background-card.png
  - generated-backgrounds.css

Usage:
  python image.py
  python image.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen


API_KEY = "sk-acw-c96736f9-d4ce71e3f112f324"
BASE_URL = "https://api.aicodewith.com"
MODEL = "gpt-image-2-beta"

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "static" / "img" / "generated"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def api_json(method: str, url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API request failed: {exc.code} {exc.reason}\n{detail}") from exc


BACKGROUND_TASKS = [
    {
        "name": "page-import-bg",
        "filename": "page-import-bg.png",
        "prompt": """
Create a gorgeous premium background for the DATA IMPORT page of a Chinese sales forecasting web app.
Mood: luxury dark productivity app, elegant and cinematic, nearly black canvas with mint green luminous accents.
Visual details: soft aurora-like mint glow, subtle glass refractions, faint precision grid, tiny grain, tasteful depth,
with generous dark negative space for large serif headline and upload card. No words, no logos, no people, no objects.
Palette: #04080f, #071a18, #7cf9c8, #2ee6a6, very low-opacity white highlights.
Composition: glow should sit slightly left/center and fade to the right; refined, beautiful, not noisy.
Aspect ratio 16:9, high resolution website background.
""".strip(),
    },
    {
        "name": "page-analysis-bg",
        "filename": "page-analysis-bg.png",
        "prompt": """
Create a gorgeous premium background for an OPERATIONS ANALYTICS dashboard page.
Mood: high-end data command center, dark glass, mint green analytical glow, elegant but readable.
Visual details: abstract flowing data ribbons, faint chart-like arcs and grid lines, soft depth layers, subtle particles,
no readable text, no numbers, no logos. Keep center and lower areas dark enough for KPI cards and ECharts panels.
Palette: deep black #04080f, blue-black #08111f, mint #7cf9c8, emerald #2ee6a6, cyan hints.
Aspect ratio 16:9, high resolution website background.
""".strip(),
    },
    {
        "name": "page-prediction-bg",
        "filename": "page-prediction-bg.png",
        "prompt": """
Create a gorgeous premium background for an AI FORECASTING LAB page in a sales prediction website.
Mood: refined machine learning workspace, futuristic but restrained, dark black canvas with mint neural glow.
Visual details: abstract neural paths, timeline curves, soft luminous nodes, glass haze, very faint forecasting waveforms,
no text, no logos, no people, no literal robots. Leave space for forms, sliders, and progress cards.
Palette: #04080f, #0a1118, #7cf9c8, #2ee6a6, tiny cyan highlights. Elegant and beautiful.
Aspect ratio 16:9, high resolution website background.
""".strip(),
    },
    {
        "name": "page-report-bg",
        "filename": "page-report-bg.png",
        "prompt": """
Create a gorgeous premium background for a DECISION REPORT page of a sales forecasting web app.
Mood: executive report, polished dark luxury, calm confidence, mint green highlights.
Visual details: subtle layered paper/glass sheets, soft radial glow, refined diagonal lines, faint report-like frames,
no readable text, no numbers, no logos. Must support charts, tables, and summary cards on top.
Palette: black #04080f, charcoal #111827, mint #7cf9c8, emerald #2ee6a6, restrained white highlights.
Aspect ratio 16:9, high resolution website background.
""".strip(),
    },
    {
        "name": "site-background-card",
        "filename": "site-background-card.png",
        "prompt": """
Create a luxurious dark glass-card surface texture for a mint-accented analytics web interface.
Look: translucent black glass, fine grain, elegant edge lighting, barely visible mint rim glow, soft inner shadow,
premium frosted surface. It should crop well behind cards and side panels. No text, no icons, no objects, no logos.
Color palette: #0a0f14, #111827, mint #7cf9c8 at very low opacity.
Aspect ratio 4:3, high resolution.
""".strip(),
    },
]


def create_task(prompt: str, image_urls: Iterable[str] | None = None) -> str:
    body: dict[str, object] = {
        "model": MODEL,
        "prompt": prompt,
        "size": "auto",
    }
    if image_urls:
        body["image_urls"] = list(image_urls)

    data = api_json("POST", f"{BASE_URL}/v1/images/generations", body)
    if "id" not in data:
        raise RuntimeError(f"Image API did not return task id: {data}")
    return str(data["id"])


def poll_task(task_id: str, interval_seconds: int = 5, timeout_seconds: int = 600) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = api_json("GET", f"{BASE_URL}/v1/tasks/{task_id}")
        status = result.get("status")

        if status == "completed":
            result_data = result.get("result_data") or []
            if not result_data or "url" not in result_data[0]:
                raise RuntimeError(f"Completed task has no image URL: {result}")
            return str(result_data[0]["url"])

        if status == "failed":
            raise RuntimeError(f"Image generation failed: {result}")

        print(f"  waiting for {task_id}: {status or 'unknown'}")
        time.sleep(interval_seconds)

    raise TimeoutError(f"Image generation timed out after {timeout_seconds}s: {task_id}")


def infer_extension(url: str, content_type: str | None, fallback: str = ".png") -> str:
    parsed_suffix = Path(urlparse(url).path).suffix.lower()
    if parsed_suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return parsed_suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed in {".png", ".jpg", ".jpeg", ".webp"}:
            return guessed
    return fallback


def download_image(url: str, output_path: Path) -> Path:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=120) as response:
        content = response.read()
        content_type = response.headers.get("content-type")

    extension = infer_extension(url, content_type, output_path.suffix)
    final_path = output_path.with_suffix(extension)
    final_path.write_bytes(content)
    return final_path


def write_css_snippet(generated_files: list[Path]) -> Path:
    by_stem = {path.stem: path.name for path in generated_files}
    css = f"""/* Generated by image.py. Copy the rules you want into static/css/style.css. */
:root {{
    --generated-bg-import: url('/static/img/generated/{by_stem.get('page-import-bg', 'page-import-bg.png')}');
    --generated-bg-analysis: url('/static/img/generated/{by_stem.get('page-analysis-bg', 'page-analysis-bg.png')}');
    --generated-bg-prediction: url('/static/img/generated/{by_stem.get('page-prediction-bg', 'page-prediction-bg.png')}');
    --generated-bg-report: url('/static/img/generated/{by_stem.get('page-report-bg', 'page-report-bg.png')}');
    --generated-bg-card: url('/static/img/generated/{by_stem.get('site-background-card', 'site-background-card.png')}');
}}

.momentum-page {{
    background-image: var(--generated-bg-import);
    background-size: cover;
    background-position: center;
}}

body.page-analysis {{ background-image: var(--generated-bg-analysis); }}
body.page-prediction {{ background-image: var(--generated-bg-prediction); }}
body.page-report {{ background-image: var(--generated-bg-report); }}

.momentum-input-card,
.momentum-info-card {{
    background-image: linear-gradient(rgba(255,255,255,0.045), rgba(255,255,255,0.045)), var(--generated-bg-card);
    background-size: cover;
    background-position: center;
}}
"""
    css_path = OUTPUT_DIR / "generated-backgrounds.css"
    css_path.write_text(css, encoding="utf-8")
    return css_path


def generate_backgrounds(dry_run: bool = False) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_files: list[Path] = []

    for item in BACKGROUND_TASKS:
        output_path = OUTPUT_DIR / item["filename"]
        print(f"Generating {item['name']} -> {output_path}")
        print(f"Prompt:\n{item['prompt']}\n")

        if dry_run:
            continue

        task_id = create_task(item["prompt"])
        print(f"  task id: {task_id}")
        image_url = poll_task(task_id)
        print(f"  image url: {image_url}")
        saved_path = download_image(image_url, output_path)
        print(f"  saved: {saved_path}")
        generated_files.append(saved_path)

    if dry_run:
        print("Dry run complete. No API calls were made and no images were downloaded.")
        return

    css_path = write_css_snippet(generated_files)
    print(f"CSS snippet saved: {css_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate website background images with the image API.")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts and output paths without API calls.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generate_backgrounds(dry_run=args.dry_run)
