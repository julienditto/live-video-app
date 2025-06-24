import subprocess
import time
import os
from google.cloud import storage
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
STREAM_KEY = "streamkey"
WATCH_DIR = f"/tmp/recordings"
GCS_BUCKET = "diveviz-bucket"
GCS_PREFIX = f"videos/{STREAM_KEY}/"  # Optional folder structure
SEGMENT_TIME = 9  # seconds

# Ensure watch directory exists
os.makedirs(WATCH_DIR, exist_ok=True)

# Set up GCS client
storage_client = storage.Client()
bucket = storage_client.bucket(GCS_BUCKET)

# Watchdog handler
class UploadHandler(FileSystemEventHandler):
    def on_closed(self, event):
        if not event.is_directory and event.src_path.endswith(".mp4"):
            self.upload_to_gcs(event.src_path)

    def upload_to_gcs(self, file_path):
        filename = os.path.basename(file_path)
        gcs_key = os.path.join(GCS_PREFIX, filename)
        print(f"Uploading {file_path} to gs://{GCS_BUCKET}/{gcs_key} ...")
        try:
            blob = bucket.blob(gcs_key)
            blob.upload_from_filename(file_path)
            print(f"Uploaded: {file_path}")
            os.remove(file_path)
            print(f"Deleted local: {file_path}")
        except Exception as e:
            print(f"Upload failed: {e}")

# Start ffmpeg in background loop
def start_ffmpeg_loop():
    while True:
        print("[INFO] Starting ffmpeg recording...")
        process = subprocess.Popen([
            "ffmpeg", "-i", f"rtmp://localhost/live/{STREAM_KEY}",
            "-c", "copy", "-f", "segment",
            "-segment_time", str(SEGMENT_TIME),
            "-reset_timestamps", "1", "-strftime", "1",
            f"{WATCH_DIR}/{STREAM_KEY}-%Y-%m-%d_%H-%M-%S.mp4"
        ])
        process.wait()
        print("[WARN] ffmpeg stopped. Restarting in 5 seconds...")
        time.sleep(5)

# Main program
if __name__ == "__main__":
    # Watchdog observer
    event_handler = UploadHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WATCH_DIR, recursive=False)
    observer.start()

    try:
        start_ffmpeg_loop()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()