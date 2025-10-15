import requests
import m3u8
import time
import re
from datetime import datetime
from io import BytesIO
from mutagen.id3 import ID3, ID3NoHeaderError

MASTER_HLS_URL = "https://cf98fa7b2ee4450e.mediapackage.us-east-1.amazonaws.com/out/v1/3a9c4275036341c297c9860c3c4c7f2d/index.m3u8"
LOCAL_TS_PATH = "./id3_blocks/id3.ts"  # For testing local TS file

seen_segments = set()


def get_playlist(url):
    """Fetch the latest m3u8 playlist (master or media)."""
    try:
        return m3u8.load(url)
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Failed to load playlist: {e}")
        return None


def get_lowest_bitrate_variant(master_url):
    """If this is a master playlist, select the lowest bitrate variant."""
    playlist = get_playlist(master_url)
    if not playlist:
        return None

    # If it's already a media playlist (has segments), just return the same URL
    if playlist.segments:
        print(f"ℹ️ Provided URL is already a media playlist.")
        return master_url

    # Otherwise, pick the lowest bitrate variant
    if not playlist.playlists:
        print(f"⚠️ No variants found in master playlist.")
        return None

    lowest_variant = min(playlist.playlists, key=lambda p: p.stream_info.bandwidth or 999999999)
    lowest_url = lowest_variant.absolute_uri
    print(f"✅ Selected lowest bitrate variant: {lowest_url}")
    return lowest_url


def extract_id3_blocks_from_response(content: bytes):
    """Extract all ID3 metadata blocks from a TS segment binary."""
    blocks = []
    for match in re.finditer(b"ID3", content):
        start = match.start()
        size_bytes = content[start + 6:start + 10]
        if len(size_bytes) < 4:
            continue
        size = 0
        for b in size_bytes:
            size = (size << 7) | (b & 0x7F)
        end = start + 10 + size
        blocks.append(content[start:end])
    return blocks


def decode_id3_with_mutagen(block: bytes):
    """Decode an ID3 block using Mutagen for detailed frame parsing."""
    try:
        tag = ID3(BytesIO(block))
        decoded = {}
        for frame in tag.values():
            if frame.FrameID == "PRIV":
                owner = frame.owner
                data = frame.data.decode(errors="ignore")
                decoded[f"PRIV:{owner}"] = data
            elif hasattr(frame, "text"):
                decoded[frame.FrameID] = frame.text
            else:
                decoded[frame.FrameID] = str(frame)
        return decoded
    except ID3NoHeaderError:
        return None
    except Exception as e:
        return {"error": str(e)}


def check_id3_in_segment(segment_url=None, program_date_time=None, local=False):
    """Download or read a TS segment, extract and parse all ID3 tags."""
    try:
        if local:
            with open(LOCAL_TS_PATH, "rb") as f:
                data = f.read()
        else:
            response = requests.get(segment_url, timeout=10)
            response.raise_for_status()
            data = response.content

        id3_blocks = extract_id3_blocks_from_response(data)

        if not id3_blocks:
            return

        for i, block in enumerate(id3_blocks, 1):
            decoded = decode_id3_with_mutagen(block)
            if (
                decoded
                and "error" not in decoded
                and "PRIV:com.elementaltechnologies.timestamp.utc" not in decoded
            ):
                print(f"🎯 {segment_url} @ {program_date_time}")
                print(f"    🏷️  Block {i}: {decoded}")

    except Exception as e:
        print(f"[{datetime.now()}] ⚠️ Error reading segment ({segment_url or LOCAL_TS_PATH}): {e}")


def monitor_hls(hls_url):
    """Continuously poll the HLS playlist for new segments and parse their ID3 tags."""
    print(f"🔍 Monitoring HLS TS stream: {hls_url}")
    while True:
        playlist = get_playlist(hls_url)
        if playlist and playlist.segments:
            for seg in playlist.segments:
                seg_url = seg.absolute_uri
                program_date_time = getattr(seg, "program_date_time", "N/A")
                if seg_url not in seen_segments:
                    seen_segments.add(seg_url)
                    check_id3_in_segment(segment_url=seg_url, program_date_time=program_date_time)
        time.sleep(5)


if __name__ == "__main__":
    # Determine actual media playlist (lowest bitrate)
    selected_hls = get_lowest_bitrate_variant(MASTER_HLS_URL)
    if not selected_hls:
        print("❌ Could not determine HLS variant to monitor.")
    else:
        monitor_hls(selected_hls)
