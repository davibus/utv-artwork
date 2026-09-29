import os
import sys
import time
import base64
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "utv-images"
OUTPUT_DIR = BASE_DIR / "utv-TMNT-images"

MODEL = "gpt-image-2"

# GPT Image supports:
# 1024x1024
# 1536x1024
# 1024x1536
# auto
IMAGE_SIZE = "auto"

# low / medium / high / auto
QUALITY = "high"

OUTPUT_FORMAT = "jpeg"
JPEG_QUALITY = 90

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10

# Delay between successful API calls.
# Helps avoid hitting rate limits when processing large batches.
DELAY_BETWEEN_IMAGES = 2

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


# ============================================================
# VORTEX ART STYLE
# ============================================================

STYLE_PROMPT = """
Recreate the supplied photograph as a highly stylized animated illustration.

IMPORTANT:
Keep the same UTV, vehicle design, number of vehicles, people, terrain,
camera position, perspective, action, composition, and overall scene from
the original photograph. The resulting image should clearly be a
recognizable artistic recreation of the source image rather than a
completely different scene.

ART DIRECTION:

Create a rebellious hand-drawn teenage sketchbook / underground comic
animation aesthetic.

Use deliberately imperfect, energetic hand-drawn linework. Outlines should
feel rough, loose, scratchy, asymmetrical, and slightly inconsistent rather
than digitally perfect.

Blend convincing dimensional vehicle forms with expressive 2D illustration.
The UTV should retain enough realistic volume and recognizable mechanical
detail to clearly resemble the original vehicle while being heavily
stylized.

Use chunky ink contours, scribbled secondary lines, sketch marks,
cross-hatching, dry-brush marks, pencil scratches, paint streaks, and
occasional graffiti-like visual accents.

Use intentionally imperfect geometry. Tires, suspension, body panels,
terrain, rocks, dust clouds, vegetation, buildings and distant objects can
have slightly distorted or hand-drawn shapes.

The image should feel like a living drawing rather than polished CGI.

Foreground objects should contain stronger definition and dimensionality.
As objects move farther from the camera, progressively simplify and distort
their outlines and details.

Use highly expressive perspective and motion. Emphasize speed, jumping,
rock crawling, drifting, dust, mud, suspension movement, tire deformation,
or impact whenever those elements appear in the source image.

Use bold graphic shadow shapes rather than smooth photographic shading.
Mix cel-shaded dimensional forms with irregular marker, pencil and painted
textures.

Color treatment should be vivid but somewhat dirty and handmade:
deep blacks, desaturated environmental colors, strong accent colors,
uneven fills, slightly misregistered edges, subtle paper/grain texture,
and occasional color spilling outside linework.

Dust, smoke and clouds should use loose expressive brush strokes and
scribbled shapes.

Ground textures should include rough hatch marks, scratches, simplified
shapes and irregular painted areas.

Do NOT add Teenage Mutant Ninja Turtles characters.
Do NOT add recognizable copyrighted characters.
Do NOT add text, logos, captions, comic dialogue, watermarks or lettering
that are not present in the original photograph.

Do not replace the UTV with a fictional vehicle.

The goal is to transform the supplied UTV photograph into a gritty,
youthful, intentionally imperfect hand-drawn animated action illustration
while retaining the identity and composition of the original photograph.

Make the finished artwork suitable for a high-energy off-road UTV brand.
"""


# ============================================================
# HELPERS
# ============================================================

def get_api_key():
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        print()
        print("ERROR: OPENAI_API_KEY is not set.")
        print()
        print("PowerShell example:")
        print('$env:OPENAI_API_KEY="your-api-key-here"')
        print()
        sys.exit(1)

    return api_key


def find_images():
    if not INPUT_DIR.exists():
        print(f"ERROR: Input folder does not exist:")
        print(INPUT_DIR)
        sys.exit(1)

    images = [
        path
        for path in INPUT_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    return sorted(images)


def output_path_for(input_path):
    return OUTPUT_DIR / f"{input_path.stem}.jpg"


def write_failure(input_path, error_message):
    log_path = OUTPUT_DIR / "failed-images.txt"

    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{input_path.name}\n")
        f.write(f"{error_message}\n")
        f.write("-" * 80 + "\n")


# ============================================================
# OPENAI IMAGE EDIT
# ============================================================

def recreate_image(api_key, input_path):
    url = "https://api.openai.com/v1/images/edits"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    data = {
        "model": MODEL,
        "prompt": STYLE_PROMPT,
        "size": IMAGE_SIZE,
        "quality": QUALITY,
        "output_format": OUTPUT_FORMAT,
        "output_compression": str(JPEG_QUALITY),
        "n": "1",
    }

    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }

    mime_type = mime_types.get(
        input_path.suffix.lower(),
        "application/octet-stream"
    )

    with input_path.open("rb") as image_file:

        files = {
            "image": (
                input_path.name,
                image_file,
                mime_type
            )
        }

        response = requests.post(
            url,
            headers=headers,
            data=data,
            files=files,
            timeout=600
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"OpenAI API returned HTTP {response.status_code}\n"
            f"{response.text}"
        )

    result = response.json()

    if "data" not in result or not result["data"]:
        raise RuntimeError(
            f"No image data returned:\n{result}"
        )

    image_result = result["data"][0]

    # GPT Image normally returns base64 image data.
    if image_result.get("b64_json"):
        return base64.b64decode(image_result["b64_json"])

    # Fallback in case a URL is returned.
    if image_result.get("url"):
        image_response = requests.get(
            image_result["url"],
            timeout=300
        )
        image_response.raise_for_status()
        return image_response.content

    raise RuntimeError(
        f"Response contained no image:\n{result}"
    )


# ============================================================
# MAIN PROCESS
# ============================================================

def main():

    print()
    print("=" * 70)
    print("VORTEX UTV ARTWORK BATCH CREATOR")
    print("=" * 70)
    print()

    api_key = get_api_key()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    images = find_images()

    if not images:
        print(f"No images found in:")
        print(INPUT_DIR)
        return

    print(f"Input folder : {INPUT_DIR}")
    print(f"Output folder: {OUTPUT_DIR}")
    print(f"Model        : {MODEL}")
    print(f"Quality      : {QUALITY}")
    print()
    print(f"Images found: {len(images)}")
    print()

    completed = 0
    skipped = 0
    failed = 0

    for index, input_path in enumerate(images, start=1):

        output_path = output_path_for(input_path)

        print("-" * 70)
        print(
            f"[{index}/{len(images)}] "
            f"{input_path.name}"
        )

        # Resume functionality
        if output_path.exists():
            print(
                f"SKIP: already exists -> "
                f"{output_path.name}"
            )
            skipped += 1
            continue

        success = False

        for attempt in range(1, MAX_RETRIES + 1):

            try:
                if attempt > 1:
                    print(
                        f"Retry {attempt}/{MAX_RETRIES}..."
                    )

                print("Creating artwork...")

                image_bytes = recreate_image(
                    api_key,
                    input_path
                )

                with output_path.open("wb") as f:
                    f.write(image_bytes)

                print(
                    f"SAVED -> {output_path.name}"
                )

                completed += 1
                success = True
                break

            except Exception as exc:

                print(
                    f"ERROR: {exc}"
                )

                if attempt < MAX_RETRIES:
                    print(
                        f"Retrying in "
                        f"{RETRY_DELAY_SECONDS} seconds..."
                    )

                    time.sleep(
                        RETRY_DELAY_SECONDS
                    )

                else:
                    failed += 1

                    write_failure(
                        input_path,
                        str(exc)
                    )

                    print(
                        "FAILED after all retries."
                    )

        if success:
            time.sleep(DELAY_BETWEEN_IMAGES)

    print()
    print("=" * 70)
    print("FINISHED")
    print("=" * 70)
    print()
    print(f"Created : {completed}")
    print(f"Skipped : {skipped}")
    print(f"Failed  : {failed}")
    print(f"Total   : {len(images)}")
    print()
    print(f"Artwork saved in:")
    print(OUTPUT_DIR)
    print()


if __name__ == "__main__":
    main()