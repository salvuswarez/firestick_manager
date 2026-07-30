import os
import shutil
import subprocess
import zipfile

import requests
from bs4 import BeautifulSoup

# CONFIGURATIONF
FIRE_STICKS = ["192.168.1.50"]  # Replace with your IPs
GOLD_CONFIG_PATH = "./assets/.kodi"
APK_PATH = "./assets/kodi_latest.apk"
REMOTE_KODI_PATH = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi"
# Direct mirror link for stable ARMv7 (32-bit) for Fire Sticks
KODI_MIRROR_URL = "https://mirrors.kodi.tv/releases/android/arm/kodi-21.3-Omega-armeabi-v7a.apk"

BLOAT_PACKAGES = [
    "com.amazon.shoptv.client",
    "com.amazon.shoptv.firetv.client",
    "com.amazon.alexashopping",
    "com.amazon.client.metrics",
    "com.amazon.device.logmanager",
    "com.amazon.tv.fw.metrics",
    "com.amazon.kso.blackbird",
    "com.amazon.bueller.photos",
    "com.amazon.recess",
    "com.amazon.tahoe",
    "com.amazon.ags.app",
    "com.amazon.ods.kindleconnect",
    "com.amazon.firehomestarter",
    "com.amazon.logan",
]


def re_enable_bloatware(ip):
    target = f"-s {ip}:5555"
    print(f"Restoring Amazon services on {ip}...")

    for package in BLOAT_PACKAGES:
        # 'enable' brings the app back instantly without a reboot
        result = run_adb(f"{target} shell pm enable {package}")
        if "enabled" in result.lower():
            print(f"Restored: {package}")
        else:
            print(f"Could not restore {package} (it might not have been disabled)")

    print(f"Restore complete for {ip}.")


def debloat_device(ip):
    target = f"-s {ip}:5555"
    for package in BLOAT_PACKAGES:
        print(f"Disabling {package}...")
        # Use disable-user for safety or uninstall --user 0 for more space
        run_adb(f"{target} shell pm disable-user --user 0 {package}")


def find_kodi_paths(ip):
    """
    Searches the Firestick for the existing Kodi APK and configuration folder.
    Returns a tuple of (apk_remote_path, config_remote_path).
    """
    target = f"-s {ip}:5555"
    print(f"Searching for Kodi on {ip}...")

    # 1. Find the exact path of the installed APK
    # Result looks like: package:/data/app/org.xbmc.kodi-XXX/base.apk
    path_cmd = f"adb {target} shell pm path org.xbmc.kodi.tp"
    result = subprocess.run(path_cmd, shell=True, capture_output=True, text=True)

    if "package:" not in result.stdout:
        print("Error: Kodi is not installed on this device.")
        return None, None

    # Clean the output to get just the file path
    apk_remote_path = result.stdout.replace("package:", "").strip()

    # 2. Define the standard Kodi data directory
    # This contains the .kodi folder with your builds and settings
    config_remote_path = "/sdcard/Android/data/org.xbmc.kodi/files/.kodi"

    print(f"Found APK at: {apk_remote_path}")
    print(f"Found Config at: {config_remote_path}")

    return apk_remote_path, config_remote_path


def capture_gold_image(ip):
    # Ensure the local assets directory exists
    os.makedirs("./assets", exist_ok=True)

    print(f"Connecting to source device: {ip}...")
    # Explicitly check for successful connection
    connect_res = run_adb(f"connect {ip}:5555")
    if "connected" not in connect_res.lower():
        print(f"Failed to connect to {ip}. Output: {connect_res}")
        return

    target = f"-s {ip}:5555"

    # 1. Extract APK
    print("Extracting APK...")
    path_output = run_adb(f"{target} shell pm path org.xbmc.kodi")
    if "package:" in path_output:
        remote_apk_path = path_output.replace("package:", "").strip()
        # Use absolute or verified relative path for the destination
        local_apk = os.path.abspath(APK_PATH)
        print(f"Pulling {remote_apk_path} to {local_apk}")
        run_adb(f'{target} pull "{remote_apk_path}" "{local_apk}"')
    else:
        print("Kodi APK path not found. Is it installed?")
        return

    # 2. Pull Configuration Folder
    print("Extracting Kodi configuration (.kodi)...")
    local_config = os.path.abspath(GOLD_CONFIG_PATH)
    # Pulling a directory: ensure the command reflects the folder structure
    res = run_adb(f'{target} pull /sdcard/Android/data/org.xbmc.kodi/files/.kodi "{local_config}"')
    print(f"Pull Result: {res}")

    run_adb(f"disconnect {ip}:5555")
    print("Capture process finished. Check your ./assets/ folder.")


def download_latest_kodi():
    base_url = "https://mirrors.kodi.tv/releases/android/arm64-v8a/"

    # 1. Get the directory listing
    response = requests.get(base_url)
    if response.status_code != 200:
        print("Could not access mirror directory.")
        return

    # 2. Find all .apk links
    soup = BeautifulSoup(response.text, "html.parser")
    links = [a["href"] for a in soup.find_all("a", href=True) if a["href"].endswith(".apk")]

    # 3. Filter for stable releases (ignore "beta" or "rc" if you only want stable)
    stable_links = [l for l in links if "beta" not in l.lower() and "rc" not in l.lower()]

    if not stable_links:
        print("No stable APKs found.")
        return

    # 4. Sort and pick the latest (Kodi uses names like Omega, Nexus, etc.)
    # Sorting alphabetically works well because version numbers follow the names
    latest_filename = sorted(stable_links)[-1]
    full_download_url = base_url + latest_filename

    print(f"Latest version found: {latest_filename}")

    # 5. Download the actual file
    apk_response = requests.get(full_download_url, stream=True)
    with open("latest_kodi.apk", "wb") as f:
        for chunk in apk_response.iter_content(chunk_size=8192):
            f.write(chunk)

    print("Download complete.")


def run_adb(cmd):
    result = subprocess.run(f"adb {cmd}", shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ADB Error: {result.stderr.strip()}")  # This will show why pull/path failed
    return result.stdout.strip()


def prep_userdata():
    """Cleans the .kodi folder."""

    # 1. Clean up unneeded files/folders before zipping
    folders_to_delete = ["temp", "system"]
    for folder in folders_to_delete:
        path = os.path.join(GOLD_CONFIG_PATH, folder)
        if os.path.exists(path):
            print(f"Removing {folder}...")
            shutil.rmtree(path)

    # Clean Textures database to prevent broken icons
    db_path = os.path.join(GOLD_CONFIG_PATH, "userdata", "Database", "Textures13.db")
    if os.path.exists(db_path):
        os.remove(db_path)


def main():
    # Pre-process the image
    # prep_userdata()

    for ip in FIRE_STICKS:
        print(f"\n>>> Processing {ip}")
        run_adb(f"connect {ip}:5555")
        debloat_device(ip)

        target = f"-s {ip}:5555"

        # 1. Install APK (Ensure you use the ARM version for Firestick!)
        print(f"Installing {APK_PATH}...")
        run_adb(f'{target} install -r "{APK_PATH}"')

        # 2. Force Stop & Clear old data
        run_adb(f"{target} shell am force-stop org.xbmc.kodi")
        run_adb(f"{target} shell rm -rf /sdcard/Android/data/org.xbmc.kodi/files/.kodi")
        run_adb(f"{target} shell mkdir -p /sdcard/Android/data/org.xbmc.kodi/files/.kodi")

        print("Uploading profile data...")
        # 3. Push the CLEANED local folders directly
        for folder in ["addons", "userdata"]:
            local_folder = os.path.join(GOLD_CONFIG_PATH, folder)
            if os.path.exists(local_folder):
                print(f"Pushing {folder}...")
                subprocess.run(f'adb {target} push "{local_folder}" {REMOTE_KODI_PATH}/', shell=True)

        run_adb(f"disconnect {ip}:5555")
        print(f"Successfully deployed to {ip}")


if __name__ == "__main__":
    # download_latest_kodi()
    ip = "192.168.1.50"
    run_adb(f"connect {ip}:5555")
    debloat_device(ip)
    # main()
