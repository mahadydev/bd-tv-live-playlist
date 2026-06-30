# bd-tv-live-playlist

Channel data for the **BD TV Live** Samsung TV app. No backend — these static
files are fetched over HTTPS.

- `manifest.json` — lists the playlists + BDIX probe + category order.
- `channels.m3u` — open-internet channels (works on any network). Edit to add channels.
- `bdix.m3u` — BDIX-only channels (shown only on BD ISP networks).

**Add a channel:** edit `channels.m3u` (or `bdix.m3u`) — two lines each:

```
#EXTINF:-1 tvg-logo="LOGO_URL" group-title="CATEGORY",Channel Name
STREAM_URL
```

Commit. Every TV picks it up on next app launch (or the blue refresh key).

**TODO:** set `bdixProbe` in `manifest.json` to a small resource on a BDIX-only
host so the app can auto-detect BDIX networks.
