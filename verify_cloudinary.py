"""One-off Cloudinary integration check.

Exercises the real app service (app/services/storage.py), which reads
credentials from .env via app/core/config.py. Run:  python verify_cloudinary.py
Safe to delete once you've confirmed the integration works.
"""

from app.services.storage import upload_image, get_image_details, optimized_url

# A sample image from Cloudinary's public demo domain.
SAMPLE = "https://res.cloudinary.com/demo/image/upload/sample.jpg"


def main() -> None:
    # 1. Upload the sample image.
    result = upload_image(SAMPLE, public_id="onboarding_check")
    print("Upload OK")
    print("  secure_url:", result["secure_url"])
    print("  public_id :", result["public_id"])

    # 2. Fetch metadata for the uploaded asset.
    details = get_image_details(result["public_id"])
    print("Image details:")
    print("  width :", details["width"])
    print("  height:", details["height"])
    print("  format:", details["format"])
    print("  bytes :", details["bytes"])

    # 3. Build an f_auto + q_auto optimised delivery URL.
    url = optimized_url(result["public_id"])
    print("\nDone! Click link below to see the optimized version of the image.")
    print("Check the size and the format.")
    print("  ", url)


if __name__ == "__main__":
    main()
