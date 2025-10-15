This python script performs following:

1. Find a child playlist for a provided master playlist with lowest bitrate
2. Download each HLS segment as they available
3. Search for ID3 PRIV frame and filter out noise
4. Once valid ID3 found, decode it with mutagen

- You can also check the offline TS segment for ID3 markers.
