"""The Android app ships a copy of the catalog; make sure it never drifts from the source."""

import json
from pathlib import Path

from datas.catalog import bundled_path

ROOT = Path(__file__).resolve().parents[1]


def test_android_catalog_in_sync():
    android = ROOT / "android/app/src/main/assets/models.json"
    assert android.exists(), (
        "run: cp datas/catalog/models.json android/app/src/main/assets/models.json"
    )
    assert json.loads(android.read_text()) == json.loads(bundled_path().read_text())


def test_android_project_has_required_files():
    for rel in (
        "android/settings.gradle.kts",
        "android/app/build.gradle.kts",
        "android/app/src/main/AndroidManifest.xml",
        "android/gradlew",
        "android/gradle/wrapper/gradle-wrapper.jar",
        "scripts/android-fetch-llamacpp.sh",
    ):
        assert (ROOT / rel).exists(), rel
